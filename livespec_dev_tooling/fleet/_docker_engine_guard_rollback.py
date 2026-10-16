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

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Protocol

from livespec_dev_tooling.fleet._docker_engine_guard_model import (
    GUARD_EXECUTABLE,
    GUARDED_UNITS,
    GuardOutcome,
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
    "PHASE_BODIES",
    "POSTCONDITIONS",
    "ROLLBACK_PHASE_ORDER",
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

# The specification's postcondition set, read as ONE record by the final
# check. Each name is the key the host answers under, and each is phrased
# as the property that must HOLD, so a failing one reads as the sentence
# an operator needs: "no docker0" failing says the bridge is still there.
POSTCONDITIONS: Final[tuple[str, ...]] = (
    "no start permission",
    "no socket, process, queued job or pending start for the guarded units",
    "each FORWARD policy as snapshotted",
    "no Docker rule",
    "no docker0",
    "each watched sysctl as snapshotted",
)


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


def phase_child_argv(*, run: str, env: GuardEnv, phase: str) -> tuple[str, ...]:
    """The command line the driver spawns for one phase.

    The state roots are FORWARDED rather than left to default: the
    disposable acceptance host is driven somewhere other than `/var/lib`
    and `/run`, and a child that read the real locations there would act
    on state no run of this guard owns. `--phase` comes last so the
    child's route reads it off the tail.
    """
    return (
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
    """
    read = env.host.read_postconditions(snapshot=env.paths.snapshot_dir(run=run))
    return tuple(name for name in POSTCONDITIONS if not read.get(name, False))


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
        _ = env.host.run_phase_child(argv=phase_child_argv(run=run, env=env, phase=phase))
    failed = _failed_postconditions(run=run, env=env)
    return GuardOutcome(
        operation="rollback",
        run=run,
        verdict=decision.verdict,
        reason=f"the rollback ran; these postconditions fail: {', '.join(failed) or 'none'}",
    )
