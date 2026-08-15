"""Outside-in test for retired `handoff_dispatch_routing`.

Ratified Planning Lane v197 makes handoff entries ledger-held. The old active
git-handoff routing scanner remains as a stable slug in this slice, but no
longer enforces routing from `plan/*/handoff.md`.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import NamedTuple

import pytest

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[3]
_CHECK_PATH = _REPO_ROOT / "livespec_dev_tooling" / "checks" / "handoff_dispatch_routing.py"


def _load_check_module() -> ModuleType:
    """Import the check module fresh from its file path."""
    spec = importlib.util.spec_from_file_location(
        "handoff_dispatch_routing_under_test", str(_CHECK_PATH)
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


def test_retired_git_handoff_routing_scanner_noops_with_reason(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A legacy git handoff naming `:implement` no longer fails this retired scanner."""
    handoff = tmp_path / "plan" / "legacy" / "handoff.md"
    _ = handoff.parent.mkdir(parents=True)
    _ = handoff.write_text(
        "Next: run `livespec-orchestrator-beads-fabro:implement x`.\n", encoding="utf-8"
    )

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0
    assert result.stdout == ""
    assert '"disposition": "retired"' in result.stderr
    assert "ledger-held handoff timeline" in result.stderr


def test_module_importable_without_running_main() -> None:
    """The check module imports cleanly without invoking main()."""
    module = _load_check_module()
    assert callable(module.main), "main should be importable without invocation"
