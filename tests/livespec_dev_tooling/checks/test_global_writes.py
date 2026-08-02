"""Outside-in test for `livespec_dev_tooling/checks/global_writes.py` — no module-level mutable writes.

Per `python-skill-script-style-requirements.md` section "Canonical
target list" (the `check-global-writes` row), no module-level
mutable state writes from functions are permitted in
`livespec/**`. The `global` keyword (writing module state from a
function body) and `nonlocal` keyword (writing enclosing-scope
state from a nested function) are both banned.

The check now resolves the files it inspects from the git-derived
first-party `.py` universe (`config.resolve_check_universe`),
root-anchored via `config.resolve_repo_root`, rather than a
`config.source_trees` walk — so every test builds a real temp git
working tree and `git add`s its files before invoking `main()`
under a monkeypatched cwd (the same hermetic shape `test_config.py`
and `test_file_lloc.py` use). Phase-0 delta-WARN severity:
`config.source_trees` is retained as a severity classifier — a
`global`/`nonlocal` in a `source_trees` file keeps today's hard
gate (`error`, exit 1); the identical violation in a NEWLY-covered
file emits at WARN (`newly_covered` / `phase="0-warn"`, exit 0).

Driven IN-PROCESS (`monkeypatch.chdir(...)` + `capsys` + `rc =
main()`): no `COVERAGE_PROCESS_START`-instrumented child, no
`.coverage.*` race under the parallel dispatcher, materially
faster.
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path
from types import ModuleType
from typing import NamedTuple

import pytest

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[3]
_GLOBAL_WRITES = _REPO_ROOT / "livespec_dev_tooling" / "checks" / "global_writes.py"

_GLOBAL_SOURCE = (
    "from __future__ import annotations\n"
    "\n"
    "__all__: list[str] = []\n"
    "\n"
    "x = 0\n"
    "\n"
    "\n"
    "def fn() -> None:\n"
    "    global x\n"
    "    x = 1\n"
)
_NONLOCAL_SOURCE = (
    "from __future__ import annotations\n"
    "\n"
    "__all__: list[str] = []\n"
    "\n"
    "\n"
    "def outer() -> None:\n"
    "    x = 0\n"
    "    def inner() -> None:\n"
    "        nonlocal x\n"
    "        x = 1\n"
    "    inner()\n"
)
_CLEAN_SOURCE = (
    "from __future__ import annotations\n"
    "\n"
    "__all__: list[str] = []\n"
    "\n"
    "X = 0\n"
    "\n"
    "\n"
    "def fn() -> int:\n"
    "    return X + 1\n"
)


def _load_check_module() -> ModuleType:
    """Import the check module fresh from its file path.

    Loaded by path (not `import livespec_dev_tooling.checks...`) so the
    test exercises the on-disk module the Red→Green hook inspects, and
    so `main()` can be invoked in-process under a monkeypatched cwd.
    """
    spec = importlib.util.spec_from_file_location("global_writes_under_test", str(_GLOBAL_WRITES))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_MODULE = _load_check_module()


class _CheckRun(NamedTuple):
    """In-process stand-in for the subprocess `CompletedProcess` shape."""

    returncode: int
    stdout: str
    stderr: str


def _git(*, cwd: Path, args: list[str]) -> None:
    """Run a `git` subcommand in `cwd` with a hermetic 3-key env.

    `git` is not a Python spawn, so it is allowed in `tests/`; the
    hardcoded env keeps `COVERAGE_PROCESS_START` / `COV_CORE_*` out of
    the child — the shape `test_config.py` / `test_file_lloc.py` use.
    """
    _ = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
        env={"HOME": str(cwd), "GIT_CONFIG_GLOBAL": "/dev/null", "PATH": "/usr/bin:/bin"},
    )


def _init_repo_with_files(*, tmp_path: Path) -> None:
    """`git init` the fixture and stage every file already written under it."""
    _git(cwd=tmp_path, args=["init", "-q"])
    _git(cwd=tmp_path, args=["add", "-A"])


def _write(*, tmp_path: Path, rel_path: str, source: str) -> None:
    full = tmp_path / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    _ = full.write_text(source, encoding="utf-8")


def _run_check(
    *, cwd: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> _CheckRun:
    """Invoke the check's `main()` in-process under `cwd` and capture output."""
    monkeypatch.chdir(cwd)
    rc = _MODULE.main()
    captured = capsys.readouterr()
    return _CheckRun(returncode=rc, stdout=captured.out, stderr=captured.err)


def test_global_writes_rejects_global_statement_in_legacy_tree(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `global x` in a `source_trees` file fails hard (error, exit 1)."""
    _write(
        tmp_path=tmp_path, rel_path=".claude-plugin/scripts/livespec/foo.py", source=_GLOBAL_SOURCE
    )
    _init_repo_with_files(tmp_path=tmp_path)
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert ".claude-plugin/scripts/livespec/foo.py" in combined
    assert '"level": "error"' in combined


def test_global_writes_rejects_nonlocal_statement_in_legacy_tree(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `nonlocal x` in a nested function in a `source_trees` file fails (exit 1)."""
    _write(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/livespec/foo.py",
        source=_NONLOCAL_SOURCE,
    )
    _init_repo_with_files(tmp_path=tmp_path)
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode != 0


def test_global_writes_accepts_clean_module(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A module with no `global`/`nonlocal` passes (exit 0)."""
    _write(
        tmp_path=tmp_path, rel_path=".claude-plugin/scripts/livespec/foo.py", source=_CLEAN_SOURCE
    )
    _init_repo_with_files(tmp_path=tmp_path)
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0


def test_global_writes_warns_newly_covered_offender(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `global x` OUTSIDE `source_trees` WARNS (newly-covered) and passes (exit 0)."""
    _write(tmp_path=tmp_path, rel_path="pkg/foo.py", source=_GLOBAL_SOURCE)
    _init_repo_with_files(tmp_path=tmp_path)
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0
    combined = result.stdout + result.stderr
    assert "pkg/foo.py" in combined
    assert "newly_covered" in combined
    assert '"level": "error"' not in combined


def test_global_writes_accepts_codeless_repo(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A genuinely codeless repo (0 first-party `.py`) passes (exit 0, info-level)."""
    _ = (tmp_path / "README.md").write_text("no code\n", encoding="utf-8")
    _init_repo_with_files(tmp_path=tmp_path)
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0


def test_global_writes_module_importable_without_running_main() -> None:
    """The check module imports cleanly without invoking main()."""
    module = _load_check_module()
    assert callable(module.main), "main should be importable without invocation"
