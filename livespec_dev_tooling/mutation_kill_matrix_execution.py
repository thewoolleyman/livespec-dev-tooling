"""Test execution for the Rule-26 kill matrix: shared processes and isolated trees.

All of one mutant's selected tests run in ONE pytest process, which records
each test's own outcome through `mutation_kill_matrix_pytest_plugin`.  When
that process ends or times out before a test reports, the test is re-run
alone, and the lone run decides it: its recorded outcome when it reports one,
and otherwise its exit status, so a test that kills the process kills the
mutant.

Parallel workers each apply mutants in a private copy of the target, so no
worker ever sees another worker's mutant.  A copy is only sound when the
tests import the copy, so each worker's `PYTHONPATH` maps the target's own
import roots onto its copy, and a worker refuses to start while a mutated
module still resolves into the original target (an editable install).
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

from livespec_dev_tooling.mutation_kill_matrix_pytest_plugin import (
    OUTCOMES_VARIABLE,
    SELECT_VARIABLE,
    TIMEOUT_VARIABLE,
)

__all__: list[str] = [
    "PLUGIN_MODULE",
    "PYTHON",
    "TIMED_OUT_RETURNCODE",
    "CommandExecutor",
    "WorkerTree",
    "execute_command",
    "import_roots",
    "make_worker_tree",
    "outcome_environment",
    "read_outcomes",
    "run_selected",
]


PLUGIN_MODULE = "livespec_dev_tooling.mutation_kill_matrix_pytest_plugin"
# `-B`: an applied mutant usually has the source's size and lands within the
# same second, so a cached `.pyc` would pass its mtime-and-size check and the
# test would run the unmutated module. No child writes bytecode.
PYTHON = (sys.executable, "-B")
TIMED_OUT_RETURNCODE = 124
# Process start-up, collection and teardown on top of the tests' own timeouts.
_GRACE_SECONDS = 60.0
_COPY_SKIPPED = frozenset({".git", ".venv", "node_modules", "__pycache__", ".pytest_cache"})
_COPY_SKIPPED_AT_ROOT = frozenset({"reports", ".mutmut-cache", ".hypothesis"})


class CommandExecutor(Protocol):
    """Run one command from a directory and capture its result."""

    def __call__(
        self, *, args: list[str], cwd: Path, timeout: float | None = None
    ) -> subprocess.CompletedProcess[str]: ...


def execute_command(
    *, args: list[str], cwd: Path, timeout: float | None = None
) -> subprocess.CompletedProcess[str]:
    """Run one command; on timeout kill its whole process group and report 124."""
    with subprocess.Popen(  # noqa: S603 — caller-owned argv; never a shell string.
        args,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    ) as process:
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            stdout, stderr = process.communicate()
            return subprocess.CompletedProcess(args, TIMED_OUT_RETURNCODE, stdout, stderr)
    return subprocess.CompletedProcess(args, process.returncode, stdout, stderr)


def outcome_environment(*, outcomes: Path, timeout: float) -> tuple[str, ...]:
    """Return the `env` assignments that make the plugin record into `outcomes`."""
    return (f"{OUTCOMES_VARIABLE}={outcomes}", f"{TIMEOUT_VARIABLE}={timeout}")


def read_outcomes(*, outcomes: Path, slower_than: float = 0.0) -> dict[str, bool]:
    """Read the plugin's per-test lines as test node id -> failed.

    With `slower_than`, a test that ran longer than that many seconds also
    reads as failed: the baseline run arms no per-test timer, so this is how it
    judges the per-test timeout.
    """
    if not outcomes.is_file():
        return {}
    rows = (json.loads(line) for line in outcomes.read_text(encoding="utf-8").splitlines() if line)
    return {
        row["test"]: bool(row["failed"]) or (0 < slower_than < float(row["duration"]))
        for row in rows
    }


@dataclass(frozen=True, kw_only=True)
class WorkerTree:
    """One worker's private source tree and the environment its commands run under."""

    root: Path
    scratch: Path
    environment: tuple[str, ...] = ()


def _pytest_command(
    *, tree: WorkerTree, tests: list[str], outcomes: Path, timeout: float
) -> list[str]:
    """Build the one pytest command that runs `tests` and records each outcome."""
    select = tree.scratch / "selected-tests.txt"
    _ = select.write_text("\n".join(tests) + "\n", encoding="utf-8")
    files = sorted({test.split("::", 1)[0] for test in tests})
    return [
        "env",
        *tree.environment,
        *outcome_environment(outcomes=outcomes, timeout=timeout),
        f"{SELECT_VARIABLE}={select}",
        *PYTHON,
        "-m",
        "pytest",
        "-q",
        "-p",
        "no:cacheprovider",
        "-p",
        PLUGIN_MODULE,
        *files,
    ]


def _run_batch(
    *, execute: CommandExecutor, tree: WorkerTree, tests: list[str], timeout: float
) -> tuple[dict[str, bool], subprocess.CompletedProcess[str]]:
    """Run `tests` in one process and return what it recorded and how it ended."""
    outcomes = tree.scratch / "outcomes.jsonl"
    outcomes.unlink(missing_ok=True)
    result = execute(
        args=_pytest_command(tree=tree, tests=tests, outcomes=outcomes, timeout=timeout),
        cwd=tree.root,
        timeout=timeout * len(tests) + _GRACE_SECONDS,
    )
    recorded = read_outcomes(outcomes=outcomes)
    return {test: recorded[test] for test in tests if test in recorded}, result


def run_selected(
    *, execute: CommandExecutor, tree: WorkerTree, tests: list[str], timeout: float
) -> dict[str, bool]:
    """Return every test's own failed outcome, re-running alone any that went unreported."""
    if not tests:
        return {}
    outcomes, _ = _run_batch(execute=execute, tree=tree, tests=tests, timeout=timeout)
    for test in tests:
        if test in outcomes:
            continue
        alone, result = _run_batch(execute=execute, tree=tree, tests=[test], timeout=timeout)
        outcomes[test] = alone.get(test, result.returncode != 0)
    return outcomes


def import_roots(*, execute: CommandExecutor, target: Path) -> list[str]:
    """Return the target-relative `sys.path` entries the target's interpreter uses."""
    probe = execute(
        args=[*PYTHON, "-c", "import json, sys; print(json.dumps(sys.path))"], cwd=target
    )
    root = target.resolve()
    entries = cast("list[str]", json.loads(probe.stdout or "[]") if probe.returncode == 0 else [])
    roots: list[str] = []
    for entry in entries:
        path = Path(entry).resolve() if entry else None
        if path is not None and path.is_relative_to(root):
            relative = path.relative_to(root).as_posix()
            if relative not in roots:
                roots.append(relative)
    return roots


def _copy_tree(*, source: Path, destination: Path) -> None:
    """Copy the target, leaving caches and virtual environments behind, and root outputs."""
    for directory, names, files in os.walk(source):
        here = Path(directory)
        relative = here.relative_to(source)
        at_root = here == source
        names[:] = [
            name
            for name in names
            if name not in _COPY_SKIPPED and not (at_root and name in _COPY_SKIPPED_AT_ROOT)
        ]
        (destination / relative).mkdir(parents=True, exist_ok=True)
        for name in files:
            _ = shutil.copy2(here / name, destination / relative / name, follow_symlinks=False)


def _module_origin(*, execute: CommandExecutor, tree: WorkerTree, module: str) -> str:
    """Return where `module` resolves from inside the worker tree, or '' when it does not."""
    code = (
        "import importlib.util, sys\n"
        "try:\n"
        f"    spec = importlib.util.find_spec({module!r})\n"
        "except Exception:\n"
        "    spec = None\n"
        "print(spec.origin if spec is not None and spec.origin else '')\n"
    )
    result = execute(args=["env", *tree.environment, *PYTHON, "-c", code], cwd=tree.root)
    return result.stdout.strip() if result.returncode == 0 else ""


def make_worker_tree(
    *,
    execute: CommandExecutor,
    target: Path,
    workspace: Path,
    index: int,
    roots: list[str],
    modules: Iterable[str],
) -> WorkerTree:
    """Copy the target into a private tree whose tests import the copy, not the target."""
    root = workspace / f"worker-{index}" / target.name
    _copy_tree(source=target, destination=root)
    scratch = workspace / f"worker-{index}" / "scratch"
    scratch.mkdir()
    inherited = os.environ.get("PYTHONPATH", "")
    mapped = [str(root / relative) if relative != "." else str(root) for relative in roots]
    tree = WorkerTree(
        root=root,
        scratch=scratch,
        environment=(f"PYTHONPATH={os.pathsep.join(filter(None, (*mapped, inherited)))}",),
    )
    original = target.resolve()
    for module in sorted(set(modules)):
        origin = _module_origin(execute=execute, tree=tree, module=module)
        if origin and Path(origin).resolve().is_relative_to(original):
            message = (
                f"worker tree imports the original target: {module} resolves to {origin}, "
                "so a mutant applied in the copy would never run (an editable install?)"
            )
            raise RuntimeError(message)
    return tree
