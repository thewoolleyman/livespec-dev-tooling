"""Decide the ONE next step that heals a red branch, or that nothing is owed.

Per `SPECIFICATION/contracts.md` section "Cross-repo coordination automation
surface", and the design recorded in this repository's
`plan/red-master-self-healing/research/001-charter-red-master-self-healing.md`
(child C1, work-item `livespec-dev-tooling-hrpcgl`).

AT MOST ONE STEP PER RUN, AND GITHUB IS THE STATE. Every run recomputes the
step from current forge truth and performs a single transition. That is what
makes the reconciler safe under the failures it will actually meet: a crashed
run loses nothing (the next run reaches the same conclusion from the same
state), a MISSED run only delays the step, and a DUPLICATE run recomputes a
step that the first run's effect has already removed from the table. There is
no cursor, no checkpoint and no lock to go stale, because there is nothing
durable here to disagree with the forge.

OPENING AND RELEASING ARE SEPARATE STEPS ON PURPOSE. A revert is opened with
auto-merge HELD and released only once its own CI is green, so no single run
can both create a revert and land it. The hold is the gap in which
classification and the revert's own CI get to speak.

THE ORDER OF THE TABLE IS THE SAFETY ARGUMENT, not a style choice. A classified
non-regression is matched BEFORE any branch that could release a revert, so
"never merges a revert on a flake, an outage, or an unrelated failure" is a
property of the table's SHAPE rather than a rule each later branch has to
remember. A green branch is matched before the in-flight revert branch for the
same kind of reason: once the branch is healthy there is nothing to heal, and a
stale revert pull request is a human's to close rather than something for this
module to merge into a green branch.

WHERE IT REFUSES TO ACT. A regression whose culprit cannot be PROVEN (a
truncated window, an episode opening on an undecided run) or whose culprit has
no pull request to revert escalates to a needs-attention item instead. Those
are the states where acting would revert an innocent merge or hand-roll a
revert commit carrying none of the signing the server-side-revert exemption
looks for, and refusing is strictly better than guessing.

No LLM reaches any decision here: the step is a pure function of the recorded
state and committed configuration.
"""

from __future__ import annotations

from dataclasses import dataclass

from livespec_dev_tooling.cross_repo.master_health_episode import (
    culprit_commit,
    red_block,
)
from livespec_dev_tooling.cross_repo.master_health_state import (
    CI_SUCCESS,
    ReconcileConfig,
    ReconcileState,
    RevertPullRequest,
)
from livespec_dev_tooling.cross_repo.master_health_verdict import (
    VERDICT_FLAKE,
    VERDICT_GREEN,
    VERDICT_INFRA,
    VERDICT_UNCLASSIFIED,
    VERDICT_UNRELATED,
    red_verdict,
)

__all__: list[str] = [
    "NEEDS_ATTENTION_LABEL",
    "STEP_NEEDS_ATTENTION",
    "STEP_NONE",
    "STEP_OPEN_REVERT",
    "STEP_RELEASE_REVERT",
    "STEP_RERUN_FAILED_JOBS",
    "ReconcileStep",
    "episode_key",
    "reconcile_step",
]

# The fixed label the needs-attention issue carries. It is the JOIN between
# this producer and whatever reads the screen, so renaming it here silently
# empties that reader: a query for a label nothing carries returns no rows
# rather than an error. Same hazard the sibling `release_lane_issue` records.
NEEDS_ATTENTION_LABEL = "master-health-needs-attention"

STEP_NONE = "none"
STEP_RERUN_FAILED_JOBS = "rerun-failed-jobs"
STEP_OPEN_REVERT = "open-revert"
STEP_RELEASE_REVERT = "release-revert"
STEP_NEEDS_ATTENTION = "needs-attention"


@dataclass(frozen=True, kw_only=True)
class ReconcileStep:
    """The single next step one reconcile run would take, and why.

    `kind` is one of the five `STEP_*` constants. The remaining fields are the
    arguments that step needs, and each is `None` or `False` for the kinds that
    do not use it: `culprit_*` for the revert-opening step, `revert_pull_
    request` for the steps acting on a revert already in flight, and
    `episode_key` for the needs-attention step.

    `auto_merge_held` is `True` only on `STEP_OPEN_REVERT`. It is carried as
    data rather than left implicit so the caller that opens the pull request
    cannot arm auto-merge by omission.

    `reason` is operator-facing text naming WHY this step was chosen. It is
    part of the value because the step is often "do nothing", and a reader
    seeing no action needs to know which branch of the table produced it.
    """

    kind: str
    target_branch: str
    reason: str
    culprit_pull_request: int | None = None
    culprit_sha: str | None = None
    revert_pull_request: int | None = None
    auto_merge_held: bool = False
    episode_key: str | None = None


def episode_key(*, state: ReconcileState, config: ReconcileConfig) -> str | None:
    """A stable identifier for the branch's current red episode, or `None`.

    Keyed on the OLDEST commit in the red block, which is the one commit whose
    identity does not change as the episode grows: keying on the head would
    mint a new key — and so a second needs-attention issue — on every further
    merge into an already-red branch. This is what makes the issue
    one-per-episode rather than one-per-run.
    """
    block = red_block(state=state)
    if not block:
        return None
    return f"{config.target_branch}@{block[0].sha}"


def _revert_in_flight_step(
    *, revert: RevertPullRequest, config: ReconcileConfig, key: str | None
) -> ReconcileStep:
    """Decide what is owed to a revert pull request that is already open.

    Split from the table below because it is a genuinely different question —
    "what is owed to this revert" rather than "what is owed to this red
    branch" — and because it is the half that grows: every further rule about
    holding, releasing or escalating a revert belongs here, where the revert
    is in scope and the branch's verdict is not.
    """
    if revert.fix_forward_claim is not None:
        return ReconcileStep(
            kind=STEP_NONE,
            target_branch=config.target_branch,
            reason=(
                "a fix-forward claim holds this revert; judging the claim's "
                "progress is not this reconciler's decision"
            ),
            revert_pull_request=revert.number,
            episode_key=key,
        )
    # Only an explicit success reads as mergeable. A FAILING revert CI is
    # evidence that reverting does not restore green — the breakage is not the
    # culprit's, or the revert itself conflicts — and merging it would add a
    # second broken commit to an already-broken branch. A PENDING one has not
    # spoken yet, and reading silence as permission would race the revert's own
    # CI and defeat the hold.
    if revert.ci_conclusion != CI_SUCCESS:
        return ReconcileStep(
            kind=STEP_NEEDS_ATTENTION,
            target_branch=config.target_branch,
            reason=(
                f"revert CI is {revert.ci_conclusion}, not green; merge nothing "
                "and raise the episode for a human"
            ),
            revert_pull_request=revert.number,
            episode_key=key,
        )

    return ReconcileStep(
        kind=STEP_RELEASE_REVERT,
        target_branch=config.target_branch,
        reason="revert CI is green and nothing is claimed; release it to merge",
        revert_pull_request=revert.number,
        episode_key=key,
    )


def reconcile_step(*, state: ReconcileState, config: ReconcileConfig) -> ReconcileStep:
    """Choose this run's single step from recorded forge truth and config.

    Total over the recorded state. See this module's docstring for why the
    order of the branches below is the safety argument rather than a style
    choice.
    """
    verdict = red_verdict(state=state, config=config)
    key = episode_key(state=state, config=config)

    if verdict == VERDICT_GREEN:
        return ReconcileStep(
            kind=STEP_NONE,
            target_branch=config.target_branch,
            reason="branch is green; nothing to heal",
        )

    # Matched BEFORE any branch that can release a revert — see this module's
    # docstring. A revert may already be open and green here; escalating anyway
    # is the point, because the red this revert was opened for has since been
    # classified as something no revert fixes.
    if verdict in (VERDICT_FLAKE, VERDICT_INFRA, VERDICT_UNRELATED):
        return ReconcileStep(
            kind=STEP_NEEDS_ATTENTION,
            target_branch=config.target_branch,
            reason=(
                f"red classified as {verdict}, which no revert fixes; "
                "raise the episode for a human and merge nothing"
            ),
            episode_key=key,
        )

    # A revert already in flight OWNS the decision, and outranks the re-run
    # step: its existence means this episode is already past classification,
    # so re-running the culprit's jobs again would answer a question that has
    # been answered.
    revert = state.revert_pull_request
    if revert is not None:
        return _revert_in_flight_step(revert=revert, config=config, key=key)

    if verdict == VERDICT_UNCLASSIFIED:
        return ReconcileStep(
            kind=STEP_RERUN_FAILED_JOBS,
            target_branch=config.target_branch,
            reason="red but not yet classified; re-run the failed jobs once",
            episode_key=key,
        )

    culprit = culprit_commit(state=state)
    if culprit is None or culprit.pull_request is None:
        return ReconcileStep(
            kind=STEP_NEEDS_ATTENTION,
            target_branch=config.target_branch,
            reason=(
                "red is a regression but no revertable culprit is proven — the "
                "window is truncated, the episode opens on an undecided run, or "
                "the culprit was a direct push with no pull request"
            ),
            episode_key=key,
        )

    return ReconcileStep(
        kind=STEP_OPEN_REVERT,
        target_branch=config.target_branch,
        reason="regression with a proven culprit; open its revert with auto-merge held",
        culprit_pull_request=culprit.pull_request,
        culprit_sha=culprit.sha,
        auto_merge_held=True,
        episode_key=key,
    )
