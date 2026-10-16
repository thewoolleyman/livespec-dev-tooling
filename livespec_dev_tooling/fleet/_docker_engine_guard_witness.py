"""What each sample compares against the snapshot the preflight recorded.

Governing specification: `SPECIFICATION/non-functional-requirements.md`
section "Docker engine install guard", "Probes" -- "Sysctls", "k3s
witness" and "Interfaces". Governing design:
`docs/docker-engine-guard-design.md` R8 and F8.

These share a module because they share a METHOD, not merely a subject:
each one answers "is this still what it was", and each one gets its
answer by reading a record taken before the first package step and
comparing it with the host now. None of them has an opinion about what
the host OUGHT to look like -- the snapshot is the only record of what
this machine was, and a probe that asserted a value instead of a
baseline would pass a host it had already changed.

Stdlib only, Python 3.10 syntax.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Final

from livespec_dev_tooling.fleet._docker_engine_guard_netstate import compare_sysctls
from livespec_dev_tooling.fleet._docker_engine_guard_sample import ProbeResult

if TYPE_CHECKING:
    from livespec_dev_tooling.fleet._docker_engine_guard_runner import GuardCommandRunner

__all__: list[str] = [
    "CONTAINERD_PATHS",
    "CONTAINERD_PROCESS",
    "K3S_AGENT_UNIT",
    "K3S_WITNESS_PROBE",
    "PGREP_CONTAINERD_ARGV",
    "PROC_ROOT",
    "SYSCTL_PROBE",
    "WITNESS_SNAPSHOT",
    "WITNESS_TIMEOUT_SECONDS",
    "containerd_pid",
    "k3s_witness_probe",
    "sysctl_probe",
    "write_witness_snapshot",
]

# The unit whose containerd must survive the whole window, and the
# process name it runs. AFTER the install there are two processes with
# this exact name on the host -- Docker's and k3s's -- which is why the
# witness identifies k3s's by its CGROUP and never by its name.
K3S_AGENT_UNIT: Final[str] = "k3s-agent.service"
CONTAINERD_PROCESS: Final[str] = "containerd"
PGREP_CONTAINERD_ARGV: Final[tuple[str, ...]] = ("pgrep", "--exact", CONTAINERD_PROCESS)

# Where k3s's embedded containerd keeps its shim sockets and its runc
# state (design, measured state 2026-10-15). NOTHING under
# `/run/containerd` is ever deleted by a rollback, and these two paths
# are the check that nothing deleted them anyway.
CONTAINERD_PATHS: Final[tuple[Path, ...]] = (
    Path("/run/containerd/s"),
    Path("/run/containerd/runc/k8s.io"),
)

PROC_ROOT: Final[Path] = Path("/proc")

WITNESS_SNAPSHOT: Final[str] = "k3s-witness.json"
K3S_WITNESS_PROBE: Final[str] = "k3s-witness"

# A process-table scan the kernel answers from memory.
WITNESS_TIMEOUT_SECONDS: Final[int] = 15

# The one key the witness record carries.
_RECORDED_PID: Final[str] = "containerd_pid"

SYSCTL_PROBE: Final[str] = "sysctls"


def sysctl_probe(*, runner: GuardCommandRunner, snapshot: Path) -> ProbeResult:
    """Whether the five watched forwarding and bridge-netfilter values are unmoved.

    Every value that moved is named with where it was and where it is,
    because an operator reading a failed sample has to put it back and
    the snapshot is the only record of the original. A Docker install
    flips several of these, and one left flipped is how k3s's pod
    network stops forwarding without anything reporting an error.
    """
    moved = compare_sysctls(runner=runner, snapshot=snapshot)
    return ProbeResult(name=SYSCTL_PROBE, passed=not moved, error="; ".join(moved))


def containerd_pid(*, runner: GuardCommandRunner, proc_root: Path = PROC_ROOT) -> str:
    """The PID of the containerd that `k3s-agent.service` runs, or nothing.

    Identified by the process's own CGROUP, which is the only thing
    that tells k3s's containerd from the one the Docker install brings
    with it: after the install both answer to the same name, and the
    whole point of this witness is that the guard never touches the
    first. A PID that has exited between the scan and the read simply
    does not match, which is right -- it is not the witness either.
    """
    answer = runner(argv=PGREP_CONTAINERD_ARGV, timeout_seconds=WITNESS_TIMEOUT_SECONDS)
    for pid in answer.stdout.split():
        cgroup = proc_root / pid / "cgroup"
        if cgroup.is_file() and K3S_AGENT_UNIT in cgroup.read_text(encoding="utf-8"):
            return pid
    return ""


def write_witness_snapshot(
    *, destination: Path, runner: GuardCommandRunner, proc_root: Path = PROC_ROOT
) -> None:
    """Record k3s's containerd PID in the run's `before/` directory."""
    destination.mkdir(parents=True, exist_ok=True)
    _ = (destination / WITNESS_SNAPSHOT).write_text(
        json.dumps(
            {_RECORDED_PID: containerd_pid(runner=runner, proc_root=proc_root)},
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def k3s_witness_probe(
    *,
    runner: GuardCommandRunner,
    snapshot: Path,
    proc_root: Path = PROC_ROOT,
    containerd_paths: Sequence[Path] = CONTAINERD_PATHS,
) -> ProbeResult:
    """Whether k3s's containerd is the SAME process and still has its shim paths.

    The same PID, not merely a running one. A containerd that restarted
    took every pod sandbox on this node with it, and a probe that
    accepted any live PID would report that as healthy -- which is the
    exact failure the guard exists to catch, because a CI pool agent
    whose sandboxes all died is a host that has silently stopped doing
    the one job it is for.

    Both faults are reported together rather than the first one, since
    a rollback that moved the PID and removed a path has done two
    different kinds of damage.
    """
    recorded = str(
        json.loads((snapshot / WITNESS_SNAPSHOT).read_text(encoding="utf-8"))[_RECORDED_PID]
    )
    current = containerd_pid(runner=runner, proc_root=proc_root)
    missing = tuple(str(path) for path in containerd_paths if not path.exists())
    faults: tuple[str, ...] = ()
    if current != recorded:
        faults += (f"k3s-agent's containerd PID moved from {recorded} to {current or 'none'}",)
    if missing:
        faults += (f"these k3s containerd paths are missing: {missing}",)
    return ProbeResult(name=K3S_WITNESS_PROBE, passed=not faults, error="; ".join(faults))
