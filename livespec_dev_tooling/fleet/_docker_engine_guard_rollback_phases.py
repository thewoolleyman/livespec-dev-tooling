"""What ONE rollback phase of the Docker engine install guard DOES.

The driver next door in `_docker_engine_guard_rollback.py` decides WHICH
phases a firing enters, in what order, how many times and with what
budget; this module is the other half — the eight phase bodies
themselves and the one entry point a spawned phase child routes to. The
split follows the process boundary that already exists: each phase runs
in its OWN child process, so the body it executes shares nothing with
the driver's bookkeeping but the run's records.

Governing specification: `SPECIFICATION/non-functional-requirements.md`
section "Docker engine install guard", "Rollback" and "Host actions"
(this repository). Governing design: `docs/docker-engine-guard-design.md`
— R4's ordering, G5, H2's stop-first rule.

Stdlib only, for the reason the model module records: these files are
copied onto the guarded host and run against its bare interpreter, so an
expected refusal is RETURNED in a `GuardOutcome` rather than raised.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Protocol

from livespec_dev_tooling.fleet._docker_engine_guard_model import (
    GUARDED_UNITS,
    GuardOutcome,
)
from livespec_dev_tooling.fleet._docker_engine_guard_state import write_durable

if TYPE_CHECKING:
    from pathlib import Path

    from livespec_dev_tooling.fleet._docker_engine_guard_hostops import HostOps
    from livespec_dev_tooling.fleet._docker_engine_guard_state import GuardEnv

__all__: list[str] = [
    "KILL_TARGETS",
    "PHASE_BODIES",
    "STOP_AFTER_KILL",
    "UNIT_STOP_SECONDS",
    "run_phase",
]

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
            path=env.paths.rollback_dir(run=run) / f"{phase}.findings",
            data="\n".join(findings),
        )
    return GuardOutcome(
        operation="rollback",
        run=run,
        verdict="proceed",
        reason=f"rollback phase {phase} ran",
    )
