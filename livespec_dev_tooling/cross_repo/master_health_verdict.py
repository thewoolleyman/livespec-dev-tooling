"""Classify a red episode: is it a regression a revert would actually fix?

Per `SPECIFICATION/contracts.md` section "Master-health reconciler",
and the design recorded in this repository's
`plan/red-master-self-healing/research/001-charter-red-master-self-healing.md`
(child C1, work-item `livespec-dev-tooling-hrpcgl`).

THIS IS THE GUARD IN FRONT OF THE REVERT, and it is deliberately the only thing
standing there. Revert-by-default is what the current ci-gate-discipline
directive mandates, so the expensive mistake available to this module is not
failing to revert — it is reverting an innocent merge for a failure a revert
cannot fix. Two classes of red are therefore routed AWAY from the revert, and
each one alone is sufficient:

- FLAKE — the failed jobs passed when re-run once. The merge is exonerated by
  the forge itself.
- INFRA — whatever is wrong was ALREADY wrong, by either of two independent
  readings: the failure text names an outage from committed configuration (no
  runner matching the labels, bad credentials, a registry that is down), or the
  same failing check is recorded BELOW this episode inside the configured
  lookback (`master_health_flake_history`). No revert of any commit fixes a
  broken runner pool, and none fixes a check that was already failing when the
  culprit landed.

THE SECOND READING USED TO BE A VERDICT OF ITS OWN, `UNRELATED`. It was folded
into `INFRA` because both answers owe the reconciler the identical step — a
human, and no revert — and a separate verdict for an identical consequence
invites a later branch to treat the two differently for a reason nobody
recorded. The evidence also changed shape: it is read from the recorded commit
window and bounded by committed configuration, rather than taken from a
gatherer's summary that carried no distance.

INFRA IS DECIDED BEFORE THE RE-RUN IS SPENT. That ordering is not an
optimisation. During a runner-pool outage a re-run CANNOT succeed, and issuing
one adds load to the component that is already broken — the charter puts this
reconciler on GitHub-hosted runners precisely because the self-hosted pool can
itself be the failure. So an episode that already names an outage, or that is
failing a check it was failing before, is classified immediately rather than
after a round trip that is guaranteed to come back red.

UNCLASSIFIED IS NOT A REGRESSION. An episode whose jobs have not been re-run
yet is held at `UNCLASSIFIED`, which is what keeps "re-run once" a step the
reconciler must still TAKE rather than a fact it assumes it has established.
Collapsing the two would revert on first sight of red, which is exactly the
behaviour the flake class exists to prevent.

No LLM reaches this decision: the outage markers are committed text matched as
substrings, never a model's reading of a failure log.
"""

from __future__ import annotations

from livespec_dev_tooling.cross_repo.master_health_episode import red_block
from livespec_dev_tooling.cross_repo.master_health_flake_history import recurring_signatures
from livespec_dev_tooling.cross_repo.master_health_state import (
    CI_FAILURE,
    RERUN_NOT_ATTEMPTED,
    RERUN_PASSED,
    ReconcileConfig,
    ReconcileState,
)

__all__: list[str] = [
    "VERDICT_FLAKE",
    "VERDICT_GREEN",
    "VERDICT_INFRA",
    "VERDICT_REGRESSION",
    "VERDICT_UNCLASSIFIED",
    "red_verdict",
]

# `GREEN` and `UNCLASSIFIED` are separate values because they route
# differently: the first means there is nothing to do, the second means a
# re-run is still owed. A single "not a regression" value would merge a healthy
# branch with an unmeasured one.
VERDICT_GREEN = "green"
VERDICT_UNCLASSIFIED = "unclassified"
VERDICT_FLAKE = "flake"
VERDICT_INFRA = "infra"
VERDICT_REGRESSION = "regression"


def _episode_signatures(*, state: ReconcileState) -> frozenset[str]:
    """The failure signatures recorded inside the current red episode.

    Commits with no signature are DROPPED rather than contributing an empty
    string. An undecided run (cancelled, still pending) carries no failure
    text, and an empty signature would match every outage marker as a
    substring — turning a cancelled run into a spurious infra verdict.
    """
    return frozenset(
        commit.failure_signature
        for commit in red_block(state=state)
        if commit.failure_signature is not None
    )


def _names_an_outage(*, signatures: frozenset[str], config: ReconcileConfig) -> bool:
    """Whether any signature in the episode contains a committed outage marker."""
    return any(
        marker in signature for signature in signatures for marker in config.infra_outage_markers
    )


def red_verdict(*, state: ReconcileState, config: ReconcileConfig) -> str:
    """Classify the branch's current episode into exactly one verdict.

    Total over the recorded state, and ordered so that the class decidable
    without spending a re-run is reached first — see this module's docstring
    for why that ordering is load-bearing rather than incidental.
    """
    if not any(commit.ci_conclusion == CI_FAILURE for commit in red_block(state=state)):
        return VERDICT_GREEN

    signatures = _episode_signatures(state=state)
    if _names_an_outage(signatures=signatures, config=config) or signatures & recurring_signatures(
        state=state, config=config
    ):
        return VERDICT_INFRA
    if state.rerun_outcome == RERUN_PASSED:
        return VERDICT_FLAKE
    if state.rerun_outcome == RERUN_NOT_ATTEMPTED:
        return VERDICT_UNCLASSIFIED
    return VERDICT_REGRESSION
