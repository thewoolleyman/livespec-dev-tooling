"""The Docker engine install guard's commit point, and the rule that guards it.

Governing specification: `SPECIFICATION/non-functional-requirements.md`
section "Docker engine install guard" -- "Commit" (this repository).
Governing design: `docs/docker-engine-guard-design.md`, F4, G2's
`confirm` and I2's `confirm` row.

Reached only through `docker_engine_guard.run_operation`, so the lock is
held, the run is the current reservation, the commit marker has been
read, and the dispatch table has already admitted the invocation --
from `observed` with an unexpired deadline when the marker is absent.
Nothing here re-decides any of that.

WHY THE REFUSALS ARE A FUNCTION RETURNING PROSE. Each clause of the
commit rule fails for a different reason, and the right next step
differs per clause: a stale challenge is answered by re-running the
observer, while evidence that recorded a failure must never be. On a
machine reachable only over Tailscale an unexplained refusal leaves an
operator with no move at all, so the clause that stopped the commit is
carried out in the refusal's own reason.

Stdlib only, for the reason the model module records.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from livespec_dev_tooling.fleet._docker_engine_guard_model import GuardOutcome
from livespec_dev_tooling.fleet._docker_engine_guard_records import (
    CHALLENGE_MAX_AGE_SECONDS,
    consumed_nonces,
    evidence_passed,
    owned_keys_digest,
    publish_marker,
    read_challenge,
    record_consumed_nonce,
    submitted_nonce,
)
from livespec_dev_tooling.fleet._docker_engine_guard_state import record_phase

if TYPE_CHECKING:
    from livespec_dev_tooling.fleet._docker_engine_guard_model import Decision
    from livespec_dev_tooling.fleet._docker_engine_guard_state import GuardEnv

__all__: list[str] = [
    "commit_refusal",
    "confirm",
]


def commit_refusal(*, run: str, env: GuardEnv, answer: str) -> str:
    """Why this `confirm` may not commit, or an empty string when it may.

    The clauses are read in the order that costs least and tells most.
    The evidence record comes first because a window that did not pass
    is not a timing problem an operator can retry; the challenge's
    provenance comes next, because a challenge from another boot is a
    different fault from a missing one; and the nonce comes last,
    because it is the only clause whose answer the controller chose.
    """
    if not evidence_passed(paths=env.paths, run=run):
        return "the run's evidence record does not record a passing observation window"
    challenge = read_challenge(paths=env.paths)
    if challenge is None or challenge.run != run or challenge.boot_id != env.host.boot_id():
        return "no challenge for this run was issued on this boot"
    if env.host.monotonic() - challenge.issued_monotonic > CHALLENGE_MAX_AGE_SECONDS:
        return f"the outstanding challenge is older than {CHALLENGE_MAX_AGE_SECONDS} seconds"
    if answer != challenge.nonce:
        return "the answer does not carry the nonce of the outstanding challenge"
    if answer in consumed_nonces(paths=env.paths, run=run):
        return "the answered nonce was already spent by an earlier confirm"
    return ""


def confirm(*, run: str, env: GuardEnv, decision: Decision) -> GuardOutcome:
    """Commit the run, or refuse and name the clause that stopped it.

    The marker is written BEFORE the phase moves, and that order is the
    whole of R1: the marker is what every later dispatch reads to learn
    whether the host is committed, so a phase recorded first would claim
    a commitment the host could not prove after a crash. The reverse
    order is safe -- a marker with no phase update is a committed run
    whose post-commit steps a later `confirm` simply repeats.
    """
    answer = submitted_nonce(paths=env.paths, run=run)
    refusal = commit_refusal(run=run, env=env, answer=answer)
    if refusal:
        return GuardOutcome(operation="confirm", run=run, verdict="refuse", reason=refusal)
    record_consumed_nonce(paths=env.paths, run=run, nonce=answer)
    publish_marker(paths=env.paths, run=run, digest=owned_keys_digest(paths=env.paths, run=run))
    record_phase(paths=env.paths, run=run, phase="committed")
    return GuardOutcome(
        operation="confirm", run=run, verdict=decision.verdict, reason="the run is committed"
    )
