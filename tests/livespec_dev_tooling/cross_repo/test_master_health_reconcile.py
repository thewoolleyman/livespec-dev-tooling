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
    STEP_RELEASE_REVERT,
    STEP_RERUN_FAILED_JOBS,
    reconcile_step,
)
from livespec_dev_tooling.cross_repo.master_health_state import (
    CI_FAILURE,
    CI_PENDING,
    CI_SUCCESS,
    RERUN_NOT_ATTEMPTED,
    RERUN_PASSED,
    RERUN_STILL_RED,
    MasterCommit,
    ReconcileConfig,
    ReconcileState,
    RevertPullRequest,
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


def _green_revert(*, number: int = 3001, claim: str | None = None) -> RevertPullRequest:
    return RevertPullRequest(
        number=number,
        reverts_pull_request=2917,
        ci_conclusion=CI_SUCCESS,
        auto_merge_armed=False,
        fix_forward_claim=claim,
    )


def test_a_flake_verdict_escalates_and_never_releases_an_open_green_revert() -> None:
    """The load-bearing ORDER test: classification outranks the open revert.

    A revert pull request is already open and its own CI is green, which is
    exactly the state the release branch acts on — so if the non-regression
    classes were matched AFTER that branch, this state would MERGE a revert for
    a failure the re-run already exonerated. Asserting the step here is
    asserting the shape of the table, not just one verdict's mapping.
    """
    state = ReconcileState(
        head_sha="35fea321",
        commits=_incident_state().commits,
        rerun_outcome=RERUN_PASSED,
        revert_pull_request=_green_revert(),
        open_needs_attention_episodes=(),
        unrelated_failure_signatures=(),
    )

    step = reconcile_step(state=state, config=_CONFIG)

    assert step.kind == STEP_NEEDS_ATTENTION
    assert step.episode_key == "master@35fea321"


def test_an_infrastructure_outage_escalates_rather_than_reverting() -> None:
    """No revert of any commit fixes a runner pool that has no runners."""
    state = ReconcileState(
        head_sha="35fea321",
        commits=(
            _commit(sha="parent0", parent_sha="root", conclusion=CI_SUCCESS),
            _commit(
                sha="35fea321",
                parent_sha="parent0",
                conclusion=CI_FAILURE,
                pull_request=2917,
                signature="No runner matching the specified labels was found",
            ),
        ),
        rerun_outcome=RERUN_STILL_RED,
        revert_pull_request=None,
        open_needs_attention_episodes=(),
        unrelated_failure_signatures=(),
    )

    step = reconcile_step(state=state, config=_CONFIG)

    assert step.kind == STEP_NEEDS_ATTENTION
    assert step.culprit_pull_request is None


def test_a_failure_seen_on_an_unrelated_commit_escalates_rather_than_reverting() -> None:
    """The culprit did not introduce it, so reverting the culprit cannot fix it."""
    state = ReconcileState(
        head_sha="35fea321",
        commits=_incident_state().commits,
        rerun_outcome=RERUN_STILL_RED,
        revert_pull_request=None,
        open_needs_attention_episodes=(),
        unrelated_failure_signatures=(_LINT_FAILURE,),
    )

    step = reconcile_step(state=state, config=_CONFIG)

    assert step.kind == STEP_NEEDS_ATTENTION
    assert step.episode_key == "master@35fea321"


def _still_red_with_revert(*, revert: RevertPullRequest) -> ReconcileState:
    """Master still red, the revert open but not yet landed — the real shape.

    The branch stays red until the revert actually merges, so this is the state
    every release decision is made in, not an artificial one.
    """
    return ReconcileState(
        head_sha="35fea321",
        commits=_incident_state().commits,
        rerun_outcome=RERUN_STILL_RED,
        revert_pull_request=revert,
        open_needs_attention_episodes=(),
        unrelated_failure_signatures=(),
    )


def test_a_held_revert_with_green_ci_and_no_claim_is_released_to_merge() -> None:
    """The acceptance assertion: green revert CI, nothing claimed, so release it.

    This is the step that actually returns the branch to green, and it names
    the revert pull request it releases so the caller arms auto-merge on that
    pull request rather than on whatever it last looked at.
    """
    step = reconcile_step(state=_still_red_with_revert(revert=_green_revert()), config=_CONFIG)

    assert step.kind == STEP_RELEASE_REVERT
    assert step.revert_pull_request == 3001
    assert step.auto_merge_held is False


def test_a_fix_forward_claim_holds_the_revert_rather_than_releasing_it() -> None:
    """A claim suspends the release, and C1 judges the claim no further.

    Whether a claimed fix-forward is making PROGRESS is child C2's decision
    with calibrated step durations behind it. C1 must therefore do the one
    thing that is safe without that calibration: hold, and take no step. A
    reconciler that released through a claim would make C2 unimplementable,
    because the revert would already have landed.
    """
    claimed = _green_revert(claim="fix-forward: #3100")

    step = reconcile_step(state=_still_red_with_revert(revert=claimed), config=_CONFIG)

    assert step.kind == STEP_NONE
    assert "claim" in step.reason


def test_a_revert_whose_own_ci_is_red_is_not_merged_and_escalates() -> None:
    """The acceptance assertion: a red revert CI is never merged.

    A revert whose own CI fails is evidence that reverting does NOT restore
    green — the branch is broken by something the culprit did not introduce, or
    the revert itself conflicts. Merging it would add a second broken commit to
    an already-broken branch, so the only safe step is to hand the episode to
    a human.
    """
    red_revert = RevertPullRequest(
        number=3001,
        reverts_pull_request=2917,
        ci_conclusion=CI_FAILURE,
        auto_merge_armed=False,
        fix_forward_claim=None,
    )

    step = reconcile_step(state=_still_red_with_revert(revert=red_revert), config=_CONFIG)

    assert step.kind == STEP_NEEDS_ATTENTION
    assert step.revert_pull_request == 3001
    assert step.episode_key == "master@35fea321"


def test_a_revert_whose_ci_has_not_concluded_is_not_merged_either() -> None:
    """Pending is not green, and must not be read as permission to merge.

    This is the same distinction the state vocabulary draws for the branch
    itself: only an explicit success reads as green. Treating "no conclusion
    yet" as mergeable would race the revert's own CI and defeat the hold.
    """
    pending_revert = RevertPullRequest(
        number=3001,
        reverts_pull_request=2917,
        ci_conclusion=CI_PENDING,
        auto_merge_armed=False,
        fix_forward_claim=None,
    )

    step = reconcile_step(state=_still_red_with_revert(revert=pending_revert), config=_CONFIG)

    assert step.kind == STEP_NEEDS_ATTENTION


def test_two_runs_against_one_state_decide_the_same_step() -> None:
    """Determinism is the first half of "takes the next step once".

    A duplicate run is harmless only if it cannot reach a DIFFERENT conclusion
    from the same truth. With no clock, no randomness and no stored cursor in
    the decision path, the step is a function of its inputs — asserted here so
    a future input that breaks it fails loudly.
    """
    state = _incident_state()

    assert reconcile_step(state=state, config=_CONFIG) == reconcile_step(
        state=state, config=_CONFIG
    )


def test_once_the_revert_exists_no_further_run_opens_a_second_one() -> None:
    """The acceptance assertion: a duplicate run never opens a second revert.

    This replays the state as it stands AFTER the open step has been applied —
    the revert is now in flight — and asserts the table no longer offers the
    open step. Nothing is deduplicated and no lock is held: the forge state the
    first run produced is itself what makes the second run decide differently,
    which is why a missed or duplicated run cannot wedge the loop.
    """
    after_open = _still_red_with_revert(revert=_green_revert())

    step = reconcile_step(state=after_open, config=_CONFIG)

    assert step.kind != STEP_OPEN_REVERT
    assert step.culprit_pull_request is None


def test_a_revert_already_armed_for_merge_is_not_released_a_second_time() -> None:
    """The same idempotence for the RELEASE step as for the open step.

    Without this the reconciler would re-release on every tick for the whole
    window between arming auto-merge and the merge actually landing — which at
    the plan's measured p90 master-CI duration of 10.5 minutes is many ticks of
    a 5-minute schedule, each one a redundant write.
    """
    armed = RevertPullRequest(
        number=3001,
        reverts_pull_request=2917,
        ci_conclusion=CI_SUCCESS,
        auto_merge_armed=True,
        fix_forward_claim=None,
    )

    step = reconcile_step(state=_still_red_with_revert(revert=armed), config=_CONFIG)

    assert step.kind == STEP_NONE
    assert step.revert_pull_request == 3001
