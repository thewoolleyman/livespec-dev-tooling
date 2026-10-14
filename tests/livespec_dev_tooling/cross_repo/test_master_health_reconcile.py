"""Tests for `master_health_reconcile` — the at-most-one-step decision table.

No I/O, no forge, no LLM: every state replayed here is a RECORDED GitHub state
built in-process, which is the only shape this work-item's acceptance
assertions can be graded against — each one opens "given a recorded GitHub
state" (work-item `livespec-dev-tooling-hrpcgl`, child C1 of plan
`red-master-self-healing`).

THE INCIDENT SHAPE IS THE FIRST TEST. On 2026-10-14 orchestrator PR #2917
passed PR CI and its rebase-merge `35fea321` reddened master, the green-master
gate refused every factory dispatch for ~38 minutes, and revert-versus-
fix-forward was settled by whoever happened to act first. That episode, reduced
to a two-commit recorded state, is what the first test replays.
"""

from __future__ import annotations

from livespec_dev_tooling.cross_repo.master_health_reconcile import (
    NEEDS_ATTENTION_LABEL,
    STEP_NEEDS_ATTENTION,
    STEP_NONE,
    STEP_OPEN_REVERT,
    STEP_RERUN_FAILED_JOBS,
    reconcile_step,
)
from livespec_dev_tooling.cross_repo.master_health_state import (
    CI_FAILURE,
    CI_SUCCESS,
    RERUN_NOT_ATTEMPTED,
    RERUN_STILL_RED,
    MasterCommit,
    ReconcileConfig,
    ReconcileState,
)

_LINT_FAILURE = "check-lint failed"

_CONFIG = ReconcileConfig(
    target_branch="master",
    infra_outage_markers=("No runner matching", "registry down"),
)


def _commit(
    *,
    sha: str,
    parent_sha: str,
    conclusion: str,
    pull_request: int | None = None,
    signature: str | None = None,
) -> MasterCommit:
    return MasterCommit(
        sha=sha,
        parent_sha=parent_sha,
        pull_request=pull_request,
        ci_conclusion=conclusion,
        failure_signature=signature,
    )


def _incident_state(
    *,
    rerun_outcome: str = RERUN_STILL_RED,
    culprit_pull_request: int | None = 2917,
) -> ReconcileState:
    """The 2026-10-14 shape: a green parent, then a red rebase-merge."""
    return ReconcileState(
        head_sha="35fea321",
        commits=(
            _commit(sha="parent0", parent_sha="root", conclusion=CI_SUCCESS),
            _commit(
                sha="35fea321",
                parent_sha="parent0",
                conclusion=CI_FAILURE,
                pull_request=culprit_pull_request,
                signature=_LINT_FAILURE,
            ),
        ),
        rerun_outcome=rerun_outcome,
        revert_pull_request=None,
        open_needs_attention_episodes=(),
        unrelated_failure_signatures=(),
    )


def test_a_still_red_rerun_on_a_green_parent_opens_the_revert_with_auto_merge_held() -> None:
    """The acceptance assertion: one run opens the culprit's revert, HELD.

    `auto_merge_held` is asserted explicitly because it is the half of this
    step that keeps the revert from landing before its own CI has spoken.
    Opening and releasing are two separate steps precisely so that no single
    run can do both.
    """
    step = reconcile_step(state=_incident_state(), config=_CONFIG)

    assert step.kind == STEP_OPEN_REVERT
    assert step.culprit_pull_request == 2917
    assert step.culprit_sha == "35fea321"
    assert step.auto_merge_held is True
    assert step.target_branch == "master"


def test_the_first_sight_of_red_re_runs_the_failed_jobs_rather_than_reverting() -> None:
    """An unclassified red owes a re-run; it is not yet a regression.

    This is the step that makes the flake class reachable at all. Without it
    the reconciler would revert on first sight of red and the re-run evidence
    would never exist.
    """
    step = reconcile_step(state=_incident_state(rerun_outcome=RERUN_NOT_ATTEMPTED), config=_CONFIG)

    assert step.kind == STEP_RERUN_FAILED_JOBS
    assert step.culprit_pull_request is None


def test_a_green_branch_yields_no_step_at_all() -> None:
    """Nothing to heal. The reconciler must be silent on a healthy branch."""
    state = ReconcileState(
        head_sha="parent0",
        commits=(_commit(sha="parent0", parent_sha="root", conclusion=CI_SUCCESS),),
        rerun_outcome=RERUN_NOT_ATTEMPTED,
        revert_pull_request=None,
        open_needs_attention_episodes=(),
        unrelated_failure_signatures=(),
    )

    step = reconcile_step(state=state, config=_CONFIG)

    assert step.kind == STEP_NONE
    assert step.episode_key is None


def test_a_regression_whose_culprit_has_no_pull_request_escalates_instead() -> None:
    """A direct push cannot be reverted through a pull request.

    The revert mechanism is a forge-side revert OF A PULL REQUEST, so a commit
    that never had one is outside what this reconciler can act on. It escalates
    rather than inventing a hand-rolled revert commit, which would carry none
    of the signing the server-side-revert exemption looks for.
    """
    step = reconcile_step(state=_incident_state(culprit_pull_request=None), config=_CONFIG)

    assert step.kind == STEP_NEEDS_ATTENTION
    assert step.episode_key == "master@35fea321"
    assert NEEDS_ATTENTION_LABEL == "master-health-needs-attention"
