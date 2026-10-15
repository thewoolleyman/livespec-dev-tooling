"""Tests for `master_health_gating` — only the gating workflow starts an episode.

No I/O, no forge, no LLM: every state replayed here is a RECORDED GitHub state
built in-process (work-item `livespec-dev-tooling-zdqnr2`, the culprit-selection
calibration of child C1 in plan `red-master-self-healing`).

THE MEASURED SHAPE IS A NON-GATING WORKFLOW RED FOR DAYS. On 2026-10-15 this
repository carried a scheduled, non-gating workflow that had been failing for
days on an infrastructure fault while the gating workflow was green on every
master commit. A reconciler that read the newest failing run on the branch
would have opened a revert for a commit whose own gating CI never failed, so
the projection is replayed through `reconcile_step` as well as in isolation.

ONE SHA CARRIES TWO RECORDS IN EVERY STATE BELOW, on purpose. That is what a
gatherer reaching for each workflow's newest run per commit actually produces,
and it is the shape that breaks a by-sha index: the episode reader walks
`parent_sha` through such an index, so whichever record happens to land last
would otherwise decide whether master reads red.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from types import ModuleType

from livespec_dev_tooling.cross_repo.master_health_reconcile import (
    STEP_NONE,
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

_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / "livespec_dev_tooling"
    / "cross_repo"
    / "master_health_gating.py"
)
_MODULE_NAME = "livespec_dev_tooling.cross_repo.master_health_gating"

_GATING_WORKFLOW = "CI"
_LOOKBACK_COMMITS = 20
_SCHEDULED_WORKFLOW = "fleet-capacity-sweep"
_LINT_FAILURE = "check-lint failed"
_ORDINARY_SUBJECT = "feat(cross-repo): an ordinary merge"


def _module() -> ModuleType:
    """Import the projection only after asserting its module exists."""
    assert _MODULE_PATH.is_file(), f"missing gating projection module: {_MODULE_PATH}"
    return importlib.import_module(_MODULE_NAME)


def _config() -> ReconcileConfig:
    """Committed configuration naming the workflow whose gate job is required."""
    return ReconcileConfig(
        target_branch="master",
        infra_outage_markers=("No runner matching",),
        gating_workflow=_GATING_WORKFLOW,
        unrelated_lookback_commits=_LOOKBACK_COMMITS,
    )


def _commit(
    *,
    sha: str,
    parent_sha: str,
    workflow: str,
    conclusion: str,
    pull_request: int | None = None,
) -> MasterCommit:
    return MasterCommit(
        sha=sha,
        parent_sha=parent_sha,
        pull_request=pull_request,
        ci_workflow=workflow,
        ci_conclusion=conclusion,
        failure_signature=_LINT_FAILURE if conclusion == CI_FAILURE else None,
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


def _scheduled_red_window() -> ReconcileState:
    """Gating CI green on every commit; the scheduled sweep red on the head."""
    return _state(
        head_sha="b",
        commits=(
            _commit(sha="a", parent_sha="root", workflow=_GATING_WORKFLOW, conclusion=CI_SUCCESS),
            _commit(
                sha="b",
                parent_sha="a",
                workflow=_GATING_WORKFLOW,
                conclusion=CI_SUCCESS,
                pull_request=2920,
            ),
            _commit(
                sha="b",
                parent_sha="a",
                workflow=_SCHEDULED_WORKFLOW,
                conclusion=CI_FAILURE,
                pull_request=2920,
            ),
        ),
    )


def test_a_non_gating_workflow_record_is_dropped_from_the_recorded_window() -> None:
    """The projection keeps the gating verdicts and nothing else.

    Dropping rather than downgrading to undecided is the load-bearing half: an
    undecided record stays INSIDE the episode, so a non-gating failure would
    still hold the branch open for a culprit instead of leaving the gating
    verdict exactly as recorded.
    """
    module = _module()

    projected = module.gating_state(state=_scheduled_red_window(), config=_config())

    assert [commit.ci_workflow for commit in projected.commits] == [
        _GATING_WORKFLOW,
        _GATING_WORKFLOW,
    ]
    assert projected.head_sha == "b"


def test_a_non_gating_workflow_failure_never_starts_an_episode_or_names_a_culprit() -> None:
    """The acceptance assertion, read through the reconciler's own entry point.

    Only a failure of the gating workflow — the one whose all-green gate job is
    the required check — starts an episode. A scheduled sweep red for days is
    not a red master: branch protection never consulted it, so no merge was
    ever blocked by it and no revert can fix it.
    """
    step = reconcile_step(state=_scheduled_red_window(), config=_config())

    assert step.kind == STEP_NONE
    assert step.culprit_pull_request is None
    assert step.episode_key is None


def test_the_gating_workflows_own_failure_still_names_its_culprit() -> None:
    """The converse, so the projection cannot pass by muting everything.

    A non-gating SUCCESS record shares the head's sha here. Without the
    projection the by-sha index would answer with whichever of the two records
    landed last, and that record reading green is how a genuine red master
    would go unhealed — the same defect as the case above, in the opposite
    direction.
    """
    state = _state(
        head_sha="b",
        commits=(
            _commit(sha="a", parent_sha="root", workflow=_GATING_WORKFLOW, conclusion=CI_SUCCESS),
            _commit(
                sha="b",
                parent_sha="a",
                workflow=_GATING_WORKFLOW,
                conclusion=CI_FAILURE,
                pull_request=2920,
            ),
            _commit(
                sha="b",
                parent_sha="a",
                workflow=_SCHEDULED_WORKFLOW,
                conclusion=CI_SUCCESS,
                pull_request=2920,
            ),
        ),
    )

    step = reconcile_step(state=state, config=_config())

    assert step.kind == STEP_OPEN_REVERT
    assert step.culprit_pull_request == 2920
    assert step.culprit_sha == "b"
