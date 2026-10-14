"""Read ONE red episode off the watched branch's recorded timeline.

Per `SPECIFICATION/contracts.md` section "Cross-repo coordination automation
surface", and the design recorded in this repository's
`plan/red-master-self-healing/research/001-charter-red-master-self-healing.md`
(child C1, work-item `livespec-dev-tooling-hrpcgl`).

Two questions about a red branch, both pure functions of the recorded state:
how far back the current red episode extends, and which merge caused it.

ANCESTRY IS WALKED THROUGH `parent_sha`, NEVER THROUGH LIST POSITION. The forge
hands a commit window over in whatever order the endpoint happened to return,
and a rule that trusted that order would read a correct window as a different
timeline. Walking the links means a caller supplying its commits newest-first,
oldest-first or unordered gets the same answer.

A CANCELLED OR PENDING RUN IS UNDECIDED — NOT GREEN, AND NOT RED. It is counted
INSIDE the episode (the branch is not known-good there, so the episode has not
ended) but it can neither BE a culprit nor PROVE one. Those are two separate
consequences of the same fact and both are load-bearing: treating an undecided
run as green reverts a commit on the strength of a run that never spoke, and
treating it as red names a culprit whose own CI never failed. The plan's
measurements make this the common case rather than an edge — 46 merges in 24 h
at a peak of 6/h in the busiest fleet repository, where runs are routinely
cancelled by a newer push or batched.

THE CULPRIT RULE IS DELIBERATELY INCOMPLETE, AND FAILS TO "NONE". A red commit
is named only when its parent is recorded AND green, because the parent's
verdict is the only thing separating "this merge broke the branch" from "the
branch was already broken when this merge landed". When the window is truncated
above the episode, or the episode opens on an undecided run, there is no such
evidence and this answers `None` — which routes the episode to a human instead
of reverting an innocent merge. An unprovable culprit and a proven one must
never be indistinguishable.
"""

from __future__ import annotations

from livespec_dev_tooling.cross_repo.master_health_state import (
    CI_FAILURE,
    CI_SUCCESS,
    MasterCommit,
    ReconcileState,
)

__all__: list[str] = ["culprit_commit", "red_block"]


def _by_sha(*, state: ReconcileState) -> dict[str, MasterCommit]:
    """Index the recorded window so ancestry is a lookup rather than a scan."""
    return {commit.sha: commit for commit in state.commits}


def red_block(*, state: ReconcileState) -> tuple[MasterCommit, ...]:
    """The episode: commits from the head back to the last green, OLDEST-FIRST.

    Walks parents from `head_sha` and stops at the first commit whose own CI
    was green, or when the window runs out. Oldest-first is the contract the
    culprit rule reads "earliest" off, so reversing it would invert that rule
    silently rather than failing.

    A green head yields an empty block, which is how a caller distinguishes a
    healthy branch from an episode of length one.
    """
    by_sha = _by_sha(state=state)
    block: list[MasterCommit] = []
    cursor = by_sha.get(state.head_sha)
    while cursor is not None and cursor.ci_conclusion != CI_SUCCESS:
        block.append(cursor)
        cursor = by_sha.get(cursor.parent_sha)
    block.reverse()
    return tuple(block)


def culprit_commit(*, state: ReconcileState) -> MasterCommit | None:
    """The earliest RED commit in the episode whose parent was GREEN, or `None`.

    Both halves of the test are required, and neither is a formality: the
    commit itself must have FAILED (an undecided run is not a regression), and
    its parent must be recorded and have SUCCEEDED (otherwise the branch's
    state before this merge is unknown). See this module's docstring for why
    the honest answer when neither holds is `None`.
    """
    by_sha = _by_sha(state=state)
    for commit in red_block(state=state):
        if commit.ci_conclusion != CI_FAILURE:
            continue
        parent = by_sha.get(commit.parent_sha)
        if parent is not None and parent.ci_conclusion == CI_SUCCESS:
            return commit
    return None
