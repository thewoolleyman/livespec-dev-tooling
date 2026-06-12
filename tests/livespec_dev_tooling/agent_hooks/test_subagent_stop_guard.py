"""Tests for `livespec_dev_tooling/agent_hooks/subagent_stop_guard.py`.

Per work-item livespec-dev-tooling-7us.2, the SubagentStop guard
blocks a sub-agent's turn-end (exit 2) while derived in-flight
markers exist in a worktree that sub-agent created, and fails open
(exit 0) on every error path.

Covered behaviors:

- worktree-path extraction from transcript text (both `worktrees/`
  and `.claude/worktrees/` layouts; dedupe; no false matches);
- marker derivation against REAL tmp_path git repos (uncommitted
  tracked changes, unpushed commits, ahead-of-canonical gating) and
  against a fake `gh` stub on PATH (unarmed-PR / no-PR detection,
  fail-open on every other `gh` outcome);
- the pure block/allow decision (`_decide`) including the
  per-session anti-wedge block cap;
- the end-to-end hook protocol via in-process `main()` calls
  (stdin JSON in, exit code out) plus one subprocess invocation of
  the script exactly as the Claude Code hook runs it.

Private names are imported via from-imports (the package-private
access model, mirroring `tests/livespec_dev_tooling/fleet/`);
monkeypatch seams use the string-target form so collaborator
functions are patched on the module the callers resolve against.
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from livespec_dev_tooling.agent_hooks.subagent_stop_guard import (
    _MAX_BLOCKS_PER_SESSION,
    _MAX_WORKTREES,
    _STATE_DIR_ENV,
    _commits_ahead_of_canonical,
    _decide,
    _derive_markers,
    _extract_worktree_paths,
    _gather_worktrees,
    _git_count,
    _has_uncommitted_tracked_changes,
    _load_hook_input,
    _read_block_count,
    _record_block,
    _state_path,
    _unarmed_pr_marker,
    _unpushed_commit_count,
    _worktree_marker,
    main,
)

__all__: list[str] = []


_MODULE = "livespec_dev_tooling.agent_hooks.subagent_stop_guard"
_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPT = _REPO_ROOT / "livespec_dev_tooling" / "agent_hooks" / "subagent_stop_guard.py"

# Vars git sets when invoking hooks (lefthook pre-commit / pre-push /
# commit-msg). The guard's internal `git -C <worktree>` probes inherit
# the test process env; under a hook, GIT_DIR / GIT_INDEX_FILE would
# redirect those probes at the SURROUNDING repo instead of the
# tmp_path mini-repo. Mirrors the discipline in
# `test_no_stale_revise_branches.py`.
_GIT_ENV_PASSTHROUGH_VARS: tuple[str, ...] = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_COMMON_DIR",
    "GIT_NAMESPACE",
    "GIT_LITERAL_PATHSPECS",
    "GIT_PREFIX",
)


@pytest.fixture(autouse=True)
def _scrub_git_hook_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in _GIT_ENV_PASSTHROUGH_VARS:
        monkeypatch.delenv(var, raising=False)


def _git(*, cwd: Path, args: list[str]) -> None:
    _ = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
        env={
            "HOME": str(cwd),
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_SYSTEM": "/dev/null",
            "PATH": "/usr/bin:/bin",
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@example.com",
        },
    )


def _make_pushed_repo(*, tmp_path: Path) -> Path:
    """A `worktrees/<slug>`-shaped repo, branch `work`, fully pushed to origin.

    `origin/master` points at the same commit as `work`, so the repo
    starts with zero unpushed commits and zero commits ahead of the
    canonical branch.
    """
    remote = tmp_path / "remote.git"
    remote.mkdir(parents=True)
    _git(cwd=remote, args=["init", "--bare", "--quiet"])
    worktree = tmp_path / "worktrees" / "wt"
    worktree.mkdir(parents=True)
    _git(cwd=worktree, args=["init", "--quiet", "-b", "work"])
    _ = (worktree / "tracked.txt").write_text("v1\n", encoding="utf-8")
    _git(cwd=worktree, args=["add", "tracked.txt"])
    _git(cwd=worktree, args=["commit", "--quiet", "-m", "seed"])
    _git(cwd=worktree, args=["remote", "add", "origin", str(remote)])
    _git(cwd=worktree, args=["push", "--quiet", "origin", "work:master", "work:work"])
    _git(cwd=worktree, args=["fetch", "--quiet", "origin"])
    return worktree


def _add_unpushed_commit(*, worktree: Path) -> None:
    _ = (worktree / "tracked.txt").write_text("v2\n", encoding="utf-8")
    _git(cwd=worktree, args=["add", "tracked.txt"])
    _git(cwd=worktree, args=["commit", "--quiet", "-m", "more work"])


def _push_branch(*, worktree: Path) -> None:
    _git(cwd=worktree, args=["push", "--quiet", "origin", "work:work"])
    _git(cwd=worktree, args=["fetch", "--quiet", "origin"])


def _install_fake_gh(
    *,
    tmp_path: Path,
    stdout: str = "",
    stderr: str = "",
    returncode: int = 0,
) -> str:
    """Install a fake `gh` at tmp_path/bin/gh; return a PATH using it."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    gh_stub = bin_dir / "gh"
    script = (
        "#!/bin/sh\n"
        f"printf '%s' '{stdout}'\n"
        f"printf '%s' '{stderr}' >&2\n"
        f"exit {returncode}\n"
    )
    _ = gh_stub.write_text(script, encoding="utf-8")
    gh_stub.chmod(0o755)
    return f"{bin_dir}:/usr/bin:/bin"


# ---------------------------------------------------------------------------
# _extract_worktree_paths
# ---------------------------------------------------------------------------


def test_extract_worktree_paths_matches_both_layouts_and_dedupes() -> None:
    text = (
        "cd /data/projects/x/worktrees/slug-1 && ls\n"
        '"/data/projects/y/.claude/worktrees/s2"\n'
        "again /data/projects/x/worktrees/slug-1/deeper/file.py\n"
        "no worktree mention here\n"
    )
    paths = _extract_worktree_paths(transcript_text=text)
    assert paths == [
        Path("/data/projects/x/worktrees/slug-1"),
        Path("/data/projects/y/.claude/worktrees/s2"),
    ]


def test_extract_worktree_paths_empty_on_plain_text() -> None:
    assert _extract_worktree_paths(transcript_text="nothing relevant") == []


# ---------------------------------------------------------------------------
# git-derived markers against real tmp repos
# ---------------------------------------------------------------------------


def test_uncommitted_tracked_changes_false_on_clean_repo(tmp_path: Path) -> None:
    worktree = _make_pushed_repo(tmp_path=tmp_path)
    assert _has_uncommitted_tracked_changes(worktree=worktree) is False


def test_uncommitted_tracked_changes_true_on_modified_tracked_file(tmp_path: Path) -> None:
    worktree = _make_pushed_repo(tmp_path=tmp_path)
    _ = (worktree / "tracked.txt").write_text("dirty\n", encoding="utf-8")
    assert _has_uncommitted_tracked_changes(worktree=worktree) is True


def test_uncommitted_tracked_changes_ignores_untracked_files(tmp_path: Path) -> None:
    worktree = _make_pushed_repo(tmp_path=tmp_path)
    _ = (worktree / "scratch.txt").write_text("untracked\n", encoding="utf-8")
    assert _has_uncommitted_tracked_changes(worktree=worktree) is False


def test_uncommitted_tracked_changes_none_on_non_repo(tmp_path: Path) -> None:
    assert _has_uncommitted_tracked_changes(worktree=tmp_path) is None


def test_unpushed_commit_count_zero_when_fully_pushed(tmp_path: Path) -> None:
    worktree = _make_pushed_repo(tmp_path=tmp_path)
    assert _unpushed_commit_count(worktree=worktree) == 0


def test_unpushed_commit_count_counts_local_only_commits(tmp_path: Path) -> None:
    worktree = _make_pushed_repo(tmp_path=tmp_path)
    _add_unpushed_commit(worktree=worktree)
    assert _unpushed_commit_count(worktree=worktree) == 1


def test_unpushed_commit_count_none_on_non_repo(tmp_path: Path) -> None:
    assert _unpushed_commit_count(worktree=tmp_path) is None


def test_git_count_none_on_non_numeric_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    git_stub = bin_dir / "git"
    _ = git_stub.write_text("#!/bin/sh\necho not-a-number\nexit 0\n", encoding="utf-8")
    git_stub.chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir))
    assert _git_count(worktree=tmp_path, args=["rev-list", "--count", "HEAD"]) is None


def test_commits_ahead_of_canonical_zero_at_origin_master(tmp_path: Path) -> None:
    worktree = _make_pushed_repo(tmp_path=tmp_path)
    assert _commits_ahead_of_canonical(worktree=worktree) == 0


def test_commits_ahead_of_canonical_counts_branch_work(tmp_path: Path) -> None:
    worktree = _make_pushed_repo(tmp_path=tmp_path)
    _add_unpushed_commit(worktree=worktree)
    _push_branch(worktree=worktree)
    assert _commits_ahead_of_canonical(worktree=worktree) == 1


def test_commits_ahead_of_canonical_none_on_non_repo(tmp_path: Path) -> None:
    assert _commits_ahead_of_canonical(worktree=tmp_path) is None


# ---------------------------------------------------------------------------
# _unarmed_pr_marker (fake `gh` stub on PATH)
# ---------------------------------------------------------------------------


def test_unarmed_pr_marker_flags_pushed_branch_without_pr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _install_fake_gh(
        tmp_path=tmp_path,
        stderr="no pull requests found for branch work",
        returncode=1,
    )
    monkeypatch.setenv("PATH", path)
    marker = _unarmed_pr_marker(worktree=tmp_path)
    assert marker is not None
    assert "NO PR" in marker


def test_unarmed_pr_marker_fails_open_on_other_gh_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _install_fake_gh(tmp_path=tmp_path, stderr="HTTP 502 bad gateway", returncode=1)
    monkeypatch.setenv("PATH", path)
    assert _unarmed_pr_marker(worktree=tmp_path) is None


def test_unarmed_pr_marker_fails_open_on_invalid_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _install_fake_gh(tmp_path=tmp_path, stdout="not json")
    monkeypatch.setenv("PATH", path)
    assert _unarmed_pr_marker(worktree=tmp_path) is None


def test_unarmed_pr_marker_fails_open_on_non_dict_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _install_fake_gh(tmp_path=tmp_path, stdout="[1, 2]")
    monkeypatch.setenv("PATH", path)
    assert _unarmed_pr_marker(worktree=tmp_path) is None


def test_unarmed_pr_marker_allows_merged_pr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _install_fake_gh(
        tmp_path=tmp_path,
        stdout='{"state": "MERGED", "autoMergeRequest": null}',
    )
    monkeypatch.setenv("PATH", path)
    assert _unarmed_pr_marker(worktree=tmp_path) is None


def test_unarmed_pr_marker_flags_open_pr_without_auto_merge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _install_fake_gh(
        tmp_path=tmp_path,
        stdout='{"state": "OPEN", "autoMergeRequest": null}',
    )
    monkeypatch.setenv("PATH", path)
    marker = _unarmed_pr_marker(worktree=tmp_path)
    assert marker is not None
    assert "auto-merge" in marker


def test_unarmed_pr_marker_allows_armed_pr(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = _install_fake_gh(
        tmp_path=tmp_path,
        stdout='{"state": "OPEN", "autoMergeRequest": {"enabledAt": "2026-06-12T00:00:00Z"}}',
    )
    monkeypatch.setenv("PATH", path)
    assert _unarmed_pr_marker(worktree=tmp_path) is None


def test_unarmed_pr_marker_fails_open_when_gh_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()
    monkeypatch.setenv("PATH", str(empty_bin))
    assert _unarmed_pr_marker(worktree=tmp_path) is None


# ---------------------------------------------------------------------------
# _worktree_marker composition (probe seams monkeypatched on the module)
# ---------------------------------------------------------------------------


def _patch_probes(
    monkeypatch: pytest.MonkeyPatch,
    *,
    dirty: bool | None,
    unpushed: int | None,
    ahead: int | None,
    pr_marker: str | None,
) -> None:
    def fake_dirty(*, worktree: Path) -> bool | None:
        _ = worktree
        return dirty

    def fake_unpushed(*, worktree: Path) -> int | None:
        _ = worktree
        return unpushed

    def fake_ahead(*, worktree: Path) -> int | None:
        _ = worktree
        return ahead

    def fake_pr(*, worktree: Path) -> str | None:
        _ = worktree
        return pr_marker

    monkeypatch.setattr(f"{_MODULE}._has_uncommitted_tracked_changes", fake_dirty)
    monkeypatch.setattr(f"{_MODULE}._unpushed_commit_count", fake_unpushed)
    monkeypatch.setattr(f"{_MODULE}._commits_ahead_of_canonical", fake_ahead)
    monkeypatch.setattr(f"{_MODULE}._unarmed_pr_marker", fake_pr)


def test_worktree_marker_reports_dirty_first(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_probes(monkeypatch, dirty=True, unpushed=5, ahead=5, pr_marker="ignored")
    marker = _worktree_marker(worktree=Path("/wt"))
    assert marker == "/wt: uncommitted tracked changes"


def test_worktree_marker_reports_unpushed_commits(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_probes(monkeypatch, dirty=False, unpushed=2, ahead=2, pr_marker="ignored")
    marker = _worktree_marker(worktree=Path("/wt"))
    assert marker == "/wt: 2 unpushed commit(s)"


def test_worktree_marker_reports_pr_state_when_pushed_and_ahead(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_probes(monkeypatch, dirty=False, unpushed=0, ahead=1, pr_marker="PR not armed")
    marker = _worktree_marker(worktree=Path("/wt"))
    assert marker == "/wt: PR not armed"


def test_worktree_marker_none_when_pr_is_armed_or_done(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_probes(monkeypatch, dirty=False, unpushed=0, ahead=1, pr_marker=None)
    assert _worktree_marker(worktree=Path("/wt")) is None


def test_worktree_marker_skips_pr_probe_at_zero_ahead(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # pr_marker is a non-None sentinel: if the PR probe ran at zero
    # ahead-count, _worktree_marker would surface "/wt: must-not-surface"
    # instead of None.
    _patch_probes(monkeypatch, dirty=False, unpushed=0, ahead=0, pr_marker="must-not-surface")
    assert _worktree_marker(worktree=Path("/wt")) is None


@pytest.mark.parametrize(
    ("dirty", "unpushed", "ahead"),
    [(None, 0, 1), (False, None, 1), (False, 0, None)],
)
def test_worktree_marker_fails_open_when_any_probe_breaks(
    monkeypatch: pytest.MonkeyPatch,
    dirty: bool | None,
    unpushed: int | None,
    ahead: int | None,
) -> None:
    _patch_probes(monkeypatch, dirty=dirty, unpushed=unpushed, ahead=ahead, pr_marker="ignored")
    assert _worktree_marker(worktree=Path("/wt")) is None


def test_derive_markers_collects_and_caps(monkeypatch: pytest.MonkeyPatch) -> None:
    probed: list[Path] = []

    def fake_marker(*, worktree: Path) -> str | None:
        probed.append(worktree)
        return f"{worktree}: marked" if worktree.name == "wt0" else None

    monkeypatch.setattr(f"{_MODULE}._worktree_marker", fake_marker)
    worktrees = [Path(f"/x/worktrees/wt{i}") for i in range(12)]
    markers = _derive_markers(worktrees=worktrees)
    assert markers == ["/x/worktrees/wt0: marked"]
    assert len(probed) == _MAX_WORKTREES


# ---------------------------------------------------------------------------
# pure decision + block-count state
# ---------------------------------------------------------------------------


def test_decide_allows_without_markers() -> None:
    assert _decide(markers=[], block_count=0) is False


def test_decide_blocks_with_markers_under_cap() -> None:
    assert _decide(markers=["m"], block_count=0) is True
    assert _decide(markers=["m"], block_count=_MAX_BLOCKS_PER_SESSION - 1) is True


def test_decide_fails_open_at_cap() -> None:
    assert _decide(markers=["m"], block_count=_MAX_BLOCKS_PER_SESSION) is False


def test_state_path_uses_env_override_and_sanitizes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(_STATE_DIR_ENV, str(tmp_path))
    path = _state_path(session_id="ab/cd:ef")
    assert path.parent == tmp_path
    assert path.name == "livespec-subagent-stop-guard-ab_cd_ef.blocks"


def test_state_path_defaults_to_tempdir_and_unknown_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(_STATE_DIR_ENV, raising=False)
    path = _state_path(session_id="")
    assert path.name == "livespec-subagent-stop-guard-unknown.blocks"


def test_read_block_count_zero_on_missing_or_garbage(tmp_path: Path) -> None:
    assert _read_block_count(path=tmp_path / "absent") == 0
    garbage = tmp_path / "garbage"
    _ = garbage.write_text("not a number\n", encoding="utf-8")
    assert _read_block_count(path=garbage) == 0


def test_record_block_round_trips_and_suppresses_write_errors(tmp_path: Path) -> None:
    state = tmp_path / "state.blocks"
    _record_block(path=state, count=2)
    assert _read_block_count(path=state) == 2
    _record_block(path=tmp_path / "missing-dir" / "state.blocks", count=1)


# ---------------------------------------------------------------------------
# hook-input parsing + worktree gathering
# ---------------------------------------------------------------------------


def test_load_hook_input_rejects_bad_json_and_non_dict() -> None:
    assert _load_hook_input(raw="{nope") is None
    assert _load_hook_input(raw="[1, 2]") is None
    assert _load_hook_input(raw='{"a": 1}') == {"a": 1}


def test_gather_worktrees_empty_without_usable_transcript(tmp_path: Path) -> None:
    assert _gather_worktrees(hook_input={}) == []
    assert _gather_worktrees(hook_input={"transcript_path": 7}) == []
    missing = tmp_path / "missing.jsonl"
    assert _gather_worktrees(hook_input={"transcript_path": str(missing)}) == []


def test_gather_worktrees_keeps_only_existing_git_worktrees(tmp_path: Path) -> None:
    real = _make_pushed_repo(tmp_path=tmp_path)
    phantom = tmp_path / "worktrees" / "phantom"
    transcript = tmp_path / "transcript.jsonl"
    _ = transcript.write_text(f'{{"text": "{real} and {phantom}"}}\n', encoding="utf-8")
    gathered = _gather_worktrees(hook_input={"transcript_path": str(transcript)})
    assert gathered == [real]


# ---------------------------------------------------------------------------
# main() — in-process hook-protocol behavior
# ---------------------------------------------------------------------------


def _run_main(*, monkeypatch: pytest.MonkeyPatch, stdin_text: str) -> int:
    monkeypatch.setattr(sys, "stdin", io.StringIO(stdin_text))
    return main()


def test_main_fails_open_on_unparseable_stdin(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _run_main(monkeypatch=monkeypatch, stdin_text="{nope") == 0


def test_main_allows_when_no_worktrees_in_transcript(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    transcript = tmp_path / "transcript.jsonl"
    _ = transcript.write_text('{"text": "no worktree mention"}\n', encoding="utf-8")
    payload = json.dumps({"session_id": "s1", "transcript_path": str(transcript)})
    assert _run_main(monkeypatch=monkeypatch, stdin_text=payload) == 0


def test_main_allows_when_worktree_is_handed_off(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    worktree = _make_pushed_repo(tmp_path=tmp_path)
    transcript = tmp_path / "transcript.jsonl"
    _ = transcript.write_text(f'{{"text": "working in {worktree}"}}\n', encoding="utf-8")
    payload = json.dumps({"session_id": "s2", "transcript_path": str(transcript)})
    assert _run_main(monkeypatch=monkeypatch, stdin_text=payload) == 0


def test_main_blocks_on_unpushed_commits_and_counts_blocks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    monkeypatch.setenv(_STATE_DIR_ENV, str(state_dir))
    worktree = _make_pushed_repo(tmp_path=tmp_path)
    _add_unpushed_commit(worktree=worktree)
    transcript = tmp_path / "transcript.jsonl"
    _ = transcript.write_text(f'{{"text": "working in {worktree}"}}\n', encoding="utf-8")
    payload = json.dumps({"session_id": "s3", "transcript_path": str(transcript)})
    assert _run_main(monkeypatch=monkeypatch, stdin_text=payload) == 2
    assert _read_block_count(path=_state_path(session_id="s3")) == 1


def test_main_fails_open_past_the_block_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    monkeypatch.setenv(_STATE_DIR_ENV, str(state_dir))
    worktree = _make_pushed_repo(tmp_path=tmp_path)
    _add_unpushed_commit(worktree=worktree)
    transcript = tmp_path / "transcript.jsonl"
    _ = transcript.write_text(f'{{"text": "working in {worktree}"}}\n', encoding="utf-8")
    _record_block(path=_state_path(session_id="s4"), count=_MAX_BLOCKS_PER_SESSION)
    payload = json.dumps({"session_id": "s4", "transcript_path": str(transcript)})
    assert _run_main(monkeypatch=monkeypatch, stdin_text=payload) == 0


def test_main_fails_open_on_internal_crash(monkeypatch: pytest.MonkeyPatch) -> None:
    def exploding_gather(*, hook_input: dict[str, object]) -> list[Path]:
        _ = hook_input
        raise RuntimeError("boom")

    monkeypatch.setattr(f"{_MODULE}._gather_worktrees", exploding_gather)
    assert _run_main(monkeypatch=monkeypatch, stdin_text='{"session_id": "s5"}') == 0


# ---------------------------------------------------------------------------
# subprocess end-to-end — exactly as the Claude Code hook invokes it
# ---------------------------------------------------------------------------


def test_script_blocks_then_allows_end_to_end(tmp_path: Path) -> None:
    worktree = _make_pushed_repo(tmp_path=tmp_path)
    _add_unpushed_commit(worktree=worktree)
    transcript = tmp_path / "transcript.jsonl"
    _ = transcript.write_text(f'{{"text": "working in {worktree}"}}\n', encoding="utf-8")
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    payload = json.dumps({"session_id": "e2e", "transcript_path": str(transcript)})
    env = {k: v for k, v in os.environ.items() if k not in _GIT_ENV_PASSTHROUGH_VARS}
    env[_STATE_DIR_ENV] = str(state_dir)

    blocked = subprocess.run(
        [sys.executable, str(_SCRIPT)],
        input=payload,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert blocked.returncode == 2
    assert "BLOCKING turn-end" in blocked.stderr
    assert "unpushed commit" in blocked.stderr

    _push_branch(worktree=worktree)
    env["PATH"] = _install_fake_gh(
        tmp_path=tmp_path,
        stdout='{"state": "OPEN", "autoMergeRequest": {"enabledAt": "2026-06-12T00:00:00Z"}}',
    )
    allowed = subprocess.run(
        [sys.executable, str(_SCRIPT)],
        input=payload,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert allowed.returncode == 0
