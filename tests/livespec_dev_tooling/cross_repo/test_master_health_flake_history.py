"""Tests for `master_health_flake_history` — did this check already fail below?

No I/O, no forge, no LLM: every state replayed here is a RECORDED GitHub state
built in-process (work-item `livespec-dev-tooling-zdqnr2`, the culprit-selection
calibration of child C1 in plan `red-master-self-healing`).

THE MEASURED SHAPE IS A CHRONICALLY FLAKY CHECK. The plan's calibration found
`check-e2e-tmux` failing in 25 of console-beads-fabro's 27 episodes, most of
them cleared by an unrelated docs commit — so a revert-by-default reconciler
reading only the current episode would have reverted innocent `docs(plan)`
merges, over and over. The window below the episode is where the evidence
against that lives, and every state here carries an EARLIER red episode for
exactly that reason.

THE WINDOW IS BOUNDED, AND THE BOUND IS TESTED BOTH WAYS. An unbounded history
convicts today's genuine regression on a signature that failed once months ago
for an unrelated reason — check names recur, causes do not — so the same state
is replayed at a lookback that reaches the earlier failure and at one that does
not.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from types import ModuleType

from livespec_dev_tooling.cross_repo.master_health_reconcile import (
    STEP_NEEDS_ATTENTION,
    STEP_OPEN_REVERT,
    reconcile_step,
)
from livespec_dev_tooling.cross_repo.master_health_state import (
    CI_FAILURE,
    CI_SUCCESS,
    RERUN_STILL_RED,
    MasterCommit,
    ReconcileConfig,
    ReconcileState,
)
from livespec_dev_tooling.cross_repo.master_health_verdict import (
    VERDICT_INFRA,
    VERDICT_REGRESSION,
    red_verdict,
)

_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / "livespec_dev_tooling"
    / "cross_repo"
    / "master_health_flake_history.py"
)
_MODULE_NAME = "livespec_dev_tooling.cross_repo.master_health_flake_history"

_GATING_WORKFLOW = "CI"
_FLAKY_CHECK = "check-e2e-tmux failed"
_ORDINARY_SUBJECT = "docs(plan): an unrelated merge"


def _module() -> ModuleType:
    """Import the history read only after asserting its module exists."""
    assert _MODULE_PATH.is_file(), f"missing flake-history module: {_MODULE_PATH}"
    return importlib.import_module(_MODULE_NAME)


def _config(*, lookback: int) -> ReconcileConfig:
    """Committed configuration, varied only by how far back the rule may look."""
    return ReconcileConfig(
        target_branch="master",
        infra_outage_markers=("No runner matching",),
        gating_workflow=_GATING_WORKFLOW,
        unrelated_lookback_commits=lookback,
    )


def _commit(
    *,
    sha: str,
    parent_sha: str,
    conclusion: str,
    signature: str | None = None,
    pull_request: int | None = None,
) -> MasterCommit:
    return MasterCommit(
        sha=sha,
        parent_sha=parent_sha,
        pull_request=pull_request,
        ci_workflow=_GATING_WORKFLOW,
        ci_conclusion=conclusion,
        failure_signature=signature,
        subject=_ORDINARY_SUBJECT,
    )


def _recurring_window() -> ReconcileState:
    """Today's red, and the SAME check red three commits further back.

    The earlier red is a closed episode — green commits sit between it and the
    current one — which is the only shape in which the same signature appears
    outside the episode: inside a window, a red below a green is a previous
    episode of its own.
    """
    return ReconcileState(
        head_sha="e",
        commits=(
            _commit(sha="a", parent_sha="root", conclusion=CI_SUCCESS),
            _commit(sha="b", parent_sha="a", conclusion=CI_FAILURE, signature=_FLAKY_CHECK),
            _commit(sha="c", parent_sha="b", conclusion=CI_SUCCESS),
            _commit(sha="d", parent_sha="c", conclusion=CI_SUCCESS),
            _commit(
                sha="e",
                parent_sha="d",
                conclusion=CI_FAILURE,
                signature=_FLAKY_CHECK,
                pull_request=5200,
            ),
        ),
        rerun_outcome=RERUN_STILL_RED,
        revert_pull_request=None,
        open_needs_attention_episodes=(),
    )


def test_a_signature_that_also_failed_inside_the_lookback_window_is_recurring() -> None:
    """The read itself: three commits back is within a three-commit lookback."""
    module = _module()

    recurring = module.recurring_signatures(state=_recurring_window(), config=_config(lookback=3))

    assert recurring == frozenset({_FLAKY_CHECK})


def test_the_same_signature_beyond_the_lookback_window_is_not_recurring() -> None:
    """The bound, on the identical state: a shorter reach sees nothing.

    Without this the rule would be unbounded in effect, and a check name that
    failed long ago for an unrelated reason would exonerate every later
    regression that happens to fail the same check.
    """
    module = _module()

    recurring = module.recurring_signatures(state=_recurring_window(), config=_config(lookback=2))

    assert recurring == frozenset()


def test_a_green_branch_has_no_history_to_read() -> None:
    """With no episode there is nothing to compare, so the read is empty.

    Answering with the last commits of a green branch would be a different
    question than the one this module exists to ask.
    """
    module = _module()
    green = ReconcileState(
        head_sha="a",
        commits=(_commit(sha="a", parent_sha="root", conclusion=CI_SUCCESS),),
        rerun_outcome=RERUN_STILL_RED,
        revert_pull_request=None,
        open_needs_attention_episodes=(),
    )

    assert module.recurring_signatures(state=green, config=_config(lookback=5)) == frozenset()


def test_a_check_that_also_failed_on_an_unrelated_commit_is_infrastructure() -> None:
    """The acceptance assertion: classified as infrastructure, and no revert.

    INFRASTRUCTURE rather than a class of its own because the reconciler owes
    the same thing either way — a human, and no revert — and because the
    failure predates the culprit: whatever is wrong was already wrong, which is
    what "infrastructure" means here. The step is asserted beside the verdict
    because "no revert is opened" is a fact about the step, not the verdict.
    """
    state = _recurring_window()
    config = _config(lookback=3)

    assert red_verdict(state=state, config=config) == VERDICT_INFRA

    step = reconcile_step(state=state, config=config)

    assert step.kind == STEP_NEEDS_ATTENTION
    assert step.culprit_pull_request is None
    assert step.episode_key == "master@e"


def test_the_same_red_outside_the_lookback_is_still_a_revertable_regression() -> None:
    """The converse, so the rule cannot pass by exonerating everything.

    Same recorded window, same failing check, shorter lookback: the reconciler
    must still open the revert. A rule that classified this away would disarm
    revert-by-default for every repository with a long-lived check name.
    """
    state = _recurring_window()
    config = _config(lookback=2)

    assert red_verdict(state=state, config=config) == VERDICT_REGRESSION

    step = reconcile_step(state=state, config=config)

    assert step.kind == STEP_OPEN_REVERT
    assert step.culprit_pull_request == 5200
