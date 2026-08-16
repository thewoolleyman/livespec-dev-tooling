"""Outside-in test for `livespec_dev_tooling/checks/plan_no_tombstone.py`.

The tombstone ban is structural: a topic must not exist at both
`plan/<topic>/` and `plan/archive/<topic>/`. The check is static,
credential-free, fail-closed, and has no opt-in lever.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import NamedTuple

import pytest

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[3]
_CHECK_PATH = _REPO_ROOT / "livespec_dev_tooling" / "checks" / "plan_no_tombstone.py"


def _load_check_module() -> ModuleType:
    """Import the check module fresh from its file path (the tree the RGR hook inspects)."""
    assert _CHECK_PATH.is_file(), "plan_no_tombstone check module should exist"
    spec = importlib.util.spec_from_file_location("plan_no_tombstone_under_test", _CHECK_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _CheckRun(NamedTuple):
    """In-process stand-in for the subprocess `CompletedProcess` shape."""

    returncode: int
    stdout: str
    stderr: str


def _run_check(
    *, cwd: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> _CheckRun:
    """Invoke the check's `main()` in-process under `cwd`."""
    monkeypatch.chdir(cwd)
    rc = _load_check_module().main()
    captured = capsys.readouterr()
    return _CheckRun(returncode=rc, stdout=captured.out, stderr=captured.err)


def _mkdir(*, root: Path, relative: str) -> None:
    """Create a fixture directory under `root`."""
    (root / relative).mkdir(parents=True, exist_ok=True)


def test_live_and_archived_topic_fails(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A topic present at both live and archived paths fails and names both directories."""
    _mkdir(root=tmp_path, relative="plan/t")
    _mkdir(root=tmp_path, relative="plan/archive/t")
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    combined = result.stdout + result.stderr
    assert result.returncode == 1, f"both-present topic should fail; stderr={result.stderr!r}"
    assert result.stdout == ""
    assert '"level": "error"' in combined
    assert '"disposition": "kept"' in combined
    assert "plan/t" in combined
    assert "plan/archive/t" in combined


def test_live_only_topic_passes(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A topic present only under `plan/<topic>/` stays green."""
    _mkdir(root=tmp_path, relative="plan/t")
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0, f"live-only topic should pass; stderr={result.stderr!r}"


def test_archived_only_topic_passes(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A topic present only under `plan/archive/<topic>/` stays green."""
    _mkdir(root=tmp_path, relative="plan/archive/t")
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0, f"archived-only topic should pass; stderr={result.stderr!r}"


def test_no_plan_dir_passes(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A repo with no `plan/` directory passes trivially."""
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0, f"missing plan/ should pass; stderr={result.stderr!r}"


def test_nested_archive_not_treated_as_live_topic(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The archive container itself is not a live topic named `archive`."""
    _mkdir(root=tmp_path, relative="plan/archive")
    _mkdir(root=tmp_path, relative="plan/archive/archive")
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0, f"archive container should be ignored; stderr={result.stderr!r}"


def test_module_importable_without_running_main() -> None:
    """The check module imports cleanly without invoking main()."""
    module = _load_check_module()
    assert callable(module.main), "main should be importable without invocation"
