"""Outside-in test for `livespec_dev_tooling/checks/plan_thread_anchor_declared.py`.

The static half of plan-lifecycle enforcement: every ACTIVE `plan/*/handoff.md`
(excluding `plan/archive/`) must declare a concrete `**Ledger anchor:**` naming a
real epic id. Missing, empty, or placeholder anchors fail; the anchor may sit
mid-line after a `·` separator. Driven in-process (`monkeypatch.chdir(tmp_path)` +
`capsys` + `rc = main()`) per the repo's no-subprocess test convention.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import NamedTuple

import pytest

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[3]
_CHECK_PATH = _REPO_ROOT / "livespec_dev_tooling" / "checks" / "plan_thread_anchor_declared.py"


def _load_check_module() -> ModuleType:
    """Import the check module fresh from its file path (the tree the RGR hook inspects)."""
    spec = importlib.util.spec_from_file_location(
        "plan_thread_anchor_declared_under_test", str(_CHECK_PATH)
    )
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


def _run_check(
    *, cwd: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> _CheckRun:
    """Invoke the check's `main()` in-process under `cwd`."""
    monkeypatch.chdir(cwd)
    rc = _MODULE.main()
    captured = capsys.readouterr()
    return _CheckRun(returncode=rc, stdout=captured.out, stderr=captured.err)


def _write_handoff(*, root: Path, thread: str, body: str) -> Path:
    """Create `<root>/plan/<thread>/handoff.md` with `body`."""
    thread_dir = root / "plan" / thread
    thread_dir.mkdir(parents=True, exist_ok=True)
    handoff = thread_dir / "handoff.md"
    handoff.write_text(body, encoding="utf-8")
    return handoff


def test_concrete_anchor_passes(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A handoff header with a concrete `**Ledger anchor:**` epic id passes (exit 0)."""
    _write_handoff(
        root=tmp_path,
        thread="fleet-plan",
        body="# H\n\n**Ledger anchor:** epic `livespec-dev-tooling-scsj5e`\n",
    )
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0, f"concrete anchor should pass; stderr={result.stderr!r}"


def test_mid_line_anchor_passes(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The anchor may sit mid-line after a `·` separator (as work-item-state-machine's does)."""
    _write_handoff(
        root=tmp_path,
        thread="work-item-state-machine",
        body="# H\n\n**Thread:** x · **Ledger anchor:** epic `livespec-dev-tooling-l2sm` (note)\n",
    )
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0, f"mid-line anchor should pass; stderr={result.stderr!r}"


def test_missing_anchor_fails(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A handoff with no `**Ledger anchor:**` line fails and names the file."""
    _write_handoff(root=tmp_path, thread="no-anchor", body="# H\n\nNo anchor here.\n")
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 1, f"missing anchor should fail; stderr={result.stderr!r}"
    combined = result.stdout + result.stderr
    assert "plan/no-anchor/handoff.md" in combined
    assert '"level": "error"' in combined


def test_angle_placeholder_fails(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An angle-bracket placeholder anchor (`<epic-id>`) fails."""
    _write_handoff(root=tmp_path, thread="ph", body="# H\n\n**Ledger anchor:** epic `<epic-id>`\n")
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 1, f"angle placeholder should fail; stderr={result.stderr!r}"


def test_sentinel_word_placeholder_fails(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A sentinel-word anchor (`TBD`) fails."""
    _write_handoff(root=tmp_path, thread="tbd", body="# H\n\n**Ledger anchor:** epic `TBD`\n")
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 1, f"TBD anchor should fail; stderr={result.stderr!r}"


def test_non_concrete_shape_fails(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A token that is neither placeholder nor a concrete `<tenant>-<id>` shape fails."""
    _write_handoff(
        root=tmp_path, thread="bad-shape", body="# H\n\n**Ledger anchor:** epic `singleword`\n"
    )
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 1, f"non-concrete anchor should fail; stderr={result.stderr!r}"


def test_archived_handoffs_ignored(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Handoffs under `plan/archive/` are ignored — nested and directly under archive."""
    nested = tmp_path / "plan" / "archive" / "old-thread"
    nested.mkdir(parents=True, exist_ok=True)
    (nested / "handoff.md").write_text("# H\n\nNo anchor.\n", encoding="utf-8")
    archive_root = tmp_path / "plan" / "archive"
    (archive_root / "handoff.md").write_text("# H\n\nNo anchor.\n", encoding="utf-8")
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0, f"archived handoffs must be ignored; stderr={result.stderr!r}"


def test_no_plan_dir_passes(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A repo with no `plan/` directory passes trivially (exit 0)."""
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0, f"missing plan/ should exit 0; got {result.returncode}"


def test_module_importable_without_running_main() -> None:
    """The check module imports cleanly without invoking main()."""
    module = _load_check_module()
    assert callable(module.main), "main should be importable without invocation"
