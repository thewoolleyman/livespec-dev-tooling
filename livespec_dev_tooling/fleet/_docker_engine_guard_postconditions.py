"""The rollback's whole postcondition set: its NAMES, and its read as ONE record.

Governing specification: `SPECIFICATION/non-functional-requirements.md`
section "Docker engine install guard", "Rollback" (the postcondition
list) and "Host actions", "Postcondition read".

ONE record and not eight calls, and the difference is load-bearing. The
driver writes `rolled-back` only when EVERY postcondition holds and names
each failing one otherwise, so the eight facts have to be gathered by a
single pass that either answers all of them or fails: a caller assembling
them from separate reads could report a host as clean while one read was
still outstanding, and `rolled-back` is final.

The NAMES live here too, beside the read that has to answer under them,
because a record keyed any other way is not a narrower answer — it is a
WRONG one. The driver's final check looks each name up in this mapping
and counts one it does not find as FAILING, so a disagreement between
the two sides reports every postcondition failing on a host that is
wholly rolled back. That is not hypothetical: it was measured on a
disposable guest on 2026-10-16, where the rollback had removed the start
permission, stopped both daemons and deleted `docker0`, and the run was
still recorded `rollback-partial` — which holds the host's reservation
until an operator intervenes. One definition, consumed by both sides, is
what closes it; a fake host answers under whatever keys its caller
supplies, so no test of either side alone can see the names drift apart.

Six names over eight facts, because the specification gives the guarded
units ONE postcondition: a bound socket, a surviving task and a queued
job are three ways for the same sentence to be false, and the driver has
no separate repair for them.

Stdlib only, Python 3.10 syntax.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from livespec_dev_tooling.fleet._docker_engine_guard_firewall_actions import (
    current_forward_policies,
    residual_docker_rules,
    snapshot_forward_policies,
)
from livespec_dev_tooling.fleet._docker_engine_guard_model import GUARDED_UNITS
from livespec_dev_tooling.fleet._docker_engine_guard_netstate import (
    compare_sysctls,
    read_bridge_links,
)
from livespec_dev_tooling.fleet._docker_engine_guard_units import (
    read_queued_jobs,
    unit_property,
)

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from livespec_dev_tooling.fleet._docker_engine_guard_model import GuardPaths
    from livespec_dev_tooling.fleet._docker_engine_guard_runner import GuardCommandRunner

__all__: list[str] = [
    "BRIDGE_GONE",
    "FORWARD_RESTORED",
    "LISTENING_SOCKETS_ARGV",
    "PERMISSION_GONE",
    "POSTCONDITIONS",
    "RULES_GONE",
    "SOCKET_TIMEOUT_SECONDS",
    "SYSCTLS_MATCH",
    "TASKS_CURRENT",
    "UNITS_QUIET",
    "no_docker_socket",
    "no_guarded_process",
    "no_queued_guarded_job",
    "read_postconditions",
]

# The specification's postcondition set, read as ONE record by the
# driver's final check. Each name is the key the host answers under, and
# each is phrased as the property that must HOLD, so a failing one reads
# as the sentence an operator needs: "no docker0" failing says the bridge
# is still there.
PERMISSION_GONE: Final[str] = "no start permission"
UNITS_QUIET: Final[str] = "no socket, process, queued job or pending start for the guarded units"
FORWARD_RESTORED: Final[str] = "each FORWARD policy as snapshotted"
RULES_GONE: Final[str] = "no Docker rule"
BRIDGE_GONE: Final[str] = "no docker0"
SYSCTLS_MATCH: Final[str] = "each watched sysctl as snapshotted"

POSTCONDITIONS: Final[tuple[str, ...]] = (
    PERMISSION_GONE,
    UNITS_QUIET,
    FORWARD_RESTORED,
    RULES_GONE,
    BRIDGE_GONE,
    SYSCTLS_MATCH,
)

# `ss -lx` is the instrument design R5 names for "docker.socket holds no
# socket": the unit can read `inactive` while a socket it created is
# still bound, and a bound socket re-triggers the service.
LISTENING_SOCKETS_ARGV: Final[tuple[str, ...]] = ("ss", "-lx", "--no-header")
SOCKET_TIMEOUT_SECONDS: Final[int] = 15

# Any listening unix socket whose path carries this is Docker's API.
_DOCKER_SOCKET_PATH: Final[str] = "docker.sock"

# The control-group task count, which is what "no process remains in
# those cgroups" actually means: a container process in a unit's cgroup
# is not its `MainPID`, so a `MainPID` read would report an emptied unit
# while containers were still running under it.
TASKS_CURRENT: Final[str] = "TasksCurrent"

# How an empty or absent cgroup reports its task count. `[not set]` is
# what systemd prints for a unit that is not running at all.
_NO_TASKS: Final[frozenset[str]] = frozenset({"0", "[not set]", ""})


def no_docker_socket(*, runner: GuardCommandRunner) -> bool:
    """Whether no listening unix socket is the Docker API."""
    answer = runner(argv=LISTENING_SOCKETS_ARGV, timeout_seconds=SOCKET_TIMEOUT_SECONDS)
    return _DOCKER_SOCKET_PATH not in answer.stdout


def no_guarded_process(*, runner: GuardCommandRunner) -> bool:
    """Whether every guarded unit's control group is empty."""
    return all(
        unit_property(runner=runner, unit=unit, name=TASKS_CURRENT) in _NO_TASKS
        for unit in GUARDED_UNITS
    )


def no_queued_guarded_job(*, runner: GuardCommandRunner) -> bool:
    """Whether the job queue holds nothing for a guarded unit.

    This covers the specification's "pending start" as well as its
    "queued job": a start job that has not run yet is exactly what would
    bring the engine back a second after the rollback reported success.
    """
    return not any(job.unit in GUARDED_UNITS for job in read_queued_jobs(runner=runner))


def read_postconditions(
    *, runner: GuardCommandRunner, paths: GuardPaths, snapshot: Path
) -> Mapping[str, bool]:
    """The eight rollback facts as one record, under the six specified names.

    Keyed by `POSTCONDITIONS`, in that order, because the driver's final
    check reads this mapping BY NAME and treats a name it cannot find as
    a postcondition that failed.

    The three guarded-unit facts are read into locals before they are
    combined rather than `and`-ed in place: `and` would stop at the first
    one that fails, and the record this pass exists to take is of the
    whole host, not of however much of it the first failure left worth
    looking at.
    """
    socket_quiet = no_docker_socket(runner=runner)
    processes_quiet = no_guarded_process(runner=runner)
    jobs_quiet = no_queued_guarded_job(runner=runner)
    return {
        PERMISSION_GONE: not paths.permission.exists(),
        UNITS_QUIET: socket_quiet and processes_quiet and jobs_quiet,
        FORWARD_RESTORED: current_forward_policies(runner=runner)
        == snapshot_forward_policies(snapshot=snapshot),
        RULES_GONE: residual_docker_rules(runner=runner, snapshot=snapshot) == (),
        BRIDGE_GONE: read_bridge_links(runner=runner) == (),
        SYSCTLS_MATCH: compare_sysctls(runner=runner, snapshot=snapshot) == (),
    }
