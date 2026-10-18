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
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from typing import TYPE_CHECKING, Final

from livespec_dev_tooling.fleet._docker_engine_guard_firewall import DOCKER_BRIDGE
from livespec_dev_tooling.fleet._docker_engine_guard_netstate import (
    LINK_SHOW_ARGV,
    LINK_TIMEOUT_SECONDS,
    compare_sysctls,
)
from livespec_dev_tooling.fleet._docker_engine_guard_sample import ProbeResult

if TYPE_CHECKING:
    from livespec_dev_tooling.fleet._docker_engine_guard_runner import GuardCommandRunner

__all__: list[str] = [
    "CONTAINERD_PATHS",
    "CONTAINERD_PROCESS",
    "INTERFACE_PROBE",
    "INTERFACE_SNAPSHOT",
    "K3S_AGENT_UNIT",
    "K3S_WITNESS_PROBE",
    "PGREP_CONTAINERD_ARGV",
    "PROC_ROOT",
    "SYSCTL_PROBE",
    "WITNESS_SNAPSHOT",
    "WITNESS_TIMEOUT_SECONDS",
    "HostLink",
    "containerd_pid",
    "interface_probe",
    "k3s_witness_probe",
    "read_links",
    "sysctl_probe",
    "write_interface_snapshot",
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
INTERFACE_SNAPSHOT: Final[str] = "interfaces.json"
K3S_WITNESS_PROBE: Final[str] = "k3s-witness"
INTERFACE_PROBE: Final[str] = "interfaces"

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


@dataclass(frozen=True, kw_only=True)
class HostLink:
    """One interface as `ip -o link show` reports it: its name and its master.

    The MASTER rides beside the name because it is the only column that
    tells a veth k3s's pod network made from a veth Docker made: both
    appear during the observation window, both are named at random, and
    only the second is the guard's to find. It is read live at sample
    time rather than recorded, so the snapshot stays the list of NAMES
    it already was.
    """

    name: str
    master: str


def _link_master(*, row: str) -> str:
    """The interface this `ip -o link show` row is enslaved to, or nothing.

    `ip` reports it as the field following the `master` keyword, and a
    row without the keyword is enslaved to nothing. The field is taken
    by PAIRING each field with its successor rather than by indexing
    past the keyword, so a row whose last field is `master` yields
    nothing and needs no bounds guard -- the same reason the reader
    below zips slices.
    """
    pairs = pairwise(row.split())
    return next((after for keyword, after in pairs if keyword == "master"), "")


def read_links(*, runner: GuardCommandRunner) -> Mapping[str, HostLink]:
    """Every interface on the host, its INDEX mapped to its name and master.

    The index is carried because that is how the canary's veth pair is
    identified: the container side names the host-side INDEX, never the
    host-side name, which is random. Any `@peer` suffix is stripped from
    the name so a veth reads as the name a deletion would take.

    Each row contributes a pair by ZIPPING two one-element slices, so a
    row with fewer than two fields contributes nothing and needs no
    length guard -- and a guard no recorded output can reach is a line
    no test can cover.
    """
    answer = runner(argv=LINK_SHOW_ARGV, timeout_seconds=LINK_TIMEOUT_SECONDS)
    return {
        index.rstrip(":"): HostLink(
            name=name.rstrip(":").partition("@")[0], master=_link_master(row=raw)
        )
        for raw in answer.stdout.splitlines()
        # `strict=False` is REQUIRED and not a relaxation: a row with
        # fewer than two fields pairs with nothing, which is the whole
        # point -- `strict=True` would raise on it instead.
        for index, name in zip(raw.split()[:1], raw.split()[1:2], strict=False)
    }


def write_interface_snapshot(*, destination: Path, runner: GuardCommandRunner) -> None:
    """Record every interface NAME on the host in the run's `before/` directory."""
    destination.mkdir(parents=True, exist_ok=True)
    _ = (destination / INTERFACE_SNAPSHOT).write_text(
        json.dumps(sorted(link.name for link in read_links(runner=runner).values()), indent=2)
        + "\n",
        encoding="utf-8",
    )


def interface_probe(
    *, runner: GuardCommandRunner, snapshot: Path, canary_veth_index: str
) -> ProbeResult:
    """Whether anything but `docker0`, the canary's veth and a recorded bridge's own has appeared.

    Compared against the RECORDED set rather than against names the
    guard knows, because this host already carries `cni0`, `flannel.1`
    and k3s's own veths -- a probe that listed the interfaces it
    expected would have to enumerate another subsystem's, and would go
    wrong the moment that subsystem added one.

    A link whose MASTER is a name the snapshot recorded is that same
    subsystem adding one WHILE THE WINDOW RUNS, which is ordinary on the
    only kind of host the guard is for: a CI node admits pods, and each
    pod puts a veth on `cni0`. Without this the rule failed every window
    on a live node -- measured 2026-10-18 on gmktec-xubuntu, 18 pod
    veths in one window, a clean install rolled back. The master is
    attested by the recorded NAME and nothing else, which is exactly
    what makes it safe to allow: `docker0` is absent from every
    snapshot the preflight takes (it refuses a host that already has
    one), so Docker's own veths are never on a recorded master and keep
    failing the sample. This is the interface counterpart of the
    firewall comparison's `KUBE-*` / `FLANNEL-*` carve-out.

    An UNIDENTIFIED canary veth is a failure rather than a wildcard:
    the pair is allowed because the guard created it and can delete it,
    and a pair the guard cannot point at is a pair its cleanup cannot
    find either.
    """
    links = read_links(runner=runner)
    recorded: set[str] = {
        str(name)
        for name in json.loads((snapshot / INTERFACE_SNAPSHOT).read_text(encoding="utf-8"))
    }
    pair: set[str] = {links[canary_veth_index].name} if canary_veth_index in links else set()
    allowed: set[str] = recorded | {DOCKER_BRIDGE} | pair
    appeared = tuple(
        sorted(
            link.name
            for link in links.values()
            if link.name not in allowed and link.master not in recorded
        )
    )
    return ProbeResult(
        name=INTERFACE_PROBE,
        passed=not appeared,
        error=("" if not appeared else f"these interfaces appeared since the snapshot: {appeared}"),
    )
