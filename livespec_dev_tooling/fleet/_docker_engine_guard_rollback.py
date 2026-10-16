"""The Docker engine install guard's rollback driver.

`docker_engine_guard.py` reaches `run_rollback` here once its dispatch
table has decided that a rollback may proceed, so the driver lives beside
the guard rather than inside it.

Governing specification: `SPECIFICATION/non-functional-requirements.md`
section "Docker engine install guard", "Rollback" (this repository).
Governing design: `docs/docker-engine-guard-design.md` — F1's rollback,
R4's ordering, G5, H2's stop-first rule and H6's bounds.

Stdlib only, for the reason the model module records: these files are
copied onto the guarded host and run against its bare interpreter, so an
expected refusal is RETURNED in a `GuardOutcome` rather than raised.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Protocol

from livespec_dev_tooling.fleet._docker_engine_guard_model import (
    GUARD_EXECUTABLE,
    GUARDED_UNITS,
    GuardOutcome,
)
from livespec_dev_tooling.fleet._docker_engine_guard_postconditions import (
    BRIDGE_GONE,
    FORWARD_RESTORED,
    POSTCONDITIONS,
    RULES_GONE,
    SYSCTLS_MATCH,
    UNITS_QUIET,
)
from livespec_dev_tooling.fleet._docker_engine_guard_state import (
    read_phase,
    record_phase,
    write_durable,
)

if TYPE_CHECKING:
    from pathlib import Path

    from livespec_dev_tooling.fleet._docker_engine_guard_hostops import HostOps
    from livespec_dev_tooling.fleet._docker_engine_guard_model import Decision, Phase
    from livespec_dev_tooling.fleet._docker_engine_guard_state import GuardEnv

__all__: list[str] = [
    "MAX_ATTEMPTS",
    "PHASE_BODIES",
    "PHASE_BUDGET_SECONDS",
    "POSTCONDITIONS",
    "POSTCONDITION_OF_PHASE",
    "ROLLBACK_PHASE_ORDER",
    "deadman_timer_unit",
    "phase_child_argv",
    "run_phase",
    "run_rollback",
]

# The phases a run is already ON the rollback path in. A firing that
# arrives on one of them records nothing: the dead-man re-fires every 60
# seconds, so most firings land here, and re-recording `rolling-back`
# over a `rollback-partial` would erase the one record an operator reads
# while deciding whether the host needs a repair.
_ROLLBACK_PATH_PHASES: Final[tuple[Phase, ...]] = ("rolling-back", "rollback-partial")

# The two guard units that can still write to the Docker daemon when a
# rollback begins: the observer, which may hold an API request, and the
# starter, which may be mid-start. Both are fixed unit names (design I3),
# so the service manager refuses a second activation of either.
GUARD_OBSERVE_UNIT: Final[str] = "docker-engine-guard-observe.service"
GUARD_START_UNIT: Final[str] = "docker-engine-guard-start.service"

# How long each fenced unit gets between its SIGTERM and its SIGKILL.
FENCE_KILL_SECONDS: Final[int] = 10


def deadman_timer_unit(*, run: str) -> str:
    """This run's dead-man TIMER unit — the unit a finished driver stops.

    The timer, not the service: the service is what this driver is
    running inside, and stopping that would kill the firing before it
    recorded anything. `systemd-run --unit=docker-engine-deadman-<run>
    --on-active=…` creates both, which is why the suffix has to be
    spelled out rather than taken from the `--unit=` value.
    """
    return f"docker-engine-deadman-{run}.timer"


# The bounded wait on each `systemctl stop` a rollback phase issues. Every
# stop is bounded because a rollback that blocked on one would hold the
# lock until its own budget killed it, having run none of the later
# phases.
UNIT_STOP_SECONDS: Final[int] = 30

# The slice holding every container this run created. Killing BY CGROUP
# is what spares k3s: its containerd and every shim live in
# `k3s-agent.service` and the kubepods slices, never in these three, so
# no k3s process is reachable from the kill at all.
KILL_TARGETS: Final[tuple[str, ...]] = (
    "docker.service",
    "containerd.service",
    "fabro-sandbox.slice",
)

# What the bounded stop after the kill covers: the kill's three targets
# plus `docker.socket`, and the socket FIRST — a listening socket that
# outlived the service it activates would re-trigger a start.
STOP_AFTER_KILL: Final[tuple[str, ...]] = (
    "docker.socket",
    "docker.service",
    "containerd.service",
    "fabro-sandbox.slice",
)

# The specification's rollback order. Written out rather than derived
# from the budget table below, because the ORDER is a rule in its own
# right and a derived tuple would make a reordering invisible.
ROLLBACK_PHASE_ORDER: Final[tuple[str, ...]] = (
    "socket-stop",
    "job-cancel",
    "forward-restore",
    "cgroup-kill",
    "unit-disable",
    "footprint-removal",
    "interface-deletion",
    "sysctl-comparison",
)
# Each phase's own `timeout -k 10` bound, apportioned so the eight SUM
# to 600 of the rollback operation's 900-second budget. The remaining 300
# is what the lock wait and the final all-postconditions check run in,
# and that margin is the point: eight generously-bounded phases would
# leave the final check to be SIGKILLed by the rollback unit's own
# `TimeoutStartSec`, and a rollback killed before its final check writes
# no outcome at all.
#
# The apportionment is not flat, because the phases are not alike. The
# footprint phase parses and deletes rules in up to three passes with a
# per-command `iptables -w 5`, so it carries half the total; the cgroup
# kill waits on four bounded stops; the rest are single `systemctl` or
# `ip` calls and take the floor.
PHASE_BUDGET_SECONDS: Final[dict[str, int]] = {
    "socket-stop": 30,
    "job-cancel": 30,
    "forward-restore": 30,
    "cgroup-kill": 120,
    "unit-disable": 30,
    "footprint-removal": 300,
    "interface-deletion": 30,
    "sysctl-comparison": 30,
}

# How many times a phase may be ENTERED without a recorded success
# before later firings skip it. Three, so a phase whose child crashes
# the same way every time delays the later phases by at most three
# firings rather than forever; its postcondition is still read by every
# final check and still reported.
MAX_ATTEMPTS: Final[int] = 3

# What `timeout` is given between the SIGTERM at the budget and the
# SIGKILL that follows it, so a phase ignoring the first still ends.
PHASE_KILL_AFTER_SECONDS: Final[int] = 10

# Which postcondition each phase exists to establish, so the final check
# can make a phase eligible again when its own postcondition regresses.
#
# Four phases share `UNITS_QUIET` and that is not a modelling
# compromise: the check reads one record of the guarded units, so it
# genuinely cannot tell which of the four a regression belongs to, and
# re-running all four is the only sound answer. `PERMISSION_GONE` has no
# phase at all — the driver revokes the permission itself, in-process,
# before the phases — so a failing permission is retried by the next
# firing's revocation rather than by any phase, and the name is therefore
# not imported here.
POSTCONDITION_OF_PHASE: Final[dict[str, str]] = {
    "socket-stop": UNITS_QUIET,
    "job-cancel": UNITS_QUIET,
    "forward-restore": FORWARD_RESTORED,
    "cgroup-kill": UNITS_QUIET,
    "unit-disable": UNITS_QUIET,
    "footprint-removal": RULES_GONE,
    "interface-deletion": BRIDGE_GONE,
    "sysctl-comparison": SYSCTLS_MATCH,
}


@dataclass(frozen=True, kw_only=True)
class _PhaseContext:
    """Everything a rollback phase acts through, and nothing else.

    Narrower than the `GuardEnv` the driver holds, on purpose: a phase
    body reads no record, writes no phase and decides no admission — it
    takes one bounded host action and compares against one snapshot.
    """

    host: HostOps
    snapshot: Path


class _PhaseBody(Protocol):
    """What one rollback phase does, and what it hands back to report.

    The returned strings are the phase's FINDINGS — a residual rule, a
    deleted interface, a sysctl that no longer matches the snapshot. They
    are recorded rather than acted on: shared state is never written back
    blindly, because another actor may own the value now.
    """

    def __call__(self, *, context: _PhaseContext) -> tuple[str, ...]: ...


def _socket_stop(*, context: _PhaseContext) -> tuple[str, ...]:
    """Stop `docker.socket`, before anything stops `docker.service`.

    Load-bearing rather than tidy (design rider 1): a `Restart=` respawn
    does NOT re-evaluate `ConditionPathExists` on systemd 259, so a
    listening socket left in place would keep re-triggering starts that
    the revoked permission can no longer skip.
    """
    context.host.stop_unit(unit="docker.socket", timeout_seconds=UNIT_STOP_SECONDS)
    return ()


def _job_cancel(*, context: _PhaseContext) -> tuple[str, ...]:
    """Cancel the guarded units' queued jobs, by job id.

    Never a bare `systemctl cancel`, which cancels the WHOLE queue
    including k3s's own jobs. A queued start job is what would otherwise
    bring a daemon straight back the moment the kill finished.
    """
    guarded = set(GUARDED_UNITS)
    context.host.cancel_jobs(
        job_ids=tuple(job.job_id for job in context.host.queued_jobs() if job.unit in guarded)
    )
    return ()


def _forward_restore(*, context: _PhaseContext) -> tuple[str, ...]:
    """Put each address family's FORWARD policy back to its snapshot value.

    Early in the order because it is the ACCESS-relevant phase and takes
    milliseconds: a FORWARD policy left where Docker put it is the
    failure that would cost the maintainer the host.
    """
    context.host.restore_forward_policy(snapshot=context.snapshot)
    return ()


def _cgroup_kill(*, context: _PhaseContext) -> tuple[str, ...]:
    """SIGKILL by cgroup, then stop, and nothing outside those cgroups."""
    context.host.kill_cgroup(units=KILL_TARGETS)
    for unit in STOP_AFTER_KILL:
        context.host.stop_unit(unit=unit, timeout_seconds=UNIT_STOP_SECONDS)
    return ()


def _unit_disable(*, context: _PhaseContext) -> tuple[str, ...]:
    """Disable the three guarded units the package postinst enabled.

    Without this they stay enabled and condition-skipped: harmless while
    the permission is absent, and a pending start the postconditions
    would keep reporting.
    """
    context.host.disable_units(units=GUARDED_UNITS)
    return ()


def _footprint_removal(*, context: _PhaseContext) -> tuple[str, ...]:
    """Remove exactly Docker's rule footprint, and report any residue."""
    return context.host.remove_firewall_footprint(snapshot=context.snapshot)


def _interface_deletion(*, context: _PhaseContext) -> tuple[str, ...]:
    """Delete `docker0` and every veth mastered by it, and report what went."""
    return context.host.delete_bridge_interfaces()


def _sysctl_comparison(*, context: _PhaseContext) -> tuple[str, ...]:
    """Compare the watched sysctls with the snapshot and report each difference."""
    return context.host.compare_sysctls(snapshot=context.snapshot)


PHASE_BODIES: Final[dict[str, _PhaseBody]] = {
    "socket-stop": _socket_stop,
    "job-cancel": _job_cancel,
    "forward-restore": _forward_restore,
    "cgroup-kill": _cgroup_kill,
    "unit-disable": _unit_disable,
    "footprint-removal": _footprint_removal,
    "interface-deletion": _interface_deletion,
    "sysctl-comparison": _sysctl_comparison,
}


def _rollback_dir(*, run: str, env: GuardEnv) -> Path:
    """Where this run's rollback bookkeeping lives, beside its other records."""
    return env.paths.run_dir(run=run) / "rollback"


def _attempts(*, run: str, env: GuardEnv, phase: str) -> int:
    """How many times this phase has been ENTERED, across every firing.

    Absent reads as zero, which is the only safe reading: the record is
    written before the phase is entered, so no record means no entry.
    """
    record = _rollback_dir(run=run, env=env) / f"{phase}.attempts"
    return int(record.read_text(encoding="utf-8")) if record.is_file() else 0


def _record_attempt(*, run: str, env: GuardEnv, phase: str, attempts: int) -> None:
    """Advance this phase's attempt count durably, before the phase is entered."""
    write_durable(
        path=_rollback_dir(run=run, env=env) / f"{phase}.attempts",
        data=str(attempts + 1),
    )


def _clear_success(*, run: str, env: GuardEnv, phase: str) -> None:
    """Drop this phase's success record, so a later firing re-runs it."""
    (_rollback_dir(run=run, env=env) / f"{phase}.success").unlink(missing_ok=True)


def _succeeded(*, run: str, env: GuardEnv, phase: str) -> bool:
    """Whether this phase has a recorded success a later firing may trust."""
    return (_rollback_dir(run=run, env=env) / f"{phase}.success").is_file()


def _record_success(*, run: str, env: GuardEnv, phase: str) -> None:
    """Record that this phase's child completed, durably."""
    write_durable(path=_rollback_dir(run=run, env=env) / f"{phase}.success", data=phase)


def phase_child_argv(*, run: str, env: GuardEnv, phase: str) -> tuple[str, ...]:
    """The command line the driver spawns for one phase.

    `timeout -k 10 <budget>` is what makes a phase that hangs cost its
    own budget and nothing more: SIGTERM at the budget, SIGKILL ten
    seconds later, and a status back to the driver either way.

    The state roots are FORWARDED rather than left to default: the
    disposable acceptance host is driven somewhere other than `/var/lib`
    and `/run`, and a child that read the real locations there would act
    on state no run of this guard owns. `--phase` comes last so the
    child's route reads it off the tail.
    """
    return (
        "timeout",
        "-k",
        str(PHASE_KILL_AFTER_SECONDS),
        str(PHASE_BUDGET_SECONDS[phase]),
        str(GUARD_EXECUTABLE),
        "rollback",
        run,
        "--state-root",
        str(env.paths.state_root),
        "--runtime-root",
        str(env.paths.runtime_root),
        "--phase",
        phase,
    )


def run_phase(*, run: str, env: GuardEnv, phase: str) -> GuardOutcome:
    """Run ONE rollback phase, in the child process the driver spawned for it.

    A phase name outside the eight is an expected refusal RETURNED on the
    outcome, never a raise: this module runs on a bare host interpreter
    where the Result railway is not importable, so the outcome carries
    the refusal instead.
    """
    body = PHASE_BODIES.get(phase)
    if body is None:
        return GuardOutcome(
            operation="rollback",
            run=run,
            verdict="refuse",
            reason=f"{phase} is not one of this guard's rollback phases",
        )
    findings = body(context=_PhaseContext(host=env.host, snapshot=env.paths.snapshot_dir(run=run)))
    if findings:
        write_durable(
            path=_rollback_dir(run=run, env=env) / f"{phase}.findings",
            data="\n".join(findings),
        )
    return GuardOutcome(
        operation="rollback",
        run=run,
        verdict="proceed",
        reason=f"rollback phase {phase} ran",
    )


def _failed_postconditions(*, run: str, env: GuardEnv) -> tuple[str, ...]:
    """Every postcondition the final check finds failing, in specified order.

    Read as ONE record after every stop phase, and read FAIL-CLOSED: a
    postcondition the host did not answer at all counts as failing, so a
    narrowed or broken read reports a partial recovery rather than a
    clean one.

    Which makes the NAMES load-bearing, and is why they are imported
    from the module that answers under them rather than restated here: a
    second spelling of this set would not narrow the check, it would
    make every lookup miss and report a wholly rolled-back host as
    partial. That is exactly what two spellings did on 2026-10-16.
    """
    read = env.host.read_postconditions(snapshot=env.paths.snapshot_dir(run=run))
    return tuple(name for name in POSTCONDITIONS if not read.get(name, False))


def _final_check(*, run: str, env: GuardEnv) -> tuple[str, ...]:
    """Read every postcondition, and make each failing phase eligible again.

    A success record is what a later firing trusts to skip a phase, so a
    STALE one is the one way this driver could leave a host unrepaired
    while reporting that it had tried: the phase ran, something undid its
    work, and every firing after it skipped it. Clearing against this
    read closes that.
    """
    failed = _failed_postconditions(run=run, env=env)
    for phase in ROLLBACK_PHASE_ORDER:
        if POSTCONDITION_OF_PHASE[phase] in failed:
            _clear_success(run=run, env=env, phase=phase)
    return failed


def _record_outcome(*, run: str, env: GuardEnv, failed: tuple[str, ...]) -> Phase:
    """Write this firing's outcome — as the run's phase AND durably beside it.

    The phase is what every later operation dispatches on; the record is
    what a later `verify` and an operator read, and it carries the NAMES.
    "Something failed" does not support the decision an operator reaching
    a partial host has to make: a residual Docker rule, a surviving
    `docker0` and a sysctl that no longer matches the snapshot need three
    different repairs, and only the names tell them apart.

    `rolled-back` is FINAL: it makes every later dead-man firing a no-op
    and lets a later `reserve` take the host. Written while one
    postcondition still failed it would retire the dead-man over a host
    that still has a Docker rule or a `docker0`, and nothing would come
    back to look — which is why the partial outcome exists at all.
    """
    outcome: Phase = "rollback-partial" if failed else "rolled-back"
    write_durable(
        path=_rollback_dir(run=run, env=env) / "outcome.json",
        data=json.dumps({"outcome": outcome, "failed_postconditions": list(failed)}),
    )
    record_phase(paths=env.paths, run=run, phase=outcome)
    return outcome


def _fence_and_revoke(*, env: GuardEnv) -> None:
    """Stop both writers, then take the start permission back.

    The ORDER is the content of this step. Revoking first would leave a
    window in which an observer that has been told to stop, but is not
    yet inactive, submits one more Docker request against a daemon the
    revocation was meant to close; a `systemctl stop` returns only once
    the unit is inactive, so stopping first is what closes it. The
    revocation itself is what makes `Restart=always` unable to respawn
    the daemon, which is why nothing else may precede it either.
    """
    env.host.stop_unit(unit=GUARD_OBSERVE_UNIT, timeout_seconds=FENCE_KILL_SECONDS)
    env.host.stop_unit(unit=GUARD_START_UNIT, timeout_seconds=FENCE_KILL_SECONDS)
    env.host.revoke_start_permission()


def _deadman_is_done(*, run: str, env: GuardEnv, outcome: Phase) -> bool:
    """Whether the dead-man has nothing left to come back to this run for.

    Two ways that is true, and they are different reasons. A
    `rolled-back` run is finished: every postcondition holds, so a later
    firing would find nothing to do and the timer's own 60-second repeat
    would run forever over a recovered host.

    A `rollback-partial` run is finished too once no phase is left that
    a later firing WOULD enter — every phase either holding a success or
    having spent its three attempts. The run then rests at
    `rollback-partial` and waits for an operator: the defect is real,
    the record names it, and nothing automatic is going to fix it.
    """
    if outcome == "rolled-back":
        return True
    return not any(_enterable(run=run, env=env, phase=phase) for phase in ROLLBACK_PHASE_ORDER)


def _enterable(*, run: str, env: GuardEnv, phase: str) -> bool:
    """Whether a later firing would still ENTER this phase.

    The two skip rules of `_enter_phase`, read as a question rather than
    acted on, so the driver can ask what work is left without doing any.
    """
    return not _succeeded(run=run, env=env, phase=phase) and (
        _attempts(run=run, env=env, phase=phase) < MAX_ATTEMPTS
    )


def _enter_phase(*, run: str, env: GuardEnv, phase: str) -> None:
    """Record one attempt at `phase`, then spawn the child that runs it.

    Recording FIRST is what bounds a phase that keeps killing the driver:
    such a phase never returns to record anything, so an attempt written
    after the spawn would never be written for exactly the phase the
    budget exists to bound.

    Two kinds of phase are not entered at all, and NEITHER is hidden by
    that: each one's postcondition is still read by the final check and
    still named in the outcome, so skipping only decides what work a
    firing repeats, never what it reports.

    A phase holding a success is DONE. The final check clears the
    success of every phase whose postcondition failed, so a success that
    survived into this firing is the record of a postcondition that
    HELD — and re-running it would mean a `rollback-partial` host whose
    only defect is a `docker0` got its cgroups re-killed and its whole
    rule set re-parsed every 60 seconds, forever.

    A phase that has spent its attempts without ever succeeding is
    skipped for the opposite reason: it is not going to finish. Bounding
    it is what stops one crashing phase from standing between the
    dead-man and the later ones.
    """
    if not _enterable(run=run, env=env, phase=phase):
        return
    _record_attempt(
        run=run, env=env, phase=phase, attempts=_attempts(run=run, env=env, phase=phase)
    )
    if env.host.run_phase_child(argv=phase_child_argv(run=run, env=env, phase=phase)):
        _record_success(run=run, env=env, phase=phase)


def run_rollback(*, run: str, env: GuardEnv, decision: Decision) -> GuardOutcome:
    """Run every rollback phase for `run` and record its outcome.

    `decision` is the table's, already made under the lock: reaching here
    means the run is uncommitted and its phase admits a rollback.

    The phase record comes FIRST, before any other step. It is what
    closes the forward path — `start` and `confirm` are each allowed only
    from a phase this run no longer has — so recording it first is what
    makes a driver killed immediately afterwards leave a run nothing can
    carry forward, rather than one that was acted on and still looks
    startable. A run already on the rollback path keeps the phase it
    arrived with until this firing writes an outcome.
    """
    if read_phase(paths=env.paths, run=run) not in _ROLLBACK_PATH_PHASES:
        record_phase(paths=env.paths, run=run, phase="rolling-back")
    _fence_and_revoke(env=env)
    for phase in ROLLBACK_PHASE_ORDER:
        _enter_phase(run=run, env=env, phase=phase)
    failed = _final_check(run=run, env=env)
    outcome = _record_outcome(run=run, env=env, failed=failed)
    if _deadman_is_done(run=run, env=env, outcome=outcome):
        # LAST, after the outcome that earned it. The dead-man is the
        # only thing that comes back to a run on the rollback path — no
        # `confirm` is coming — so retiring it is safe exactly when
        # there is nothing left for a later firing to do.
        env.host.stop_unit(unit=deadman_timer_unit(run=run), timeout_seconds=UNIT_STOP_SECONDS)
    return GuardOutcome(
        operation="rollback",
        run=run,
        verdict=decision.verdict,
        reason=f"the rollback ran; these postconditions fail: {', '.join(failed) or 'none'}",
    )
