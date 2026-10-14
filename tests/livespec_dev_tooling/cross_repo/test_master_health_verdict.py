"""Tests for `master_health_verdict` — is this red master a genuine regression?

No I/O, no forge, no LLM: every state replayed here is a RECORDED GitHub state
built in-process (work-item `livespec-dev-tooling-hrpcgl`, child C1 of plan
`red-master-self-healing`).

THE THREE NON-REGRESSION CLASSES EACH GET THEIR OWN TEST because each one on
its own must be enough to stop a revert. The acceptance assertion is a
disjunction — passes on re-run, OR appears on an unrelated commit, OR names an
infrastructure outage — and a disjunction tested only through its first branch
is three rules with one rule's worth of evidence.
"""

from __future__ import annotations

from livespec_dev_tooling.cross_repo.master_health_state import (
    CI_CANCELLED,
    CI_FAILURE,
    CI_SUCCESS,
    RERUN_NOT_ATTEMPTED,
    RERUN_PASSED,
    RERUN_STILL_RED,
    MasterCommit,
    ReconcileConfig,
    ReconcileState,
)
from livespec_dev_tooling.cross_repo.master_health_verdict import (
    VERDICT_FLAKE,
    VERDICT_GREEN,
    VERDICT_INFRA,
    VERDICT_REGRESSION,
    VERDICT_UNCLASSIFIED,
    VERDICT_UNRELATED,
    red_verdict,
)

_LINT_FAILURE = "check-lint failed"
_NO_RUNNERS = "No runner matching the specified labels was found"

_CONFIG = ReconcileConfig(
    target_branch="master",
    infra_outage_markers=("No runner matching", "registry down", "bad credentials"),
)


def _commit(
    *,
    sha: str,
    parent_sha: str,
    conclusion: str,
    signature: str | None = None,
) -> MasterCommit:
    return MasterCommit(
        sha=sha,
        parent_sha=parent_sha,
        pull_request=101,
        ci_conclusion=conclusion,
        failure_signature=signature,
    )


def _red_state(
    *,
    rerun_outcome: str = RERUN_STILL_RED,
    signature: str | None = _LINT_FAILURE,
    unrelated: tuple[str, ...] = (),
    head_conclusion: str = CI_FAILURE,
) -> ReconcileState:
    """A one-commit red episode on a green parent, varied by the kwargs."""
    return ReconcileState(
        head_sha="bbb",
        commits=(
            _commit(sha="aaa", parent_sha="root", conclusion=CI_SUCCESS),
            _commit(sha="bbb", parent_sha="aaa", conclusion=head_conclusion, signature=signature),
        ),
        rerun_outcome=rerun_outcome,
        revert_pull_request=None,
        open_needs_attention_episodes=(),
        unrelated_failure_signatures=unrelated,
    )


def test_a_failure_that_passes_on_re_run_is_a_flake() -> None:
    """First of the three non-regression classes: the re-run came back green."""
    state = _red_state(rerun_outcome=RERUN_PASSED)

    assert red_verdict(state=state, config=_CONFIG) == VERDICT_FLAKE


def test_a_failure_naming_an_outage_marker_is_infra_without_spending_a_re_run() -> None:
    """Second class, and it is decided BEFORE the re-run on purpose.

    During a runner-pool outage a re-run cannot succeed and only adds load to
    the thing that is already broken, so the marker short-circuits it. The
    `rerun_outcome` here is deliberately NOT_ATTEMPTED to pin that ordering.
    """
    state = _red_state(rerun_outcome=RERUN_NOT_ATTEMPTED, signature=_NO_RUNNERS)

    assert red_verdict(state=state, config=_CONFIG) == VERDICT_INFRA


def test_a_failure_also_seen_on_an_unrelated_commit_is_not_this_merges_fault() -> None:
    """Third class: the same signature is recorded outside this episode.

    A revert cannot fix a failure the culprit did not introduce, so this is
    classified away from regression even though the re-run stayed red.
    """
    state = _red_state(unrelated=(_LINT_FAILURE,))

    assert red_verdict(state=state, config=_CONFIG) == VERDICT_UNRELATED


def test_still_red_on_re_run_with_no_exonerating_evidence_is_a_regression() -> None:
    """The one verdict that authorizes opening a revert."""
    state = _red_state()

    assert red_verdict(state=state, config=_CONFIG) == VERDICT_REGRESSION


def test_an_un_rerun_failure_is_unclassified_rather_than_a_regression() -> None:
    """Absence of evidence is not a regression verdict.

    This is what keeps the re-run a step the reconciler still has to take,
    rather than a fact it is assumed to have established.
    """
    state = _red_state(rerun_outcome=RERUN_NOT_ATTEMPTED)

    assert red_verdict(state=state, config=_CONFIG) == VERDICT_UNCLASSIFIED


def test_a_green_branch_is_its_own_verdict_not_an_unclassified_red() -> None:
    """Totality: the classifier answers for a healthy branch too.

    `GREEN` rather than `UNCLASSIFIED` because the two route differently — one
    means nothing to do, the other means a re-run is owed.
    """
    state = _red_state(head_conclusion=CI_SUCCESS, signature=None)

    assert red_verdict(state=state, config=_CONFIG) == VERDICT_GREEN


def test_an_undecided_run_contributes_no_signature_to_the_classification() -> None:
    """A cancelled commit inside the episode carries no failure text.

    It must not be read as an empty signature that matches an outage marker by
    accident, which is how a substring rule over `None` would behave if the
    filter were dropped.
    """
    state = ReconcileState(
        head_sha="ccc",
        commits=(
            _commit(sha="aaa", parent_sha="root", conclusion=CI_SUCCESS),
            _commit(sha="bbb", parent_sha="aaa", conclusion=CI_CANCELLED),
            _commit(sha="ccc", parent_sha="bbb", conclusion=CI_FAILURE, signature=_LINT_FAILURE),
        ),
        rerun_outcome=RERUN_STILL_RED,
        revert_pull_request=None,
        open_needs_attention_episodes=(),
        unrelated_failure_signatures=(),
    )

    assert red_verdict(state=state, config=_CONFIG) == VERDICT_REGRESSION
