"""Classify a red episode: is it a regression a revert would actually fix?

Per `SPECIFICATION/contracts.md` section "Cross-repo coordination automation
surface", and the design recorded in this repository's
`plan/red-master-self-healing/research/001-charter-red-master-self-healing.md`
(child C1, work-item `livespec-dev-tooling-hrpcgl`).

THIS IS THE GUARD IN FRONT OF THE REVERT, and it is deliberately the only thing
standing there. Revert-by-default is what the current ci-gate-discipline
directive mandates, so the expensive mistake available to this module is not
failing to revert — it is reverting an innocent merge for a failure a revert
cannot fix. Three classes of red are therefore routed AWAY from the revert, and
each one alone is sufficient:

- FLAKE — the failed jobs passed when re-run once. The merge is exonerated by
  the forge itself.
- INFRA — the failure text names an outage from committed configuration (no
  runner matching the labels, bad credentials, a registry that is down). No
  revert of any commit fixes a broken runner pool.
- UNRELATED — the same failure signature is recorded OUTSIDE this episode, so
  the culprit did not introduce it.

INFRA AND UNRELATED ARE DECIDED BEFORE THE RE-RUN IS SPENT. That ordering is
not an optimisation. During a runner-pool outage a re-run CANNOT succeed, and
issuing one adds load to the component that is already broken — the charter
puts this reconciler on GitHub-hosted runners precisely because the self-hosted
pool can itself be the failure. So an episode that already names an outage is
classified immediately rather than after a round trip that is guaranteed to
come back red.

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
from livespec_dev_tooling.cross_repo.master_health_state import (
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
    "VERDICT_UNRELATED",
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
VERDICT_UNRELATED = "unrelated"
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


def red_verdict(*, state: ReconcileState, config: ReconcileConfig) -> str:
    """Classify the branch's current episode into exactly one verdict.

    Total over the recorded state, and ordered so that the two classes
    decidable without spending a re-run are reached first — see this module's
    docstring for why that ordering is load-bearing rather than incidental.
    """
    if not red_block(state=state):
        return VERDICT_GREEN

    signatures = _episode_signatures(state=state)
    if any(
        marker in signature for signature in signatures for marker in config.infra_outage_markers
    ):
        return VERDICT_INFRA
    if signatures & frozenset(state.unrelated_failure_signatures):
        return VERDICT_UNRELATED
    if state.rerun_outcome == RERUN_PASSED:
        return VERDICT_FLAKE
    if state.rerun_outcome == RERUN_NOT_ATTEMPTED:
        return VERDICT_UNCLASSIFIED
    return VERDICT_REGRESSION
