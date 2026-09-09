"""Consumer-tier: self-application catches a regression before release.

Covers the `SPECIFICATION/scenarios.md` scenario "self-application
catches a regression before release". The consumer-observable contract:
when a check runs against a working tree that carries a regression (a
deliberately-injected rule violation), the check FAILS (exit non-zero)
and surfaces the offending file — so a PR that introduces the regression
cannot merge while the check is wired into the consumer's `just check`.

This test injects a regression into a synthetic consumer fixture and
asserts the shared `no_inheritance` check (run as a consumer would, via
`python -m`) catches it; the paired clean-tree assertion proves the
check does not false-positive. This is the regression-injection shape
the scenario describes, exercised at the consumer tier.

The check runs IN-PROCESS. `_run_no_inheritance` resolves the check by
module name (`importlib.import_module`), chdirs into the fixture with
`monkeypatch.chdir`, calls `main()`, and reads stdout/stderr off
`capsys`. A consumer reaches the SAME `main()` whether it names the
module via `python -m` or imports it, so the consumer-observable
contract here — non-zero exit on the injected regression, the offending
`src/mod.py` named in the diagnostic, exit `0` on the clean tree — is
untouched; only the capture mechanism changed. The regression case is
the one that most depends on faithful capture, and it still reads the
combined `stdout + stderr` exactly as it did off `CompletedProcess`.
Running in-process means no `COVERAGE_PROCESS_START`-instrumented child,
hence no `.coverage.*` write race when the parallel dispatcher schedules
this file beside others, and a faster run.

The `git` spawn in `_git` STAYS, which is why this file keeps its
`subprocess_spawn_allowlist` entry in `pyproject.toml`. The rerouted
checks derive their file universe from the git index
(`config.resolve_check_universe`), so producing a real git working tree
is the whole job of this fixture — there is no in-process equivalent to
substitute. Its hardcoded 3-key env (`HOME`, `GIT_CONFIG_GLOBAL`,
`PATH`) keeps `COVERAGE_PROCESS_START` and `COV_CORE_*` out of that
child, so the surviving spawn starts no coverage writer either.
"""

from __future__ import annotations

import importlib
import subprocess
from pathlib import Path
from typing import NamedTuple

import pytest

__all__: list[str] = []

pytestmark = pytest.mark.consumer

# The shared check under test, named exactly as a consumer names it in
# `python -m livespec_dev_tooling.checks.no_inheritance`.
_CHECK_MODULE = "livespec_dev_tooling.checks.no_inheritance"


class _CheckRun(NamedTuple):
    """The three `CompletedProcess` fields the assertions read, in-process."""

    returncode: int
    stdout: str
    stderr: str


_CONSUMER_PYPROJECT = (
    "[tool.livespec_dev_tooling]\n"
    'source_trees = ["src"]\n'
    'target_dirs = ["src"]\n'
    'source_tree_prefixes = ["src/"]\n'
)

# A regression: a class inheriting from a base OUTSIDE the closed
# direct-parent allowlist. `no_inheritance` rejects any `class X(Y):`
# whose terminal base is not in `{Exception, BaseException,
# LivespecError, Protocol, NamedTuple, TypedDict}`.
_REGRESSED_SOURCE = (
    "from __future__ import annotations\n"
    "\n"
    "__all__: list[str] = []\n"
    "\n"
    "\n"
    "class Widget:\n"
    "    pass\n"
    "\n"
    "\n"
    "class Gadget(Widget):\n"
    "    pass\n"
)
_CLEAN_SOURCE = (
    "from __future__ import annotations\n"
    "\n"
    "__all__: list[str] = []\n"
    "\n"
    "\n"
    "def fn() -> int:\n"
    "    return 1\n"
)


def _git(*, cwd: Path, args: list[str]) -> None:
    """Run a `git` subcommand in `cwd` with a hermetic 3-key env.

    The rerouted checks derive their file universe from the git index
    (`config.resolve_check_universe`), so the consumer fixture must be a
    real git working tree. `git` is not a Python spawn, so it is allowed;
    the hardcoded env keeps `COVERAGE_PROCESS_START` out of this child.
    """
    _ = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
        env={"HOME": str(cwd), "GIT_CONFIG_GLOBAL": "/dev/null", "PATH": "/usr/bin:/bin"},
    )


def _write_consumer_fixture(*, root: Path, module_body: str) -> None:
    (root / "pyproject.toml").write_text(_CONSUMER_PYPROJECT, encoding="utf-8")
    src = root / "src"
    src.mkdir()
    (src / "mod.py").write_text(module_body, encoding="utf-8")
    _git(cwd=root, args=["init", "-q"])
    _git(cwd=root, args=["add", "-A"])


def _run_no_inheritance(
    *,
    cwd: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> _CheckRun:
    """Run the shared `no_inheritance` check against the consumer tree at `cwd`.

    A consumer names the check by MODULE NAME, so this resolves it by
    module name too: `importlib.import_module` reaches the same
    package-provided module `python -m
    livespec_dev_tooling.checks.no_inheritance` would, and calls the same
    `main()`. The returned triple carries the same three fields the
    retired `CompletedProcess` did, so the assertions are unchanged —
    including the combined `stdout + stderr` search for the offending
    path.
    """
    module = importlib.import_module(_CHECK_MODULE)
    monkeypatch.chdir(cwd)

    returncode = module.main()

    captured = capsys.readouterr()
    return _CheckRun(returncode=returncode, stdout=captured.out, stderr=captured.err)


def test_self_application_surfaces_injected_regression(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A regression injected into the consumer tree fails the shared check.

    The failure surfaces the offending file so the PR cannot merge until the
    regression is fixed.
    """
    _write_consumer_fixture(root=tmp_path, module_body=_REGRESSED_SOURCE)

    result = _run_no_inheritance(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode != 0, (
        f"self-application should catch the injected regression with a non-zero "
        f"exit; got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert "src/mod.py" in combined, (
        f"the failure diagnostic must surface the offending file `src/mod.py`; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_self_application_passes_clean_tree(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A clean consumer tree passes the shared check (no false positive)."""
    _write_consumer_fixture(root=tmp_path, module_body=_CLEAN_SOURCE)

    result = _run_no_inheritance(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0, (
        f"self-application must not false-positive on a clean tree; got "
        f"returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
