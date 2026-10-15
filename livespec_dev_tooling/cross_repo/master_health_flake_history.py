"""Read whether this episode's failures were ALREADY failing below it.

Per `SPECIFICATION/contracts.md` section "Cross-repo coordination automation
surface", and the design recorded in this repository's
`plan/red-master-self-healing/research/001-charter-red-master-self-healing.md`
(the culprit-selection calibration of child C1, work-item
`livespec-dev-tooling-zdqnr2`).

A CHECK THAT WAS ALREADY FAILING IS NOT THIS MERGE'S FAULT, and the plan's
calibration measured how much of the fleet's red this accounts for:
`check-e2e-tmux` failed in 25 of console-beads-fabro's 27 episodes, most of
them cleared by an unrelated docs commit. A reconciler reading only the current
episode would have reverted innocent `docs(plan)` merges, repeatedly, and each
revert would have left the check failing exactly as before.

THE EVIDENCE IS THE RECORDED WINDOW, NOT A SUMMARY. This rule reads the commits
BELOW the episode — a red commit beneath a green one is a previous episode of
its own — so the decision can be replayed from the same state that produced it.
It replaced a pre-computed `unrelated_failure_signatures` field the gatherer
filled in: that summary carried no DISTANCE, so the decision could not tell a
failure from ten minutes ago from one three months old, and therefore could not
bound itself at all.

THE WINDOW IS BOUNDED BY COMMITTED CONFIGURATION, and the bound is the whole
reason this is a rule rather than a reflex. Check names recur for unrelated
reasons — `check-per-file-coverage` fails for a hundred different causes — so
an unbounded history would exonerate every regression that happens to fail a
check some older commit also failed. The bound is counted in COMMITS rather
than minutes because the decision path holds no clock: a commit count is
replayable, a duration read at decision time is not.

Measured against the fleet's traffic, a commit count also scales the way the
question does: the charter measured 46 merges in 24 h in the busiest fleet
repository and 4 in the quietest, so N commits is "recent history" in both
without either needing its own clock.
"""

from __future__ import annotations

from livespec_dev_tooling.cross_repo.master_health_episode import lookback_block
from livespec_dev_tooling.cross_repo.master_health_state import (
    ReconcileConfig,
    ReconcileState,
)

__all__: list[str] = ["recurring_signatures"]


def recurring_signatures(*, state: ReconcileState, config: ReconcileConfig) -> frozenset[str]:
    """The failure signatures recorded below the episode, within the lookback.

    Commits with no signature are DROPPED rather than contributing an empty
    string, for the reason the episode-side read drops them: an empty signature
    would compare equal to nothing useful and would match an outage marker as a
    substring. A green branch has no episode, so it has nothing to compare and
    answers with the empty set.
    """
    return frozenset(
        commit.failure_signature
        for commit in lookback_block(state=state, lookback=config.unrelated_lookback_commits)
        if commit.failure_signature is not None
    )
