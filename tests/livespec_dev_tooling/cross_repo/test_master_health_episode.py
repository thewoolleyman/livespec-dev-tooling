"""Tests for `master_health_episode` — reading one red episode off the timeline.

No I/O, no forge, no LLM: every timeline replayed here is a RECORDED GitHub
state built in-process (work-item `livespec-dev-tooling-hrpcgl`, child C1 of
plan `red-master-self-healing`).

THE TIMELINES CARRY CANCELLED COMMITS ON PURPOSE. The plan's measurements
recorded 46 merges in 24 h with a peak of 6/h in the busiest fleet repository,
so a red episode routinely spans several master commits whose runs were
cancelled or batched rather than cleanly red. A rule derived from a tidy
green-then-red pair silently picks the wrong culprit on exactly that traffic.
"""

from __future__ import annotations

from dataclasses import replace

from livespec_dev_tooling.cross_repo.master_health_episode import (
    culprit_commit,
    head_commit,
    red_block,
    red_since,
)
from livespec_dev_tooling.cross_repo.master_health_state import (
    CI_CANCELLED,
    CI_FAILURE,
    CI_PENDING,
    CI_SUCCESS,
    RERUN_STILL_RED,
    MasterCommit,
    ReconcileState,
)

_LINT_FAILURE = "check-lint failed"
_GATING_WORKFLOW = "CI"
_LOOKBACK_COMMITS = 20
_ORDINARY_SUBJECT = "feat(cross-repo): an ordinary merge"


def _commit(
    *,
    sha: str,
    parent_sha: str,
    conclusion: str,
    pull_request: int | None = None,
    signature: str | None = None,
) -> MasterCommit:
    """A gating-workflow record; the non-gating shapes live in the gating tests."""
    return MasterCommit(
        sha=sha,
        parent_sha=parent_sha,
        pull_request=pull_request,
        ci_workflow=_GATING_WORKFLOW,
        ci_conclusion=conclusion,
        failure_signature=signature,
        subject=_ORDINARY_SUBJECT,
    )


def _state(*, head_sha: str, commits: tuple[MasterCommit, ...]) -> ReconcileState:
    return ReconcileState(
        head_sha=head_sha,
        commits=commits,
        rerun_outcome=RERUN_STILL_RED,
        revert_pull_request=None,
        open_needs_attention_episodes=(),
    )


def test_the_culprit_is_the_earliest_red_commit_whose_parent_was_green() -> None:
    """The acceptance assertion, on a block that mixes red with cancelled.

    `b` is named rather than the head `d` because reverting the newest red
    commit would leave the actual regression on master and burn a revert cycle
    proving it.
    """
    state = _state(
        head_sha="d",
        commits=(
            _commit(sha="a", parent_sha="root", conclusion=CI_SUCCESS),
            _commit(
                sha="b",
                parent_sha="a",
                conclusion=CI_FAILURE,
                pull_request=101,
                signature=_LINT_FAILURE,
            ),
            _commit(sha="c", parent_sha="b", conclusion=CI_CANCELLED),
            _commit(
                sha="d",
                parent_sha="c",
                conclusion=CI_FAILURE,
                pull_request=103,
                signature=_LINT_FAILURE,
            ),
        ),
    )

    culprit = culprit_commit(state=state)

    assert culprit is not None
    assert culprit.sha == "b"
    assert culprit.pull_request == 101


def test_the_red_block_spans_every_commit_back_to_the_last_green_oldest_first() -> None:
    """The block is the episode's extent, and it is reported oldest-first.

    Ordering is load-bearing: "earliest red" is read off the front of this
    tuple, so a newest-first block would invert the culprit rule silently.
    """
    state = _state(
        head_sha="d",
        commits=(
            _commit(sha="a", parent_sha="root", conclusion=CI_SUCCESS),
            _commit(
                sha="b",
                parent_sha="a",
                conclusion=CI_FAILURE,
                pull_request=101,
                signature=_LINT_FAILURE,
            ),
            _commit(sha="c", parent_sha="b", conclusion=CI_CANCELLED),
            _commit(
                sha="d",
                parent_sha="c",
                conclusion=CI_FAILURE,
                pull_request=103,
                signature=_LINT_FAILURE,
            ),
        ),
    )

    assert [commit.sha for commit in red_block(state=state)] == ["b", "c", "d"]


def test_a_green_head_has_no_red_block_and_no_culprit() -> None:
    """Master is healthy: the episode reader must invent nothing."""
    state = _state(
        head_sha="a",
        commits=(_commit(sha="a", parent_sha="root", conclusion=CI_SUCCESS),),
    )

    assert red_block(state=state) == ()
    assert culprit_commit(state=state) is None


def test_a_pending_commit_never_anchors_an_episode_with_a_completed_failure() -> None:
    """Pending CI above and below a failure does not become the episode start.

    The head is still pending, but `failed` is the newest completed red
    verdict. The older pending run cannot make the episode key look like a
    failure began before any gating job had actually failed.
    """
    state = _state(
        head_sha="pending-after",
        commits=(
            _commit(sha="green", parent_sha="root", conclusion=CI_SUCCESS),
            _commit(sha="pending-before", parent_sha="green", conclusion=CI_PENDING),
            _commit(
                sha="failed",
                parent_sha="pending-before",
                conclusion=CI_FAILURE,
                signature=_LINT_FAILURE,
            ),
            _commit(sha="pending-after", parent_sha="failed", conclusion=CI_PENDING),
        ),
    )

    assert [commit.sha for commit in red_block(state=state)] == ["failed", "pending-after"]


def test_the_head_record_is_read_by_sha_and_is_none_when_the_window_misses_it() -> None:
    """A truncated window answers `None`, which is not the same as a green head.

    Both a green head and a window missing the head produce an EMPTY red
    block, so a caller reading the head's own verdict — the superseded-green
    rule does — needs this to tell them apart rather than deciding on the
    absence of evidence.
    """
    recorded = _commit(sha="a", parent_sha="root", conclusion=CI_SUCCESS)
    state = _state(head_sha="a", commits=(recorded,))

    assert head_commit(state=state) == recorded
    assert head_commit(state=_state(head_sha="missing", commits=(recorded,))) is None


def test_no_culprit_when_the_earliest_reds_parent_is_not_in_the_window() -> None:
    """A truncated window is not evidence, so it names no culprit.

    The parent's verdict is what distinguishes "this merge broke master" from
    "master was already broken when this merge landed". Absent that commit the
    reconciler cannot tell, and guessing here reverts an innocent merge — so
    the honest answer is none, which routes the episode to a human instead.
    """
    state = _state(
        head_sha="b",
        commits=(
            _commit(
                sha="b",
                parent_sha="a",
                conclusion=CI_FAILURE,
                pull_request=101,
                signature=_LINT_FAILURE,
            ),
        ),
    )

    assert red_block(state=state) == (state.commits[0],)
    assert culprit_commit(state=state) is None


def test_no_culprit_when_the_block_opens_on_a_cancelled_run() -> None:
    """A cancelled run is UNDECIDED, so it can neither be nor prove a culprit.

    The earliest red here is `c`, whose parent `b` was cancelled rather than
    green — so no red commit in the block has a green parent and the rule
    yields none. Treating a cancelled parent as green would revert `c` on the
    strength of a run that never spoke.
    """
    state = _state(
        head_sha="c",
        commits=(
            _commit(sha="a", parent_sha="root", conclusion=CI_SUCCESS),
            _commit(sha="b", parent_sha="a", conclusion=CI_CANCELLED),
            _commit(
                sha="c",
                parent_sha="b",
                conclusion=CI_FAILURE,
                pull_request=102,
                signature=_LINT_FAILURE,
            ),
        ),
    )

    assert [commit.sha for commit in red_block(state=state)] == ["b", "c"]
    assert culprit_commit(state=state) is None


def _timed(*, commit: MasterCommit, completed_at: int | None) -> MasterCommit:
    return replace(commit, ci_completed_at=completed_at)


def test_the_branch_went_red_when_the_earliest_failed_commit_s_ci_concluded() -> None:
    """The hard cap measures from the first FAILURE, skipping an undecided opener."""
    state = _state(
        head_sha="d",
        commits=(
            _commit(sha="a", parent_sha="root", conclusion=CI_SUCCESS),
            _timed(
                commit=_commit(sha="b", parent_sha="a", conclusion=CI_CANCELLED), completed_at=50
            ),
            _timed(
                commit=_commit(
                    sha="c", parent_sha="b", conclusion=CI_FAILURE, signature=_LINT_FAILURE
                ),
                completed_at=100,
            ),
            _timed(
                commit=_commit(
                    sha="d", parent_sha="c", conclusion=CI_FAILURE, signature=_LINT_FAILURE
                ),
                completed_at=200,
            ),
        ),
    )

    assert red_since(state=state) == 100


def test_no_red_since_for_a_green_branch_or_one_with_no_failed_commit() -> None:
    green = _state(
        head_sha="a", commits=(_commit(sha="a", parent_sha="root", conclusion=CI_SUCCESS),)
    )
    undecided = _state(
        head_sha="b",
        commits=(
            _commit(sha="a", parent_sha="root", conclusion=CI_SUCCESS),
            _timed(
                commit=_commit(sha="b", parent_sha="a", conclusion=CI_CANCELLED), completed_at=5
            ),
        ),
    )
    untimed = _state(
        head_sha="b",
        commits=(
            _commit(sha="a", parent_sha="root", conclusion=CI_SUCCESS),
            _commit(sha="b", parent_sha="a", conclusion=CI_FAILURE, signature=_LINT_FAILURE),
        ),
    )

    assert (red_since(state=green), red_since(state=undecided), red_since(state=untimed)) == (
        None,
        None,
        None,
    )
