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
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

__all__: list[str] = []

pytestmark = pytest.mark.consumer

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


def _run_no_inheritance(*, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "livespec_dev_tooling.checks.no_inheritance"],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )


def test_self_application_surfaces_injected_regression(*, tmp_path: Path) -> None:
    """A regression injected into the consumer tree fails the shared check.

    The failure surfaces the offending file so the PR cannot merge until the
    regression is fixed.
    """
    _write_consumer_fixture(root=tmp_path, module_body=_REGRESSED_SOURCE)

    result = _run_no_inheritance(cwd=tmp_path)

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


def test_self_application_passes_clean_tree(*, tmp_path: Path) -> None:
    """A clean consumer tree passes the shared check (no false positive)."""
    _write_consumer_fixture(root=tmp_path, module_body=_CLEAN_SOURCE)

    result = _run_no_inheritance(cwd=tmp_path)

    assert result.returncode == 0, (
        f"self-application must not false-positive on a clean tree; got "
        f"returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
