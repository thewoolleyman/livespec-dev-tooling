"""Outside-in test for `livespec_dev_tooling/checks/plan_no_live_handoff_file.py`.

The gate is CHANGE-scoped rather than tree-scoped, so a fixture that merely
lays out directories cannot exercise it: what the check reads is `git diff`,
and the two moments it has to catch — the INDEX at a commit and
`origin/master...HEAD` at a push — are different reads of a real repository.
Every case here therefore builds a throwaway git repo and drives `main()`
in-process against it (`monkeypatch.chdir` + `capsys`, no Python subprocess).

The `git` invocations run with the ambient `GIT_*` environment stripped. Under
the pre-commit hook this suite runs with `GIT_INDEX_FILE` / `GIT_DIR` set, and
those override `cwd` — the fixture commands would silently operate on the REAL
repository instead of the temp one.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
from pathlib import Path
from types import ModuleType
from typing import NamedTuple

import pytest

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[3]
_CHECK_PATH = _REPO_ROOT / "livespec_dev_tooling" / "checks" / "plan_no_live_handoff_file.py"
_LIVE_HANDOFF = "plan/topic/handoff.md"
_LIVE_SUPERVISOR_HANDOFF = "plan/topic/supervisor-handoff.md"


def _load_check_module() -> ModuleType:
    """Import the check module fresh from its file path (the tree the RGR hook inspects)."""
    assert _CHECK_PATH.is_file(), "plan_no_live_handoff_file check module should exist"
    spec = importlib.util.spec_from_file_location("plan_no_live_handoff_under_test", _CHECK_PATH)
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
    module = _load_check_module()
    monkeypatch.chdir(cwd)
    rc = module.main()
    captured = capsys.readouterr()
    return _CheckRun(returncode=rc, stdout=captured.out, stderr=captured.err)


def _git(*, args: list[str], cwd: Path) -> None:
    """Run one fixture git command, with the ambient `GIT_*` environment stripped."""
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    # S603/S607: argv is a fixed list of literal git args plus test-authored
    # paths; no shell, no untrusted input.
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        cwd=str(cwd),
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )


def _write(*, root: Path, relative: str) -> None:
    """Create a fixture file (and its parents) under `root`."""
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text("fixture\n", encoding="utf-8")


def _commit_all(*, root: Path, message: str) -> None:
    """Stage everything in the fixture repo and commit it."""
    _git(args=["add", "-A"], cwd=root)
    _git(args=["commit", "-m", message], cwd=root)


def _repo_without_base(*, root: Path) -> None:
    """A repo with one commit and NO `origin/master` — the unreadable-range shape."""
    _git(args=["init", "--initial-branch=master"], cwd=root)
    _write(root=root, relative="plan/topic/research/001-note.md")
    _commit_all(root=root, message="base")


def _base_repo(*, root: Path) -> None:
    """A repo whose `origin/master` equals HEAD and which holds no handoff file."""
    _repo_without_base(root=root)
    _git(args=["update-ref", "refs/remotes/origin/master", "HEAD"], cwd=root)


def test_staged_live_handoff_fails(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The COMMIT moment: a live handoff staged but not yet committed is refused."""
    _base_repo(root=tmp_path)
    _write(root=tmp_path, relative=_LIVE_HANDOFF)
    _git(args=["add", "-A"], cwd=tmp_path)
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    combined = result.stdout + result.stderr
    assert result.returncode == 1, f"staged handoff should fail; stderr={result.stderr!r}"
    assert result.stdout == ""
    assert '"level": "error"' in combined
    assert _LIVE_HANDOFF in combined


def test_committed_live_handoff_fails_with_ledger_and_skill_guidance(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The PUSH moment: a committed handoff is refused, and the message names the mechanism."""
    _base_repo(root=tmp_path)
    _write(root=tmp_path, relative=_LIVE_SUPERVISOR_HANDOFF)
    _commit_all(root=tmp_path, message="add supervisor handoff")
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    combined = result.stdout + result.stderr
    assert result.returncode == 1, f"committed handoff should fail; stderr={result.stderr!r}"
    assert _LIVE_SUPERVISOR_HANDOFF in combined
    assert "ledger" in combined
    assert "livespec-orchestrator-beads-fabro:plan" in combined
    assert "supervise-plan" in combined
    assert "Contract + reference implementations architecture" in combined


def test_modifying_an_existing_live_handoff_fails(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An already-committed live handoff is FROZEN: editing it is refused too."""
    _repo_without_base(root=tmp_path)
    _write(root=tmp_path, relative=_LIVE_HANDOFF)
    _commit_all(root=tmp_path, message="pre-existing handoff")
    _git(args=["update-ref", "refs/remotes/origin/master", "HEAD"], cwd=tmp_path)
    _ = (tmp_path / _LIVE_HANDOFF).write_text("edited\n", encoding="utf-8")
    _commit_all(root=tmp_path, message="edit handoff")
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 1, f"edited handoff should fail; stderr={result.stderr!r}"
    assert _LIVE_HANDOFF in result.stderr


def test_deleting_a_live_handoff_passes(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Migration must stay possible: removing a live handoff is not a violation."""
    _repo_without_base(root=tmp_path)
    _write(root=tmp_path, relative=_LIVE_HANDOFF)
    _commit_all(root=tmp_path, message="pre-existing handoff")
    _git(args=["update-ref", "refs/remotes/origin/master", "HEAD"], cwd=tmp_path)
    _git(args=["rm", "--quiet", _LIVE_HANDOFF], cwd=tmp_path)
    _commit_all(root=tmp_path, message="retire the handoff file")
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0, f"deletion should pass; stderr={result.stderr!r}"


def test_root_and_nested_plan_handoffs_are_both_refused(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Every non-sanctioned location under `plan/` is the live carrier, nesting included."""
    _base_repo(root=tmp_path)
    _write(root=tmp_path, relative="plan/handoff.md")
    _write(root=tmp_path, relative="plan/topic/nested/supervisor-handoff.md")
    _commit_all(root=tmp_path, message="handoffs in odd places")
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 1, f"odd-location handoffs should fail; stderr={result.stderr!r}"
    assert "plan/handoff.md" in result.stderr
    assert "plan/topic/nested/supervisor-handoff.md" in result.stderr


def test_sanctioned_and_unrelated_paths_pass(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Archive, research, non-handoff and non-plan paths are all unaffected."""
    _base_repo(root=tmp_path)
    for relative in (
        "handoff.md",
        "docs/handoff.md",
        "plan/topic/notes.md",
        "plan/archive/topic/handoff.md",
        "plan/archive/topic/supervisor-handoff.md",
        "plan/topic/research/handoff.md",
    ):
        _write(root=tmp_path, relative=relative)
    _commit_all(root=tmp_path, message="sanctioned evidence locations")
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0, f"sanctioned locations should pass; stderr={result.stderr!r}"


def test_unreadable_staged_diff_fails_rather_than_passing(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A directory that is not a git repo yields no changed set — and must not pass."""
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    combined = result.stdout + result.stderr
    assert result.returncode == 1, f"unreadable staged diff should fail; stderr={result.stderr!r}"
    assert '"level": "error"' in combined
    assert "diff-failed" in combined


def test_unresolvable_range_base_fails_rather_than_passing(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A readable index with an absent `origin/master` is an UNKNOWN changed set, not an empty one."""
    _repo_without_base(root=tmp_path)
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    combined = result.stdout + result.stderr
    assert result.returncode == 1, f"absent origin/master should fail; stderr={result.stderr!r}"
    assert "origin/master...HEAD" in combined


def test_module_importable_without_running_main() -> None:
    """The check module imports cleanly without invoking main()."""
    module = _load_check_module()
    assert callable(module.main), "main should be importable without invocation"
