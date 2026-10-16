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

from typing import TYPE_CHECKING, Final

from livespec_dev_tooling.fleet._docker_engine_guard_model import (
    GUARDED_UNITS,
    UNIT_WAIT_SECONDS,
    GuardOutcome,
)
from livespec_dev_tooling.fleet._docker_engine_guard_records import (
    CHALLENGE_MAX_AGE_SECONDS,
    consumed_nonces,
    evidence_passed,
    marker_digest,
    owned_keys_digest,
    publish_marker,
    read_challenge,
    record_consumed_nonce,
    record_durability_warning,
    submitted_nonce,
)
from livespec_dev_tooling.fleet._docker_engine_guard_state import read_marker, record_phase

if TYPE_CHECKING:
    from livespec_dev_tooling.fleet._docker_engine_guard_model import Decision
    from livespec_dev_tooling.fleet._docker_engine_guard_state import GuardEnv

__all__: list[str] = [
    "commit_refusal",
    "committed_installation_fault",
    "confirm",
    "deadman_timer_unit",
]

# What the post-commit validation requires of each guarded unit, and it
# requires BOTH: enablement carries the engine across the next boot, the
# active state says it is running now, and neither implies the other.
_ENABLED: Final[str] = "enabled"
_ACTIVE: Final[str] = "active"


def deadman_timer_unit(*, run: str) -> str:
    """The transient TIMER unit `arm` put in the air for this run.

    A timer, not its service, and stopped rather than disabled: a
    transient unit cannot be disabled at all, so `systemctl disable` on
    it is an error rather than a no-op (design G5).
    """
    return f"docker-engine-deadman-{run}.timer"


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


def _committed_reason(*, warning: str) -> str:
    """The committed outcome's reason, carrying a durability warning if there is one."""
    return f"the run is committed; {warning}" if warning else "the run is committed"


def committed_installation_fault(*, run: str, env: GuardEnv) -> str:
    """What is wrong with the committed installation, or an empty string.

    Read AFTER the post-commit steps, because it is their only proof.
    Enabling and starting a unit says what was ASKED for; it does not say
    the engine came up. And on a committed host nothing else is watching
    any more -- the dead-man has been stopped, by design, because a
    committed run must never be rolled back -- so this read is the one
    thing left that can notice a committed host whose engine is not
    actually running.

    It REPORTS and never acts. A validation that undid what it found
    would roll back a commitment the guarded units' start condition
    already honours, which is the one move design F4 forbids outright.
    """
    enabled = env.host.unit_enabled_states()
    active = env.host.guard_unit_states()
    adrift = tuple(
        unit
        for unit in GUARDED_UNITS
        if enabled.get(unit) != _ENABLED or active.get(unit) != _ACTIVE
    )
    if adrift:
        return f"these guarded units are not both enabled and running: {', '.join(adrift)}"
    recorded = marker_digest(paths=env.paths)
    if read_marker(paths=env.paths, run=run) == "self" and recorded == owned_keys_digest(
        paths=env.paths, run=run
    ):
        return ""
    return (
        "the commit marker does not name this run with the owned keys' digest; "
        f"it holds {recorded!r}"
    )


def _finish(*, run: str, env: GuardEnv, decision: Decision, warning: str) -> GuardOutcome:
    """The post-commit steps, in the order the specification sets them.

    Every one is idempotent, which is what lets a `confirm` that died
    anywhere past the commit rename simply be run again -- and what lets
    a `confirm` for a run the marker already names repeat them with no
    challenge at all.

    The start permission goes FIRST, and that is safe only here: the
    marker is already visible, so the guarded units' start condition is
    satisfied by it from this point on and removing the tmpfs permission
    takes nothing away. The units are enabled AND started (rider point
    9) -- enabling carries the engine across the next boot, starting
    carries it across this one, and an enabled-but-stopped Docker on a
    committed host is an engine that only comes back at a reboot. The
    dead-man is stopped last, because until it is, a run that died mid
    way would be rolled back by it, and a committed run must never be.
    The validation comes after all of them, because it is their proof.
    """
    record_phase(paths=env.paths, run=run, phase="committed")
    env.host.revoke_start_permission()
    env.host.enable_units(units=GUARDED_UNITS)
    for unit in GUARDED_UNITS:
        env.host.start_unit(unit=unit, timeout_seconds=UNIT_WAIT_SECONDS)
    env.host.stop_unit(unit=deadman_timer_unit(run=run), timeout_seconds=UNIT_WAIT_SECONDS)
    record_phase(paths=env.paths, run=run, phase="confirmed")
    fault = committed_installation_fault(run=run, env=env)
    if fault:
        return GuardOutcome(operation="confirm", run=run, verdict="refuse", reason=fault)
    return GuardOutcome(
        operation="confirm",
        run=run,
        verdict=decision.verdict,
        reason=_committed_reason(warning=warning),
    )


def confirm(*, run: str, env: GuardEnv, decision: Decision) -> GuardOutcome:
    """Commit the run, or refuse and name the clause that stopped it.

    A `finish` verdict means the commit marker already names this run,
    so the run is committed whatever its phase reads and there is
    nothing left to prove: it goes straight to the post-commit steps,
    with no challenge and no evidence read. Demanding either would
    refuse a host that is already committed -- and after the reboot that
    case models, /run is tmpfs and no challenge exists at all.

    Otherwise the marker is written BEFORE the phase moves, and that order is the
    whole of R1: the marker is what every later dispatch reads to learn
    whether the host is committed, so a phase recorded first would claim
    a commitment the host could not prove after a crash. The reverse
    order is safe -- a marker with no phase update is a committed run
    whose post-commit steps a later `confirm` simply repeats.
    """
    if decision.verdict == "finish":
        return _finish(run=run, env=env, decision=decision, warning="")
    answer = submitted_nonce(paths=env.paths, run=run)
    refusal = commit_refusal(run=run, env=env, answer=answer)
    if refusal:
        return GuardOutcome(operation="confirm", run=run, verdict="refuse", reason=refusal)
    record_consumed_nonce(paths=env.paths, run=run, nonce=answer)
    failure = publish_marker(
        paths=env.paths, run=run, digest=owned_keys_digest(paths=env.paths, run=run)
    )
    if read_marker(paths=env.paths, run=run) != "self":
        return GuardOutcome(
            operation="confirm",
            run=run,
            verdict="refuse",
            reason=f"the commit marker is not in place, so this run is not committed: {failure}",
        )
    return _finish(
        run=run,
        env=env,
        decision=decision,
        warning=record_durability_warning(paths=env.paths, run=run, failure=failure),
    )
