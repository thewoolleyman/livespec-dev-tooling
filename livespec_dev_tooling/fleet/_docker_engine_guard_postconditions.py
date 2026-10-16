"""The rollback's whole postcondition set, read as ONE record.

Governing specification: `SPECIFICATION/non-functional-requirements.md`
section "Docker engine install guard", "Rollback" (the postcondition
list) and "Host actions", "Postcondition read".

ONE record and not eight calls, and the difference is load-bearing. The
driver writes `rolled-back` only when EVERY postcondition holds and names
each failing one otherwise, so the eight facts have to be gathered by a
single pass that either answers all of them or fails: a caller assembling
them from separate reads could report a host as clean while one read was
still outstanding, and `rolled-back` is final.

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
    "LISTENING_SOCKETS_ARGV",
    "SOCKET_TIMEOUT_SECONDS",
    "TASKS_CURRENT",
    "no_docker_socket",
    "no_guarded_process",
    "no_queued_guarded_job",
    "read_postconditions",
]

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
    """The eight rollback postconditions, as one record."""
    return {
        "no_start_permission": not paths.permission.exists(),
        "no_docker_socket": no_docker_socket(runner=runner),
        "no_guarded_process": no_guarded_process(runner=runner),
        "no_queued_job": no_queued_guarded_job(runner=runner),
        "forward_policies_restored": current_forward_policies(runner=runner)
        == snapshot_forward_policies(snapshot=snapshot),
        "no_docker_rule": residual_docker_rules(runner=runner, snapshot=snapshot) == (),
        "no_docker0": read_bridge_links(runner=runner) == (),
        "sysctls_restored": compare_sysctls(runner=runner, snapshot=snapshot) == (),
    }
