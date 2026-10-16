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

from livespec_dev_tooling.fleet._docker_engine_guard_model import GuardOutcome
from livespec_dev_tooling.fleet._docker_engine_guard_state import (
    holder_of,
    read_reservation,
    record_phase,
    write_reservation,
)

if TYPE_CHECKING:
    from livespec_dev_tooling.fleet._docker_engine_guard_hostops import HostOps
    from livespec_dev_tooling.fleet._docker_engine_guard_model import Decision
    from livespec_dev_tooling.fleet._docker_engine_guard_state import GuardEnv

__all__: list[str] = [
    "reserve",
]

_QUIESCENT = "inactive"


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
