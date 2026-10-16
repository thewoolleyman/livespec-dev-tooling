"""The guarded Docker SCOPE during the window: one canary and nothing else.

Governing specification: `SPECIFICATION/non-functional-requirements.md`
section "Docker engine install guard", "Probes" -- "Containers and
networks" and "Interfaces". Governing design:
`docs/docker-engine-guard-design.md` R9 ("exclusive admission during the
window") and Mechanism 4's `docker0`-only scope.

WHY THE SCOPE IS CHECKED AT ALL. The rollback can only remove what it
knows how to find: the default bridge, the `172.17.0.0/16` subnet and
the `DOCKER*` chains. A second Docker network, a second container or an
interface the guard did not create is outside that cleanup, so a
rollback would report success while leaving it behind. The scope checks
exist so the run learns that DURING the window -- while rolling back is
still cheap -- rather than afterwards, and so a run that finds one
records that its cleanup may not have covered it.

Stdlib only, Python 3.10 syntax.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from livespec_dev_tooling.fleet._docker_engine_guard_sample import ProbeResult
from livespec_dev_tooling.fleet._docker_engine_guard_units import SANDBOX_SLICE, SYSTEMCTL
from livespec_dev_tooling.fleet._docker_engine_guard_witness import PROC_ROOT

if TYPE_CHECKING:
    from pathlib import Path

    from livespec_dev_tooling.fleet._docker_engine_guard_runner import GuardCommandRunner

__all__: list[str] = [
    "CANARY_CGROUP_PROBE",
    "CONTROL_GROUP_ARGV",
    "DOCKER",
    "SCOPE_TIMEOUT_SECONDS",
    "canary_cgroup_probe",
    "canary_pid_argv",
    "slice_control_group",
]

DOCKER: Final[str] = "docker"

# `-p` and not `--property`, because this is the instrument the
# specification and design both name by that spelling. The slice is
# NESTED on this fleet (`/fabro.slice/fabro-sandbox.slice`), so its
# control-group path is resolved from the service manager rather than
# written down: a literal would be wrong the moment the slice moves,
# and wrong in the direction of failing every sample on a correctly
# configured host.
CONTROL_GROUP_ARGV: Final[tuple[str, ...]] = (
    SYSTEMCTL,
    "show",
    "-p",
    "ControlGroup",
    "--value",
    SANDBOX_SLICE,
)

# Local reads the daemon and the service manager answer from memory.
SCOPE_TIMEOUT_SECONDS: Final[int] = 20

CANARY_CGROUP_PROBE: Final[str] = "canary-cgroup"


def slice_control_group(*, runner: GuardCommandRunner) -> str:
    """The sandbox slice's cgroup path, as the service manager resolves it now."""
    answer = runner(argv=CONTROL_GROUP_ARGV, timeout_seconds=SCOPE_TIMEOUT_SECONDS)
    return answer.stdout.strip()


def canary_pid_argv(*, canary: str) -> tuple[str, ...]:
    """The canary's main PID, read from the daemon that is running it."""
    return (DOCKER, "inspect", "--format", "{{.State.Pid}}", canary)


def canary_cgroup_probe(
    *, runner: GuardCommandRunner, canary: str, proc_root: Path = PROC_ROOT
) -> ProbeResult:
    """Whether the canary is running INSIDE the sandbox slice the fleet declared.

    Read from the HOST through the canary's own PID rather than from
    the daemon's configuration, because the question is where the
    kernel actually put the process -- a `cgroup-parent` the daemon
    accepted and then ignored would read as correct from the daemon and
    wrong from `/proc`, and it is the kernel's answer that decides
    whether the rollback's cgroup kill reaches this container.
    """
    control_group = slice_control_group(runner=runner)
    pid = runner(
        argv=canary_pid_argv(canary=canary), timeout_seconds=SCOPE_TIMEOUT_SECONDS
    ).stdout.strip()
    cgroup = proc_root / pid / "cgroup"
    placement = cgroup.read_text(encoding="utf-8").strip() if cgroup.is_file() else ""
    inside = bool(control_group) and control_group in placement
    return ProbeResult(
        name=CANARY_CGROUP_PROBE,
        passed=inside,
        error=(
            ""
            if inside
            else f"the canary's cgroup is {placement or 'unreadable'}, "
            f"not under {control_group}"
        ),
    )
