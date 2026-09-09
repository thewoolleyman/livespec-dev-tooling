"""Tests for `livespec_dev_tooling/agent_hooks/subagent_stop_guard.py`.

Per work-item livespec-dev-tooling-7us.2, the SubagentStop guard
blocks a sub-agent's turn-end while derived in-flight markers exist
in a worktree that sub-agent created, and fails open on every error
path.

⛔ THE VERDICT IS THE STDOUT JSON, NOT THE EXIT CODE
(`livespec-dev-tooling-4s2sey`). These tests used to assert `main()
== 2` for a block and `== 0` for an allow, which is why the guard
shipped for weeks emitting nothing a Stop-hook evaluator could parse:
the suite asserted the LEGACY protocol, so the real wire — a response
object on stdout — was never exercised at all, and Claude Code 2.1.233
rejected every invocation with `hook returned invalid stop hook JSON
output`. A green exit-code assertion is compatible with a totally
inert hook. Assertions therefore read the PARSED stdout response, and
the subprocess pair below is the load-bearing one: it runs the script
exactly as the hook runs it and validates the bytes that actually
cross the wire.

Covered behaviors:

- worktree-path extraction from transcript text (both `worktrees/`
  and `.claude/worktrees/` layouts; dedupe; no false matches);
- marker derivation against REAL tmp_path git repos (uncommitted
  tracked changes, unpushed commits, ahead-of-canonical gating) and
  against a fake `gh` stub on PATH (unarmed-PR / no-PR detection,
  fail-open on every other `gh` outcome);
- push-name resolution (`_pushed_branch_name`) and the PR lookup keyed
  on it (`livespec-dev-tooling-i655`). The RED case is
  `test_unarmed_pr_marker_does_not_report_no_pr_for_a_merged_renamed_
  branch`: a worktree on local branch `ci-matrix-rowxc6` whose commits
  went to the forge as `feat/livespec-dev-tooling-rowxc6` and MERGED
  there. Resolving by local name found nothing, so a fully landed
  branch was reported as "pushed but has NO PR" — a marker whose named
  remedy (`gh pr create`) the forge refuses outright, since every patch
  is already on master, leaving the sub-agent to escape only via the
  anti-wedge cap. The `gh` stub these cases use is BRANCH-AWARE
  (`_install_branch_aware_gh`) rather than a fixed responder, because a
  fixed responder answers the same way whether or not the branch was
  named and so cannot tell the defect from the fix. Two controls keep
  the fix from silencing the guard: a renamed branch with genuinely no
  PR must still be flagged, and a renamed branch whose PR is open
  without auto-merge must still produce the unarmed-PR marker;
- the pure block/allow decision (`_decide`) including the
  per-session anti-wedge block cap;
- the Stop-hook response shapes (`_allow_response`, `_block_response`,
  `_hook_event_name`) and their emission on stdout (`_emit`);
- the end-to-end hook protocol via in-process `main()` calls (stdin
  JSON in, response JSON out), asserting the emitted JSON on both the
  block and the allow path.

Private names are imported via from-imports (the package-private
access model, mirroring `tests/livespec_dev_tooling/fleet/`);
monkeypatch seams use the string-target form so collaborator
functions are patched on the module the callers resolve against.

**The guard script runs IN-PROCESS.** `test_script_blocks_then_allows_
end_to_end` used to spawn `[sys.executable, subagent_stop_guard.py]`
through `_run_script`; that helper now calls `main()` directly. The
motive is the child, not the call: a `sys.executable` child inherits
`COVERAGE_PROCESS_START`, self-instruments under `pytest --cov`, and
drops a `.coverage.<host>.<pid>` file that races the parallel
dispatcher's combine step, while paying a fresh interpreter start on
each arm. Nothing about the acceptance property above is weakened —
the helper still reads the RESPONSE OBJECT off stdout through the same
`_response` parser and still fails against the retired stderr/exit-2
protocol, because an empty stdout has no response to parse.

The payload reaches `main()` the way the child got it: the script
reads stdin with one `sys.stdin.read()`, so
`monkeypatch.setattr(sys, "stdin", io.StringIO(payload))` supplies
exactly those bytes. The `env=` mapping the spawn built by hand is now
applied to the live environment — the GIT_* hook family it filtered out
is already deleted by the autouse `_scrub_git_hook_env` fixture, and
`_STATE_DIR_ENV` plus the fake-`gh` `PATH` are set with
`monkeypatch.setenv` at the same points the mapping set them, so the
guard's own `git` and `gh` probes see the identical environment.
`main()` returns the int `raise SystemExit(main())` would have handed
the shell, so no `SystemExit` is raised and none is translated.

The `git` spawns in `_git` STAY: this guard derives its markers from
REAL repository state — uncommitted tracked changes, unpushed commits,
distance from canonical — so the fixtures must build genuine repos,
and the guard itself shells out to `git` and `gh` under test. Their
hardcoded env is a REPLACEMENT for `os.environ` rather than a filtered
copy, so `COVERAGE_PROCESS_START` / `COV_CORE_*` cannot reach those
children, and this file KEEPS its `subprocess_spawn_allowlist` entry
for them.

Branch parity with the retired spawn: the same payload drives the same
two arms — the unpushed-commit block with its handoff instruction and
hook-event name, then, after a push and with an armed-PR `gh` stub on
PATH, the allow response. The only line the child reached that an
in-process call cannot is the module's
`if __name__ == "__main__": raise SystemExit(main())`, already excluded
repo-wide by the pre-existing `exclude_also` patterns in
`[tool.coverage.report]`, so no new exclusion is introduced.
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

from livespec_dev_tooling.agent_hooks.subagent_stop_guard import (
    _BLOCK_HANDOFF_INSTRUCTION,
    _DEFAULT_HOOK_EVENT_NAME,
    _MAX_BLOCKS_PER_SESSION,
    _MAX_WORKTREES,
    _STATE_DIR_ENV,
    _allow_response,
    _block_response,
    _commits_ahead_of_canonical,
    _decide,
    _derive_markers,
    _emit,
    _gather_worktrees,
    _git_count,
    _has_uncommitted_tracked_changes,
    _hook_event_name,
    _load_hook_input,
    _pushed_branch_name,
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

# The observed `livespec-dev-tooling-i655` instance, verbatim: a worktree
# sitting on local branch `ci-matrix-rowxc6` whose commits reached the
# forge under `feat/livespec-dev-tooling-rowxc6` and merged as PR #1255.
# The two names differ, which is the whole defect.
_RENAMED_LOCAL_BRANCH = "ci-matrix-rowxc6"
_RENAMED_PUSHED_BRANCH = "feat/livespec-dev-tooling-rowxc6"

# Where `_git`'s own hardcoded `PATH` ("/usr/bin:/bin") already assumes
# git lives; reused to build a bin dir carrying git and NOTHING else.
_GIT_BINARY = "/usr/bin/git"

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


def _make_renamed_pushed_repo(*, tmp_path: Path) -> Path:
    """A repo on local branch `ci-matrix-rowxc6` PUSHED as `feat/...-rowxc6`.

    `git push --set-upstream origin <local>:<pushed>` records
    `branch.<local>.merge = refs/heads/<pushed>`, so the push name is
    recoverable from LOCAL config even after the merge deleted the remote
    branch and a prune removed the remote-tracking ref — the state a
    rebase-merged leftover is actually in.
    """
    remote = tmp_path / "remote.git"
    remote.mkdir(parents=True)
    _git(cwd=remote, args=["init", "--bare", "--quiet"])
    worktree = tmp_path / "worktrees" / "wt"
    worktree.mkdir(parents=True)
    _git(cwd=worktree, args=["init", "--quiet", "-b", _RENAMED_LOCAL_BRANCH])
    _ = (worktree / "tracked.txt").write_text("v1\n", encoding="utf-8")
    _git(cwd=worktree, args=["add", "tracked.txt"])
    _git(cwd=worktree, args=["commit", "--quiet", "-m", "seed"])
    _git(cwd=worktree, args=["remote", "add", "origin", str(remote)])
    _git(cwd=worktree, args=["push", "--quiet", "origin", f"{_RENAMED_LOCAL_BRANCH}:master"])
    _git(
        cwd=worktree,
        args=[
            "push",
            "--quiet",
            "--set-upstream",
            "origin",
            f"{_RENAMED_LOCAL_BRANCH}:{_RENAMED_PUSHED_BRANCH}",
        ],
    )
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


def _install_branch_aware_gh(*, tmp_path: Path, branch: str, stdout: str) -> str:
    """Install a fake `gh` that answers `stdout` ONLY when `branch` appears in argv.

    Every other invocation — including one that names NO branch at all,
    which is exactly what the pre-fix guard issued — exits 1 with the
    forge's "no pull requests found" wording. That makes the fixture
    faithful to the forge: asking about the wrong name, or failing to ask
    about any name, is indistinguishable from a branch that genuinely has
    no pull request, which is precisely how a merged branch came to be
    reported as un-PR'd.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    gh_stub = bin_dir / "gh"
    script = (
        "#!/bin/sh\n"
        'for arg in "$@"; do\n'
        f"  [ \"$arg\" = '{branch}' ] || continue\n"
        f"  printf '%s' '{stdout}'\n"
        "  exit 0\n"
        "done\n"
        "printf 'no pull requests found for branch\\n' >&2\n"
        "exit 1\n"
    )
    _ = gh_stub.write_text(script, encoding="utf-8")
    gh_stub.chmod(0o755)
    return f"{bin_dir}:/usr/bin:/bin"


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
# _pushed_branch_name — the push name, not the local name
# ---------------------------------------------------------------------------


def test_pushed_branch_name_prefers_the_recorded_upstream_over_the_local_name(
    tmp_path: Path,
) -> None:
    worktree = _make_renamed_pushed_repo(tmp_path=tmp_path)
    assert _pushed_branch_name(worktree=worktree) == _RENAMED_PUSHED_BRANCH


def test_pushed_branch_name_falls_back_to_the_local_name_without_an_upstream(
    tmp_path: Path,
) -> None:
    # `_make_pushed_repo` pushes without `--set-upstream`, so no
    # `branch.work.merge` exists; the local name IS the push name here.
    worktree = _make_pushed_repo(tmp_path=tmp_path)
    assert _pushed_branch_name(worktree=worktree) == "work"


def test_pushed_branch_name_none_on_non_repo(tmp_path: Path) -> None:
    assert _pushed_branch_name(worktree=tmp_path) is None


def test_pushed_branch_name_none_on_detached_head(tmp_path: Path) -> None:
    worktree = _make_renamed_pushed_repo(tmp_path=tmp_path)
    _git(cwd=worktree, args=["checkout", "--quiet", "--detach", "HEAD"])
    assert _pushed_branch_name(worktree=worktree) is None


# ---------------------------------------------------------------------------
# _unarmed_pr_marker (fake `gh` stub on PATH)
#
# Every case here runs against a REAL tmp repo rather than a bare
# directory: the marker is now keyed on the branch the commits were
# pushed under, which only a repo can answer.
# ---------------------------------------------------------------------------


def test_unarmed_pr_marker_flags_pushed_branch_without_pr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    worktree = _make_pushed_repo(tmp_path=tmp_path)
    path = _install_fake_gh(
        tmp_path=tmp_path,
        stderr="no pull requests found for branch work",
        returncode=1,
    )
    monkeypatch.setenv("PATH", path)
    marker = _unarmed_pr_marker(worktree=worktree)
    assert marker is not None
    assert "NO PR" in marker


def test_unarmed_pr_marker_fails_open_on_other_gh_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    worktree = _make_pushed_repo(tmp_path=tmp_path)
    path = _install_fake_gh(tmp_path=tmp_path, stderr="HTTP 502 bad gateway", returncode=1)
    monkeypatch.setenv("PATH", path)
    assert _unarmed_pr_marker(worktree=worktree) is None


def test_unarmed_pr_marker_fails_open_on_invalid_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    worktree = _make_pushed_repo(tmp_path=tmp_path)
    path = _install_fake_gh(tmp_path=tmp_path, stdout="not json")
    monkeypatch.setenv("PATH", path)
    assert _unarmed_pr_marker(worktree=worktree) is None


def test_unarmed_pr_marker_fails_open_on_non_dict_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    worktree = _make_pushed_repo(tmp_path=tmp_path)
    path = _install_fake_gh(tmp_path=tmp_path, stdout="[1, 2]")
    monkeypatch.setenv("PATH", path)
    assert _unarmed_pr_marker(worktree=worktree) is None


def test_unarmed_pr_marker_allows_merged_pr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    worktree = _make_pushed_repo(tmp_path=tmp_path)
    path = _install_fake_gh(
        tmp_path=tmp_path,
        stdout='{"state": "MERGED", "autoMergeRequest": null}',
    )
    monkeypatch.setenv("PATH", path)
    assert _unarmed_pr_marker(worktree=worktree) is None


def test_unarmed_pr_marker_flags_open_pr_without_auto_merge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    worktree = _make_pushed_repo(tmp_path=tmp_path)
    path = _install_fake_gh(
        tmp_path=tmp_path,
        stdout='{"state": "OPEN", "autoMergeRequest": null}',
    )
    monkeypatch.setenv("PATH", path)
    marker = _unarmed_pr_marker(worktree=worktree)
    assert marker is not None
    assert "auto-merge" in marker


def test_unarmed_pr_marker_allows_armed_pr(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    worktree = _make_pushed_repo(tmp_path=tmp_path)
    path = _install_fake_gh(
        tmp_path=tmp_path,
        stdout='{"state": "OPEN", "autoMergeRequest": {"enabledAt": "2026-06-12T00:00:00Z"}}',
    )
    monkeypatch.setenv("PATH", path)
    assert _unarmed_pr_marker(worktree=worktree) is None


def test_unarmed_pr_marker_fails_open_when_gh_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    worktree = _make_pushed_repo(tmp_path=tmp_path)
    # `git` must stay reachable while `gh` is genuinely ABSENT: resolving
    # the push name precedes the `gh` call, so a bare empty PATH would
    # break `git` and short-circuit before the `gh` probe. A PATH of
    # `<empty>:/usr/bin:/bin` does not work either — this host carries a
    # real `/usr/bin/gh`, which answers (with some unrelated failure)
    # instead of raising the FileNotFoundError this case exists to drive
    # through the fail-open `except OSError`. Hence a bin dir holding
    # exactly one symlink.
    git_only_bin = tmp_path / "git-only-bin"
    git_only_bin.mkdir()
    (git_only_bin / "git").symlink_to(_GIT_BINARY)
    monkeypatch.setenv("PATH", str(git_only_bin))
    assert _unarmed_pr_marker(worktree=worktree) is None


def test_unarmed_pr_marker_fails_open_when_the_push_name_is_unresolvable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _install_fake_gh(
        tmp_path=tmp_path,
        stderr="no pull requests found for branch work",
        returncode=1,
    )
    monkeypatch.setenv("PATH", path)
    assert _unarmed_pr_marker(worktree=tmp_path) is None


# ---------------------------------------------------------------------------
# livespec-dev-tooling-i655 — the rename must not read as "no PR"
#
# The three cases below share one branch-aware `gh` fixture that answers
# ONLY when the pushed name is passed explicitly. The pre-fix guard named
# no branch at all, so it fell through to the stub's "no pull requests
# found" arm in every one of them: the merged branch was reported as
# un-PR'd (an undischargeable marker — `gh pr create` cannot open a PR
# whose every patch is already on master), and the genuinely unarmed PR
# was reported under the wrong marker text.
# ---------------------------------------------------------------------------


def test_unarmed_pr_marker_does_not_report_no_pr_for_a_merged_renamed_branch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    worktree = _make_renamed_pushed_repo(tmp_path=tmp_path)
    monkeypatch.setenv(
        "PATH",
        _install_branch_aware_gh(
            tmp_path=tmp_path,
            branch=_RENAMED_PUSHED_BRANCH,
            stdout='{"state": "MERGED", "autoMergeRequest": null}',
        ),
    )
    assert _unarmed_pr_marker(worktree=worktree) is None


def test_unarmed_pr_marker_flags_a_renamed_branch_whose_pr_is_unarmed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    worktree = _make_renamed_pushed_repo(tmp_path=tmp_path)
    monkeypatch.setenv(
        "PATH",
        _install_branch_aware_gh(
            tmp_path=tmp_path,
            branch=_RENAMED_PUSHED_BRANCH,
            stdout='{"state": "OPEN", "autoMergeRequest": null}',
        ),
    )
    marker = _unarmed_pr_marker(worktree=worktree)
    assert marker is not None
    assert "auto-merge" in marker


def test_unarmed_pr_marker_still_flags_a_renamed_branch_with_genuinely_no_pr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The control that keeps the fix from silencing the guard: the stub
    # answers for a DIFFERENT branch, so the pushed name genuinely has no
    # pull request and the marker must still be produced.
    worktree = _make_renamed_pushed_repo(tmp_path=tmp_path)
    monkeypatch.setenv(
        "PATH",
        _install_branch_aware_gh(
            tmp_path=tmp_path,
            branch="some-other-branch",
            stdout='{"state": "OPEN", "autoMergeRequest": null}',
        ),
    )
    marker = _unarmed_pr_marker(worktree=worktree)
    assert marker is not None
    assert "NO PR" in marker


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
    _ = transcript.write_text(
        f'{{"text": "git worktree add -b feature {real} master; mention {phantom}"}}\n',
        encoding="utf-8",
    )
    gathered = _gather_worktrees(hook_input={"transcript_path": str(transcript)})
    assert gathered == [real]


def test_gather_worktrees_ignores_merely_mentioned_sibling_worktree(tmp_path: Path) -> None:
    sibling = _make_pushed_repo(tmp_path=tmp_path)
    transcript = tmp_path / "transcript.jsonl"
    _ = transcript.write_text(
        f'{{"text": "sibling still dirty at {sibling}, do not touch it"}}\n',
        encoding="utf-8",
    )
    assert _gather_worktrees(hook_input={"transcript_path": str(transcript)}) == []


def test_gather_worktrees_requires_worktree_add_with_branch_option(tmp_path: Path) -> None:
    worktree = _make_pushed_repo(tmp_path=tmp_path)
    transcript = tmp_path / "transcript.jsonl"
    _ = transcript.write_text(
        f"git status {worktree}\n"
        f"git worktree add {worktree} master\n"
        f"git worktree add -b feature /tmp/plain master\n",
        encoding="utf-8",
    )
    assert _gather_worktrees(hook_input={"transcript_path": str(transcript)}) == []


def test_gather_worktrees_accepts_nested_jsonl_string_values_and_options(
    tmp_path: Path,
) -> None:
    worktree = _make_pushed_repo(tmp_path=tmp_path)
    transcript = tmp_path / "transcript.jsonl"
    payload = {
        "messages": [
            {"text": "not a command"},
            {"text": f"git worktree add --lock --reason keep -Bfeature {worktree} master"},
        ]
    }
    _ = transcript.write_text(json.dumps(payload), encoding="utf-8")
    assert _gather_worktrees(hook_input={"transcript_path": str(transcript)}) == [worktree]


def test_gather_worktrees_accepts_created_path_after_option_separator(tmp_path: Path) -> None:
    worktree = _make_pushed_repo(tmp_path=tmp_path)
    transcript = tmp_path / "transcript.jsonl"
    _ = transcript.write_text(
        f"git worktree add -b feature -- {worktree} master\n",
        encoding="utf-8",
    )
    assert _gather_worktrees(hook_input={"transcript_path": str(transcript)}) == [worktree]


def test_gather_worktrees_recovers_an_unparseable_shell_segment(tmp_path: Path) -> None:
    """An unbalanced quote must not hide a worktree — `livespec-dev-tooling-dno1`.

    ⛔ THIS TEST PINNED THE DEFECT. It was
    `test_gather_worktrees_ignores_unparseable_shell_segment` and asserted `[]`,
    so "the guard sees nothing when `shlex` cannot tokenize the segment" read as
    the CONTRACT rather than as the bug. `shlex.split` raises on ANY unbalanced
    quote — in prose, any apostrophe — so the discard was the common path for a
    narrated worktree creation, in the guard whose whole job is to stop
    worktrees being left unreaped.

    `_tokenize` now degrades to a whitespace split instead of discarding, so the
    `git worktree add -b <branch> <path>` here is still seen. The degradation
    cannot manufacture a path: the candidate is validated against the
    worktree-path regex, which forbids whitespace inside a path.
    """
    worktree = _make_pushed_repo(tmp_path=tmp_path)
    transcript = tmp_path / "transcript.jsonl"
    _ = transcript.write_text(
        f"git worktree add -b 'unterminated {worktree}\n",
        encoding="utf-8",
    )
    assert _gather_worktrees(hook_input={"transcript_path": str(transcript)}) == [worktree]


def test_gather_worktrees_ignores_json_without_string_segments(tmp_path: Path) -> None:
    transcript = tmp_path / "transcript.jsonl"
    _ = transcript.write_text('{"value": 1}\n', encoding="utf-8")
    assert _gather_worktrees(hook_input={"transcript_path": str(transcript)}) == []


# ---------------------------------------------------------------------------
# Stop-hook response shapes
# ---------------------------------------------------------------------------


def test_allow_response_is_the_valid_allow_object() -> None:
    assert _allow_response() == {"continue": True, "suppressOutput": True}


def test_block_response_carries_markers_and_handoff_in_additional_context() -> None:
    response = _block_response(
        markers=["/wt: 2 unpushed commit(s)"], hook_event_name="SubagentStop"
    )
    assert response["decision"] == "block"
    hook_specific = response["hookSpecificOutput"]
    assert isinstance(hook_specific, dict)
    context = hook_specific["additionalContext"]
    assert isinstance(context, str)
    assert hook_specific["hookEventName"] == "SubagentStop"
    assert "/wt: 2 unpushed commit(s)" in context
    assert _BLOCK_HANDOFF_INSTRUCTION in context
    # The reason (what actually keeps the sub-agent running) and the
    # additional context (what tells it WHAT to do) must not diverge.
    assert response["reason"] == context


def test_block_response_lists_every_derived_marker() -> None:
    response = _block_response(
        markers=["/a: uncommitted tracked changes", "/b: branch is pushed but has NO PR"],
        hook_event_name="Stop",
    )
    hook_specific = response["hookSpecificOutput"]
    assert isinstance(hook_specific, dict)
    context = hook_specific["additionalContext"]
    assert isinstance(context, str)
    assert "- /a: uncommitted tracked changes" in context
    assert "- /b: branch is pushed but has NO PR" in context
    assert hook_specific["hookEventName"] == "Stop"


def test_hook_event_name_echoes_the_input_and_defaults_when_absent() -> None:
    assert _hook_event_name(hook_input={"hook_event_name": "Stop"}) == "Stop"
    assert _hook_event_name(hook_input={}) == _DEFAULT_HOOK_EVENT_NAME
    assert _hook_event_name(hook_input={"hook_event_name": ""}) == _DEFAULT_HOOK_EVENT_NAME
    assert _hook_event_name(hook_input={"hook_event_name": 7}) == _DEFAULT_HOOK_EVENT_NAME


def test_emit_writes_one_json_line_to_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    _emit(response={"continue": True})
    captured = capsys.readouterr()
    assert captured.out == '{"continue": true}\n'


# ---------------------------------------------------------------------------
# main() — in-process hook-protocol behavior
#
# Every assertion reads the PARSED stdout response. `_response` fails
# LOUDLY on empty stdout rather than letting `json.loads` raise, because
# "the hook emitted nothing" is precisely the defect
# livespec-dev-tooling-4s2sey fixed and it deserves a named failure.
# ---------------------------------------------------------------------------


def _response(*, stdout: str) -> dict[str, object]:
    assert stdout.strip(), "hook emitted no stdout; a Stop-hook response object is required"
    payload = json.loads(stdout)
    assert isinstance(payload, dict)
    return payload


def _run_main(
    *, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], stdin_text: str
) -> tuple[int, dict[str, object]]:
    monkeypatch.setattr(sys, "stdin", io.StringIO(stdin_text))
    exit_code = main()
    return exit_code, _response(stdout=capsys.readouterr().out)


def _assert_allowed(*, exit_code: int, response: dict[str, object]) -> None:
    assert exit_code == 0
    assert response == _allow_response()


def test_main_fails_open_on_unparseable_stdin(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code, response = _run_main(monkeypatch=monkeypatch, capsys=capsys, stdin_text="{nope")
    _assert_allowed(exit_code=exit_code, response=response)


def test_main_allows_when_no_worktrees_in_transcript(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    transcript = tmp_path / "transcript.jsonl"
    _ = transcript.write_text('{"text": "no worktree mention"}\n', encoding="utf-8")
    payload = json.dumps({"session_id": "s1", "transcript_path": str(transcript)})
    exit_code, response = _run_main(monkeypatch=monkeypatch, capsys=capsys, stdin_text=payload)
    _assert_allowed(exit_code=exit_code, response=response)


def test_main_allows_when_worktree_is_handed_off(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    worktree = _make_pushed_repo(tmp_path=tmp_path)
    transcript = tmp_path / "transcript.jsonl"
    _ = transcript.write_text(
        f'{{"text": "git worktree add -b feature {worktree} master"}}\n',
        encoding="utf-8",
    )
    payload = json.dumps({"session_id": "s2", "transcript_path": str(transcript)})
    exit_code, response = _run_main(monkeypatch=monkeypatch, capsys=capsys, stdin_text=payload)
    _assert_allowed(exit_code=exit_code, response=response)


def test_main_blocks_on_unpushed_commits_and_counts_blocks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    monkeypatch.setenv(_STATE_DIR_ENV, str(state_dir))
    worktree = _make_pushed_repo(tmp_path=tmp_path)
    _add_unpushed_commit(worktree=worktree)
    transcript = tmp_path / "transcript.jsonl"
    _ = transcript.write_text(
        f'{{"text": "git worktree add -b feature {worktree} master"}}\n',
        encoding="utf-8",
    )
    payload = json.dumps(
        {
            "session_id": "s3",
            "transcript_path": str(transcript),
            "hook_event_name": "SubagentStop",
        }
    )
    exit_code, response = _run_main(monkeypatch=monkeypatch, capsys=capsys, stdin_text=payload)
    assert exit_code == 0
    assert response["decision"] == "block"
    hook_specific = response["hookSpecificOutput"]
    assert isinstance(hook_specific, dict)
    assert hook_specific["hookEventName"] == "SubagentStop"
    context = hook_specific["additionalContext"]
    assert isinstance(context, str)
    assert "unpushed commit" in context
    assert _read_block_count(path=_state_path(session_id="s3")) == 1


def test_main_fails_open_past_the_block_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    monkeypatch.setenv(_STATE_DIR_ENV, str(state_dir))
    worktree = _make_pushed_repo(tmp_path=tmp_path)
    _add_unpushed_commit(worktree=worktree)
    transcript = tmp_path / "transcript.jsonl"
    _ = transcript.write_text(
        f'{{"text": "git worktree add -b feature {worktree} master"}}\n',
        encoding="utf-8",
    )
    _record_block(path=_state_path(session_id="s4"), count=_MAX_BLOCKS_PER_SESSION)
    payload = json.dumps({"session_id": "s4", "transcript_path": str(transcript)})
    exit_code, response = _run_main(monkeypatch=monkeypatch, capsys=capsys, stdin_text=payload)
    _assert_allowed(exit_code=exit_code, response=response)


def test_main_fails_open_on_internal_crash(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def exploding_gather(*, hook_input: dict[str, object]) -> list[Path]:
        _ = hook_input
        raise RuntimeError("boom")

    monkeypatch.setattr(f"{_MODULE}._gather_worktrees", exploding_gather)
    exit_code, response = _run_main(
        monkeypatch=monkeypatch, capsys=capsys, stdin_text='{"session_id": "s5"}'
    )
    _assert_allowed(exit_code=exit_code, response=response)


# ---------------------------------------------------------------------------
# end-to-end — the hook protocol exactly as Claude Code drives it.
#
# THIS PAIR IS THE ACCEPTANCE TEST for livespec-dev-tooling-4s2sey: it
# reads the bytes that actually cross the wire, so it fails against the
# retired stderr/exit-2 protocol (whose stdout was empty on BOTH paths)
# no matter how the in-process seams are shaped.
# ---------------------------------------------------------------------------


def _run_script(
    *,
    payload: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> tuple[int, dict[str, object]]:
    """Drive the hook end to end: JSON payload on stdin, exit code + parsed stdout out.

    The retired spawn handed `payload` to the child on its stdin pipe; the
    script reads it with a single `sys.stdin.read()`, so a monkeypatched
    `io.StringIO` delivers byte-for-byte what the child received, and the
    response object is read off `capsys` stdout by the same `_response`
    parser that read `CompletedProcess.stdout`. `main()` returns the int the
    `raise SystemExit(main())` line would have carried to the shell, so no
    `SystemExit` translation is involved.
    """
    monkeypatch.setattr(sys, "stdin", io.StringIO(payload))
    exit_code = main()
    return exit_code, _response(stdout=capsys.readouterr().out)


def test_script_blocks_then_allows_end_to_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    worktree = _make_pushed_repo(tmp_path=tmp_path)
    _add_unpushed_commit(worktree=worktree)
    transcript = tmp_path / "transcript.jsonl"
    _ = transcript.write_text(
        f'{{"text": "git worktree add -b feature {worktree} master"}}\n',
        encoding="utf-8",
    )
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    payload = json.dumps({"session_id": "e2e", "transcript_path": str(transcript)})
    # The env the spawn built by hand is now applied to the live process
    # environment: the GIT_* hook family is already deleted by the autouse
    # `_scrub_git_hook_env` fixture (the same vars the spawn filtered out),
    # and the state dir is set the way the child received it.
    monkeypatch.setenv(_STATE_DIR_ENV, str(state_dir))

    blocked_code, blocked = _run_script(payload=payload, monkeypatch=monkeypatch, capsys=capsys)
    assert blocked_code == 0
    assert blocked["decision"] == "block"
    hook_specific = blocked["hookSpecificOutput"]
    assert isinstance(hook_specific, dict)
    assert hook_specific["hookEventName"] == _DEFAULT_HOOK_EVENT_NAME
    context = hook_specific["additionalContext"]
    assert isinstance(context, str)
    assert "unpushed commit" in context
    assert _BLOCK_HANDOFF_INSTRUCTION in context

    _push_branch(worktree=worktree)
    monkeypatch.setenv(
        "PATH",
        _install_fake_gh(
            tmp_path=tmp_path,
            stdout='{"state": "OPEN", "autoMergeRequest": {"enabledAt": "2026-06-12T00:00:00Z"}}',
        ),
    )
    allowed_code, allowed = _run_script(payload=payload, monkeypatch=monkeypatch, capsys=capsys)
    assert allowed_code == 0
    assert allowed == {"continue": True, "suppressOutput": True}
