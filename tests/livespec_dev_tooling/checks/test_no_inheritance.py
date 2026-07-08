"""Outside-in test for `livespec_dev_tooling/checks/no_inheritance.py` — direct-parent allowlist.

Per `python-skill-script-style-requirements.md` §"Canonical
target list" (the `check-no-inheritance` row), `class X(Y):` is
forbidden when `Y` is not in the direct-parent allowlist
`{Exception, BaseException, LivespecError, Protocol, NamedTuple,
TypedDict}`. Codifies flat-composition direction; `LivespecError`
itself remains an open extension point.

The check now resolves the files it inspects from the git-derived
first-party `.py` universe (`config.resolve_check_universe`),
root-anchored via `config.resolve_repo_root`, rather than a
`config.source_trees` walk. So every test builds a real temp git
working tree and `git add`s its files before invoking `main()`
under a monkeypatched cwd — the same hermetic shape
`tests/livespec_dev_tooling/test_config.py` and `test_file_lloc.py`
use. `git ls-files` reads the index, so files must be `git add`ed
(no commit is needed).

Phase-0 delta-WARN severity: `config.source_trees` is retained as
a severity classifier. A violation in a file UNDER a `source_trees`
tree keeps today's hard gate (`error`-level, exit 1); the identical
violation in a file NEWLY pulled into the git-derived universe
emits at WARN (`warning`-level, `newly_covered` / `phase="0-warn"`,
exit 0) until Phase 2 flips its repo to the hard gate.

The check is driven IN-PROCESS (`monkeypatch.chdir(...)` + `capsys`
+ `rc = main()`) rather than via a `sys.executable` subprocess: no
`COVERAGE_PROCESS_START`-instrumented child, no `.coverage.*` race
under the parallel dispatcher, and materially faster. `main()`
resolves the repo root from the process cwd, so the monkeypatched
cwd anchors the fixture.
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
_NO_INHERITANCE = _REPO_ROOT / "livespec_dev_tooling" / "checks" / "no_inheritance.py"

_BAR_SUBCLASS_SOURCE = (
    "from __future__ import annotations\n"
    "\n"
    "__all__: list[str] = []\n"
    "\n"
    "\n"
    "class Bar:\n"
    "    pass\n"
    "\n"
    "\n"
    "class Foo(Bar):\n"
    "    pass\n"
)
_ALLOWLISTED_SOURCE = (
    "from __future__ import annotations\n"
    "\n"
    "from typing import Protocol\n"
    "\n"
    "__all__: list[str] = []\n"
    "\n"
    "\n"
    "class FooError(Exception):\n"
    "    pass\n"
    "\n"
    "\n"
    "class FooProto(Protocol):\n"
    "    def bar(self) -> None: ...\n"
)


def _load_check_module() -> ModuleType:
    """Import the check module fresh from its file path.

    Loaded by path (not `import livespec_dev_tooling.checks...`) so the
    test exercises the on-disk module the Red→Green hook inspects, and
    so `main()` can be invoked in-process under a monkeypatched cwd.
    """
    spec = importlib.util.spec_from_file_location("no_inheritance_under_test", str(_NO_INHERITANCE))
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
    """Run a `git` subcommand in `cwd` with a hermetic env.

    `git` is not a Python spawn (`tests_no_subprocess_spawn` only forbids
    `sys.executable`/`python`/`python3` argv[0]), so this is allowed in
    `tests/`. The env is a hardcoded 3-key dict (never an `os.environ`
    passthrough), so `COVERAGE_PROCESS_START` / `COV_CORE_*` can never leak
    into the child — the same shape `test_config.py` / `test_file_lloc.py`
    use for the git-derived-universe fixtures.
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


def test_no_inheritance_rejects_disallowed_base_in_legacy_tree(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A disallowed base in a `source_trees` file fails hard (error, exit 1)."""
    _write(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/livespec/foo.py",
        source=_BAR_SUBCLASS_SOURCE,
    )
    _init_repo_with_files(tmp_path=tmp_path)
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert ".claude-plugin/scripts/livespec/foo.py" in combined
    assert '"level": "error"' in combined


def test_no_inheritance_accepts_allowlisted_base_classes(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Classes deriving from `Exception`, `Protocol`, etc. pass silently (exit 0)."""
    _write(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/livespec/foo.py",
        source=_ALLOWLISTED_SOURCE,
    )
    _init_repo_with_files(tmp_path=tmp_path)
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0


def test_no_inheritance_warns_newly_covered_offender(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The identical violation OUTSIDE `source_trees` WARNS (newly-covered) and passes.

    This is the fail-open hole the reroute closes: the old
    `source_trees` walk never saw a file at `pkg/foo.py`, so a repo
    whose package dir is not a `source_trees` tree reported green. The
    git-derived universe now sees it, but Phase-0 severity keeps it at
    WARN (with a `newly_covered` marker, no exit-1 contribution).
    """
    _write(tmp_path=tmp_path, rel_path="pkg/foo.py", source=_BAR_SUBCLASS_SOURCE)
    _init_repo_with_files(tmp_path=tmp_path)
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0
    combined = result.stdout + result.stderr
    assert "pkg/foo.py" in combined
    assert "newly_covered" in combined
    # WARN-not-error: no legacy offender, so no error-level diagnostic.
    assert '"level": "error"' not in combined


def test_no_inheritance_anchors_on_repo_root_from_subdirectory(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Invoked from a SUBDIRECTORY, the check still sees the whole universe.

    The old `Path.cwd()`-anchored walk, invoked from a subdir, would list
    only that subdir's files (an empty/partial universe that silently
    exits 0). Root-anchoring via `resolve_repo_root` closes that hole: the
    legacy-tree violation is found and hard-fails regardless of cwd depth.
    """
    _write(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/livespec/foo.py",
        source=_BAR_SUBCLASS_SOURCE,
    )
    subdir = tmp_path / "pkg" / "nested"
    subdir.mkdir(parents=True)
    _init_repo_with_files(tmp_path=tmp_path)
    result = _run_check(cwd=subdir, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert ".claude-plugin/scripts/livespec/foo.py" in combined


def test_no_inheritance_accepts_codeless_repo(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A genuinely codeless repo (0 first-party `.py`) passes (exit 0, info-level)."""
    _ = (tmp_path / "README.md").write_text("no code here\n", encoding="utf-8")
    _init_repo_with_files(tmp_path=tmp_path)
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0


def test_no_inheritance_module_importable_without_running_main() -> None:
    """The check module imports cleanly without invoking main()."""
    module = _load_check_module()
    assert callable(module.main)
