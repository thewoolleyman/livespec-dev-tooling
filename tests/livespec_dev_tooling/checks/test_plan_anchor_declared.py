"""Outside-in test for retired `plan_anchor_declared`.

Ratified Planning Lane v197 moved handoffs and the plan epic anchor out of git
files. The old check module remains present for slug stability in this slice,
but its old filesystem-anchor invariant is retired rather than re-scoped.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import NamedTuple

import pytest

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[3]
_CHECK_PATH = _REPO_ROOT / "livespec_dev_tooling" / "checks" / "plan_anchor_declared.py"


def _load_check_module() -> ModuleType:
    """Import the check module fresh from its file path."""
    spec = importlib.util.spec_from_file_location(
        "plan_anchor_declared_under_test", str(_CHECK_PATH)
    )
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


def test_retired_filesystem_anchor_invariant_noops_with_reason(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A legacy active handoff without a git anchor no longer fails this retired check."""
    handoff = tmp_path / "plan" / "legacy" / "handoff.md"
    _ = handoff.parent.mkdir(parents=True)
    _ = handoff.write_text("# Legacy handoff\n\nNo filesystem anchor here.\n", encoding="utf-8")

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0
    assert result.stdout == ""
    assert '"disposition": "retired"' in result.stderr
    assert "ledger-held plan epic metadata" in result.stderr


def test_module_importable_without_running_main() -> None:
    """The check module imports cleanly without invoking main()."""
    module = _load_check_module()
    assert callable(module.main), "main should be importable without invocation"
