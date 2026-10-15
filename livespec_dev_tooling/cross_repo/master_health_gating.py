"""Project a recorded window onto the repository's GATING CI workflow.

Per `SPECIFICATION/contracts.md` section "Cross-repo coordination automation
surface", and the design recorded in this repository's
`plan/red-master-self-healing/research/001-charter-red-master-self-healing.md`
(the culprit-selection calibration of child C1, work-item
`livespec-dev-tooling-zdqnr2`).

ONE WORKFLOW DECIDES WHETHER THE BRANCH IS RED, and it is the one branch
protection reads: the workflow whose all-green gate job is the required status
check. Every other workflow on the branch — a scheduled sweep, a telemetry
export, a nightly drill — can fail for days without a single merge being
blocked, because none of them gates one. Measured on 2026-10-15 on this
repository: a non-gating scheduled workflow had been red for days on an
infrastructure fault while the gating workflow was green on every master
commit. A reconciler reading the newest failing run on the branch would have
opened a revert for a commit whose own gating CI never failed.

A NON-GATING RECORD IS DROPPED, NOT DOWNGRADED TO UNDECIDED. Downgrading would
leave the commit INSIDE the episode — the branch is not known-good there — so a
non-gating failure would still start an episode and still hold the branch open
waiting for a culprit. Dropping leaves the gating verdict for that commit
exactly as recorded: present when the gating workflow spoke, ABSENT when it did
not, which is the truncated-window state the culprit rule already answers
`None` to.

ONE COMMIT MAY CARRY SEVERAL RECORDS, one per workflow that ran on it, which is
what a gatherer reading each workflow's newest run per commit produces. That is
why this projection runs BEFORE anything indexes the window: the episode reader
walks `parent_sha` through a by-sha index, so a non-gating record sharing a sha
with the gating one would otherwise decide the verdict by whichever of the two
landed last — reading a red master as green, or a green one as red.

The projection is applied ONCE, at `master_health_reconcile.reconcile_step` —
the single public entry point of the decision — so every sibling rule sees the
same projected window and none of them has to remember to ask.
"""

from __future__ import annotations

from dataclasses import replace

from livespec_dev_tooling.cross_repo.master_health_state import (
    ReconcileConfig,
    ReconcileState,
)

__all__: list[str] = ["gating_state"]


def gating_state(*, state: ReconcileState, config: ReconcileConfig) -> ReconcileState:
    """The same recorded state with every non-gating workflow record removed.

    Everything else is carried through unchanged, including `head_sha`: the
    head is a fact the caller read from the forge, and it stays true whether or
    not the gating workflow has yet spoken about that commit.
    """
    return replace(
        state,
        commits=tuple(
            commit for commit in state.commits if commit.ci_workflow == config.gating_workflow
        ),
    )
