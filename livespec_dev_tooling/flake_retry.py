"""Retry failures only when the changed tree cannot have caused them.

The pytest-rerunfailures marker is deliberately added only after a conservative
working-tree analysis. An analysis failure therefore means ``touched`` rather
than granting a retry on incomplete evidence.
"""

from __future__ import annotations

import ast
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest

from livespec_dev_tooling.gate_remote_invocation import Failure, default_gate_command_runner

if TYPE_CHECKING:
    from collections.abc import Iterable

    from _pytest.terminal import TerminalReporter

__all__: list[str] = [
    "RETRY_ATTEMPTS",
    "RETRY_DELAY_SECONDS",
    "RetryResult",
    "announce_retries",
    "mark_untouched_tests",
    "record_report",
    "retry_marker_for",
    "retry_summary",
    "write_retry_records",
]

RETRY_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 60
_UNSAFE_NAMES = {"pyproject.toml", "uv.lock", "justfile", "conftest.py"}
_RESULTS: dict[str, RetryResult] = {}


@dataclass(frozen=True, kw_only=True)
class RetryResult:
    """The final outcome of a test pytest-rerunfailures has retried."""

    nodeid: str
    attempts: int
    outcome: str


def _run_git(*, root: Path, args: list[str]) -> set[Path] | None:
    """Read one newline-delimited git path query, or report an unknown result."""
    invoked = default_gate_command_runner(argv=["git", *args], cwd=root)
    if isinstance(invoked, Failure):
        return None
    completed = invoked.unwrap()
    if completed.returncode != 0:
        return None
    return {Path(line) for line in completed.stdout.splitlines() if line}


def _default_branch_ref(*, repo_root: Path) -> str | None:
    """Name the remote default branch, or report that it cannot be known.

    `origin/HEAD` is the authority when it is set. A CI checkout usually does
    not set it, so the conventional `origin/main` and `origin/master` are tried
    next, and a repository with neither has no computable change set.
    """
    default = _run_git(root=repo_root, args=["symbolic-ref", "--short", "refs/remotes/origin/HEAD"])
    if default is not None and len(default) == 1:
        return next(iter(default)).as_posix()
    for candidate in ("origin/main", "origin/master"):
        if (
            _run_git(root=repo_root, args=["rev-parse", "--verify", "--quiet", candidate])
            is not None
        ):
            return candidate
    return None


def change_paths(*, repo_root: Path) -> set[Path] | None:
    """Return committed, index, working-tree, and untracked changes."""
    remote = _default_branch_ref(repo_root=repo_root)
    if remote is None:
        return None
    base = _run_git(root=repo_root, args=["merge-base", "HEAD", remote])
    head = _run_git(root=repo_root, args=["rev-parse", "HEAD"])
    if base is None or head is None or len(base) != 1 or len(head) != 1:
        return None
    comparison = "HEAD^" if base == head else next(iter(base)).as_posix()
    queries: tuple[list[str], ...] = (
        ["diff", "--name-only", comparison, "HEAD"],
        ["diff", "--name-only", "--cached"],
        ["diff", "--name-only"],
        ["ls-files", "--others", "--exclude-standard"],
    )
    changed: set[Path] = set()
    for query in queries:
        result = _run_git(root=repo_root, args=query)
        if result is None:
            return None
        changed.update(result)
    return changed


def _module_path(*, repo_root: Path, module: str) -> Path | None:
    """Resolve an in-repository dotted module without importing user code."""
    stem = Path(*module.split("."))
    for candidate in (repo_root / stem.with_suffix(".py"), repo_root / stem / "__init__.py"):
        if candidate.is_file():
            return candidate
    return None


def _imports(*, tree: ast.AST, path: Path, repo_root: Path) -> set[Path]:
    """Resolve direct static imports in one source module conservatively."""
    found: set[Path] = set()
    package = path.relative_to(repo_root).parent.parts
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                candidate = _module_path(repo_root=repo_root, module=alias.name)
                if candidate is not None:
                    found.add(candidate)
        elif isinstance(node, ast.ImportFrom):
            prefix = package[: max(0, len(package) - node.level + 1)] if node.level else ()
            module = ".".join((*prefix, *(node.module or "").split("."))).strip(".")
            if module:
                candidate = _module_path(repo_root=repo_root, module=module)
                if candidate is not None:
                    found.add(candidate)
            for alias in node.names:
                candidate = _module_path(
                    repo_root=repo_root, module=".".join((module, alias.name)).strip(".")
                )
                if candidate is not None:
                    found.add(candidate)
    return found


def _conftest_chain(*, repo_root: Path, test_path: Path) -> list[Path]:
    """Every `conftest.py` from the test's directory up to the repository root."""
    chain: list[Path] = []
    current = test_path.parent
    while True:
        conftest = current / "conftest.py"
        if conftest.is_file():
            chain.append(conftest)
        if current in (repo_root, current.parent):
            return chain
        current = current.parent


def _closure(*, repo_root: Path, test_path: Path) -> tuple[set[Path], set[str]] | None:
    """Read imports and string literals without executing the test tree."""
    pending = [test_path, *_conftest_chain(repo_root=repo_root, test_path=test_path)]
    modules: set[Path] = set()
    literals: set[str] = set()
    while pending:
        path = pending.pop()
        if path in modules:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError, UnicodeError):
            return None
        modules.add(path)
        literals.update(
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        )
        pending.extend(_imports(repo_root=repo_root, path=path, tree=tree) - modules)
    return modules, literals


def _changed_names(*, paths: set[Path]) -> set[str]:
    """Produce literal spellings that can identify changed code or data paths."""
    names: set[str] = set()
    for path in paths:
        names.update((path.as_posix(), path.name, *path.parts))
        if path.suffix == ".py":
            names.add(".".join(path.with_suffix("").parts))
    return names


def retry_marker_for(
    *, repo_root: Path, test_path: Path, change_paths: set[Path]
) -> dict[str, int] | None:
    """Return a rerun marker only when no changed path touches the closure."""
    if any(path.name in _UNSAFE_NAMES or path.name == Path(__file__).name for path in change_paths):
        return None
    analyzed = _closure(repo_root=repo_root, test_path=test_path)
    if analyzed is None:
        return None
    modules, literals = analyzed
    relative_modules = {path.relative_to(repo_root) for path in modules}
    if relative_modules & change_paths or literals & _changed_names(paths=change_paths):
        return None
    return {"reruns": RETRY_ATTEMPTS, "reruns_delay": RETRY_DELAY_SECONDS}


def mark_untouched_tests(*, root: Path, items: list[pytest.Item]) -> None:
    """Mark only tests proven untouched by this session's complete change set."""
    paths = change_paths(repo_root=root)
    if paths is None:
        return
    for item in items:
        marker = retry_marker_for(
            repo_root=root, test_path=Path(str(item.path)), change_paths=paths
        )
        if marker is not None:
            item.add_marker(pytest.mark.flaky(**marker))


def record_report(*, report: pytest.TestReport) -> None:
    """Keep final outcomes for rerunfailures' individual retry reports."""
    if report.when != "call":
        return
    previous = _RESULTS.get(report.nodeid)
    outcome = cast(str, report.outcome)
    if outcome == "rerun":
        _RESULTS[report.nodeid] = RetryResult(
            nodeid=report.nodeid,
            attempts=(previous.attempts if previous else 0) + 1,
            outcome="rerun",
        )
    elif previous is not None:
        _RESULTS[report.nodeid] = RetryResult(
            nodeid=report.nodeid, attempts=previous.attempts + 1, outcome=outcome
        )


def write_retry_records(*, repo_root: Path, results: Iterable[RetryResult]) -> Path:
    """Write one JSON line for each retried node id beneath the repository tmp tree."""
    output = repo_root / "tmp" / "flake-retries" / "retries.jsonl"
    _ = output.parent.mkdir(parents=True, exist_ok=True)
    _ = output.write_text(
        "".join(json.dumps(result.__dict__, sort_keys=True) + "\n" for result in results),
        encoding="utf-8",
    )
    return output


def retry_summary(*, results: Iterable[RetryResult]) -> str:
    """Render the loud terminal block required for every retry decision."""
    rows = [f"{result.nodeid}: {result.attempts} attempts, {result.outcome}" for result in results]
    return "FLAKE-RETRIED\n" + "\n".join(rows)


def announce_retries(*, terminalreporter: TerminalReporter, root: Path) -> None:
    """Persist and announce retry evidence without changing pytest's final verdict."""
    results = list(_RESULTS.values())
    if not results:
        return
    _ = write_retry_records(repo_root=root, results=results)
    _ = terminalreporter.write_sep("=", "FLAKE-RETRIED")
    for line in retry_summary(results=results).splitlines()[1:]:
        _ = terminalreporter.write_line(line)
    if os.environ.get("GITHUB_ACTIONS") == "true":
        for result in results:
            _ = terminalreporter.write_line(f"::warning::FLAKE-RETRIED {result.nodeid}")


# PYTEST CALLS ITS HOOKS POSITIONALLY. pluggy reads a hook's argument names off
# its signature and passes them by position, so a keyword-only hook receives
# nothing, and a `*args` hook receives nothing either (that shape INTERNALERRORed
# every session, run 01M6GVFTX08S). Each hook is therefore the bound `__call__`
# of a small adapter: the dunder takes pytest's fixed positional convention, and
# it hands straight on to the keyword-only function that does the work.
class _CollectionHook:
    def __call__(
        self, session: pytest.Session, config: pytest.Config, items: list[pytest.Item]
    ) -> None:
        del config
        mark_untouched_tests(root=Path(str(session.config.rootpath)), items=items)


class _ReportHook:
    def __call__(self, report: pytest.TestReport) -> None:
        record_report(report=report)


class _SummaryHook:
    def __call__(
        self, terminalreporter: TerminalReporter, exitstatus: int, config: pytest.Config
    ) -> None:
        del exitstatus
        announce_retries(terminalreporter=terminalreporter, root=Path(str(config.rootpath)))


pytest_collection_modifyitems = _CollectionHook().__call__
pytest_runtest_logreport = _ReportHook().__call__
pytest_terminal_summary = _SummaryHook().__call__
