"""The Docker engine install guard operations child 1a implements.

`reserve`, `publish`, `arm`, `start` and `recover`. Each is reached only
through `docker_engine_guard.run_operation`, so each is already under the
lock, already confirmed to be on the current reservation, and already
admitted by its dispatch-table row: nothing here re-decides admission,
and nothing here takes a lock.

Governing specification: `SPECIFICATION/non-functional-requirements.md`
section "Docker engine install guard". Stdlib only, for the reason the
model module records.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from livespec_dev_tooling.fleet._docker_engine_guard_model import (
    Deadline,
    GuardOutcome,
    deadline_seconds,
    deadman_argv,
    rollback_argv,
)
from livespec_dev_tooling.fleet._docker_engine_guard_state import (
    holder_of,
    read_deadline,
    read_reservation,
    record_phase,
    write_deadline,
    write_durable,
    write_reservation,
)

if TYPE_CHECKING:
    from livespec_dev_tooling.fleet._docker_engine_guard_hostops import HostOps
    from livespec_dev_tooling.fleet._docker_engine_guard_model import Decision
    from livespec_dev_tooling.fleet._docker_engine_guard_state import GuardEnv

__all__: list[str] = [
    "arm",
    "publish",
    "reserve",
]

_QUIESCENT = "inactive"

# Written inside the run's snapshot directory once the host snapshot has
# COMPLETED, so a resumed publish can tell "already snapshotted" from
# "interrupted part way through snapshotting".
_SNAPSHOT_TAKEN = "taken"


def _busy_guard_units(*, host: HostOps) -> tuple[str, ...]:
    """Guard units that are not quiescent, excluding this invocation's own.

    Quiescent means `inactive` WITH NO QUEUED JOB: a unit that is
    inactive but has a start job queued is about to run, and admitting a
    new reservation beside it is the race single-flight exists to
    prevent. `failed` is not `inactive` either, and naming it matters —
    a failed dead-man service means a rollback was attempted and did not
    finish.

    The invoking unit is excluded because it is necessarily active: it
    is the one running this check.
    """
    invoking = host.invoking_unit()
    queued = {job.unit for job in host.queued_jobs()}
    states = host.guard_unit_states()
    return tuple(
        unit
        for unit in sorted(states)
        if unit != invoking and (states[unit] != _QUIESCENT or unit in queued)
    )


def reserve(*, run: str, env: GuardEnv, decision: Decision) -> GuardOutcome:
    """Take the host's one reservation for `run`, or refuse and say what holds it.

    The dispatch table has already established the two durable halves of
    design I1 — no commit marker, and no current reservation that is not
    `rolled-back`. The two LIVE halves are checked here, because both are
    facts about the host right now rather than about its records: no
    guard unit still running, and nobody in the `docker` group who could
    reach the API the moment the socket appears.
    """
    busy = _busy_guard_units(host=env.host)
    if busy:
        return GuardOutcome(
            operation="reserve",
            run=run,
            verdict="refuse",
            reason="a guard unit is not quiescent, so an earlier run may still be acting",
            holder=holder_of(env=env, run=read_reservation(paths=env.paths)),
            blocking_units=busy,
        )
    members = env.host.docker_group_members()
    if members:
        return GuardOutcome(
            operation="reserve",
            run=run,
            verdict="refuse",
            reason=f"these accounts are in the docker group and could reach the API: {members}",
        )
    write_reservation(paths=env.paths, run=run)
    env.paths.inputs_dir(run=run).mkdir(parents=True, exist_ok=True)
    record_phase(paths=env.paths, run=run, phase="reserved")
    return GuardOutcome(
        operation="reserve", run=run, verdict=decision.verdict, reason="reservation taken"
    )


def publish(*, run: str, env: GuardEnv, decision: Decision) -> GuardOutcome:
    """Snapshot the host once, install the audited set inert, and prove it cannot start.

    The ORDER is the whole content of this operation. The phase reaches
    `publishing` first, so an install interrupted anywhere is a run a
    later `recover` can resume rather than a run that looks untouched.
    The snapshot is taken before the first package step and never
    retaken, because it is what a rollback compares against: taken after
    a package step it would record Docker's own footprint as the host's
    baseline, and the cleanup could no longer tell the two apart. And
    `published` is reached only once the post-install condition check
    has passed — that check is the proof the installed units cannot
    start, so arming over a run that skipped it would arm over an engine
    free to start on its own.
    """
    record_phase(paths=env.paths, run=run, phase="publishing")
    taken = env.paths.snapshot_dir(run=run) / _SNAPSHOT_TAKEN
    if not taken.is_file():
        env.host.take_snapshot(destination=env.paths.snapshot_dir(run=run))
        # Written only AFTER the host returns, so a snapshot interrupted
        # half way is retaken rather than trusted.
        write_durable(path=taken, data=run)
    env.host.install_packages(inputs=env.paths.inputs_dir(run=run))
    if not env.host.condition_check_passed():
        return GuardOutcome(
            operation="publish",
            run=run,
            verdict="refuse",
            reason="the installed units' effective conditions are not the guard's two",
        )
    record_phase(paths=env.paths, run=run, phase="published")
    return GuardOutcome(
        operation="publish", run=run, verdict=decision.verdict, reason="inert install published"
    )


def arm(*, run: str, env: GuardEnv, decision: Decision) -> GuardOutcome:
    """Record the run's deadline and put its dead-man in the air.

    The docker-group check is repeated here and NOT as a formality: the
    package step created the group, so this is the first moment the
    check can see what the install made. A member of it is a second
    party on the Docker API, and the run is rolled back rather than
    merely stopped, because the inert install is already on the host.

    The deadline is read before it is written, so a retried `arm` keeps
    the instant the run was first given — an arm that re-recorded it
    would let a run buy itself unlimited time by retrying, which is the
    one failure a dead-man cannot have. For the same reason the timer's
    `--on-active` is the interval REMAINING to that instant, recomputed
    now, rather than the full interval over again.
    """
    members = env.host.docker_group_members()
    if members:
        # The lock is held by this invocation, so the rollback entry
        # cannot be called in-process without deadlocking on it; it is
        # started as its own transient unit instead, exactly as the
        # observer starts one on a failed sample.
        env.host.systemd_run(argv=rollback_argv(run=run))
        return GuardOutcome(
            operation="arm",
            run=run,
            verdict="refuse",
            reason=f"the install created the docker group and these accounts are in it: {members}",
        )
    deadline = read_deadline(paths=env.paths, run=run)
    if deadline is None:
        deadline = Deadline(
            boot_id=env.host.boot_id(),
            monotonic=env.host.monotonic() + deadline_seconds(window_seconds=env.window_seconds),
        )
        write_deadline(paths=env.paths, run=run, deadline=deadline)
    if not env.host.deadman_timer_exists(run=run):
        remaining = max(1, round(deadline.monotonic - env.host.monotonic()))
        env.host.systemd_run(argv=deadman_argv(run=run, on_active_seconds=remaining))
    record_phase(paths=env.paths, run=run, phase="armed")
    return GuardOutcome(operation="arm", run=run, verdict=decision.verdict, reason="dead-man armed")
