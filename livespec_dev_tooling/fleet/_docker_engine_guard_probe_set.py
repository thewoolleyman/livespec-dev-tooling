"""The whole probe set of one sample, and the parameters it is assembled from.

Governing specification: `SPECIFICATION/non-functional-requirements.md`
section "Docker engine install guard", "Probes" (this repository).
Governing design: `docs/docker-engine-guard-design.md` Mechanism 3 as
corrected by R8, R9 and F8.

WHY THE ASSEMBLY IS ITS OWN MODULE. Every probe module imports
`ProbeResult` from `_docker_engine_guard_sample`, so the assembly cannot
live there: it would make that module import its own importers. It does
not belong in the real host either, which is one line of delegation per
seam by design. So the one place that knows the WHOLE set lives here,
and the host and the retry rule each stay ignorant of it.

WHERE THE PARAMETERS COME FROM. The controller uploads them into the
run's own `inputs/` directory and only `publish` installs them, so a
sample reads this run's parameters and cannot be handed another run's.
The run itself is read from the host's own reservation rather than passed
in, because `HostOps.sample` takes no arguments: the observer calls it
inside a window it has already claimed, and the reservation is what says
which window that is.

Stdlib only, Python 3.10 syntax.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Final, cast

from livespec_dev_tooling.fleet._docker_engine_guard_cluster_probes import (
    dns_placement_probe,
    node_ready_probe,
    services_probe,
)
from livespec_dev_tooling.fleet._docker_engine_guard_pod_probes import (
    PodNamespace,
    api_probe,
    dns_probe,
    https_probe,
    pod_namespace_probe,
)
from livespec_dev_tooling.fleet._docker_engine_guard_sample import Probe, build_sample
from livespec_dev_tooling.fleet._docker_engine_guard_sample_firewall import firewall_probe
from livespec_dev_tooling.fleet._docker_engine_guard_scope import (
    canary_cgroup_probe,
    canary_pid,
    canary_veth_index,
    exclusive_scope_probe,
)
from livespec_dev_tooling.fleet._docker_engine_guard_state import read_reservation
from livespec_dev_tooling.fleet._docker_engine_guard_witness import (
    CONTAINERD_PATHS,
    PROC_ROOT,
    interface_probe,
    k3s_witness_probe,
    sysctl_probe,
    write_interface_snapshot,
    write_witness_snapshot,
)

if TYPE_CHECKING:
    from livespec_dev_tooling.fleet._docker_engine_guard_model import GuardPaths
    from livespec_dev_tooling.fleet._docker_engine_guard_runner import GuardCommandRunner

__all__: list[str] = [
    "PROBE_PARAMETERS",
    "ProbeParameters",
    "host_probes",
    "probe_parameters_path",
    "read_probe_parameters",
    "record_preflight",
    "take_sample",
]

# Where the controller's uploaded probe parameters live, inside the run's
# own inputs directory and nowhere else (design G3).
PROBE_PARAMETERS: Final[str] = "probes.json"

# The declared key naming the route to the k3s server, and what the
# refusal says when the declaration cannot be run. The message names the
# key rather than describing it, because the reader is the operator who
# wrote the file it names.
_K3S_SERVER_ARGV: Final[str] = "k3s_server_argv"
_ROUTE_REFUSAL: Final[str] = f"{_K3S_SERVER_ARGV} must be a non-empty list of non-empty strings"


@dataclass(frozen=True, kw_only=True)
class ProbeParameters:
    """Everything the probe set needs that is a fact about the CLUSTER.

    Declared rather than discovered, every one of them. The node's own
    name, the k3s server to delegate a pod listing to, the ROUTE that
    reaches it, the kube-dns and API service addresses, the units the
    fleet says must stay running and the canary's name are all decisions
    made where the cluster is known — and a guard that discovered them
    would be guessing on the one host that must not be guessed about.

    `k3s_server_argv` is the command prefix that reaches the k3s server
    and runs a command there with the rights `k3s kubectl` needs. It is
    declared because what those rights cost differs per fleet (see
    `coredns_placement_argv`), and it is OPTIONAL because the previous
    root-to-root `ssh` prefix remains the default — so a run that says
    nothing about the route behaves exactly as it did before.
    """

    node: str
    k3s_server: str
    kube_dns_address: str
    dns_name: str
    api_address: str
    api_port: int
    canary: str
    must_stay_running: tuple[str, ...] = ()
    k3s_server_argv: tuple[str, ...] = ()


def probe_parameters_path(*, paths: GuardPaths, run: str) -> Path:
    """This run's own probe parameters, which no other run can write."""
    return paths.inputs_dir(run=run) / PROBE_PARAMETERS


def _k3s_server_argv(*, declared: object, path: Path) -> tuple[str, ...]:
    """The declared route to the k3s server, refused unless it can be RUN.

    Every shape but a non-empty list of non-empty strings fails where
    the failure is invisible rather than loud, which is why this refuses
    here — at the read, in front of the operator who wrote the file —
    instead of once per sample inside the observation window, on the one
    host nobody can reach by hand. An empty list reads as "no route
    declared" to the default and silently restores the root-to-root
    prefix the declaration exists to replace. A bare string is iterated
    character by character, so `"ssh host"` becomes eight one-letter
    words. A word that is empty builds an argv carrying an empty
    argument, which `ssh` reads as a host named "".
    """
    words = cast("Sequence[object]", declared) if isinstance(declared, list) else ()
    if not words or not all(isinstance(word, str) and word for word in words):
        msg = f"{path}: {_ROUTE_REFUSAL}"
        raise ValueError(msg)
    return tuple(str(word) for word in words)


def read_probe_parameters(*, paths: GuardPaths, run: str) -> ProbeParameters:
    """One run's declared probe parameters, read from its own inputs directory.

    An ABSENT `k3s_server_argv` is the undeclared route and keeps the
    placement read's previous prefix; a PRESENT one is refused unless it
    can be run. The two are told apart by membership rather than by a
    falsy value, so an explicit `null` is a malformed declaration and
    not a second spelling of "absent".
    """
    path = probe_parameters_path(paths=paths, run=run)
    recorded = json.loads(path.read_text(encoding="utf-8"))
    return ProbeParameters(
        node=str(recorded["node"]),
        k3s_server=str(recorded["k3s_server"]),
        kube_dns_address=str(recorded["kube_dns_address"]),
        dns_name=str(recorded["dns_name"]),
        api_address=str(recorded["api_address"]),
        api_port=int(recorded["api_port"]),
        canary=str(recorded["canary"]),
        must_stay_running=tuple(str(unit) for unit in recorded.get("must_stay_running", ())),
        k3s_server_argv=(
            _k3s_server_argv(declared=recorded[_K3S_SERVER_ARGV], path=path)
            if _K3S_SERVER_ARGV in recorded
            else ()
        ),
    )


def host_probes(
    *,
    runner: GuardCommandRunner,
    snapshot: Path,
    parameters: ProbeParameters,
    proc_root: Path = PROC_ROOT,
    containerd_paths: Sequence[Path] = CONTAINERD_PATHS,
) -> tuple[Probe, ...]:
    """Every probe of one sample, each bound to what it needs, in reported order.

    The canary's PID is resolved ONCE per sample, and the pod's
    namespace is resolved once per sample TOO -- but through a holder
    rather than a value, because the two are not alike. The canary is
    the guard's own container and lives as long as the window does,
    while the pods on this host come and go under an ARC listener: a
    PID bound into three probes is a PID that can be dead by the time
    the second of them runs, and the retry that exists to tell a
    transient from a change would then re-enter the same dead
    namespace. The holder shares one pod while it keeps answering and
    forgets it the moment a probe fails there, so "the pod" stays well
    defined within a sample without outliving the pod itself.
    """
    namespace = PodNamespace(runner=runner)
    canary = canary_pid(runner=runner, canary=parameters.canary)
    return (
        partial(services_probe, runner=runner, must_stay_running=parameters.must_stay_running),
        partial(node_ready_probe, runner=runner, node=parameters.node),
        partial(
            dns_placement_probe,
            runner=runner,
            server=parameters.k3s_server,
            node=parameters.node,
            k3s_server_argv=parameters.k3s_server_argv,
        ),
        partial(
            pod_namespace_probe,
            namespace=namespace,
            probe=partial(
                dns_probe,
                runner=runner,
                server=parameters.kube_dns_address,
                name=parameters.dns_name,
            ),
        ),
        partial(
            pod_namespace_probe,
            namespace=namespace,
            probe=partial(
                api_probe,
                runner=runner,
                address=parameters.api_address,
                port=parameters.api_port,
            ),
        ),
        partial(
            pod_namespace_probe,
            namespace=namespace,
            probe=partial(https_probe, runner=runner),
        ),
        partial(sysctl_probe, runner=runner, snapshot=snapshot),
        partial(
            k3s_witness_probe,
            runner=runner,
            snapshot=snapshot,
            proc_root=proc_root,
            containerd_paths=containerd_paths,
        ),
        partial(
            canary_cgroup_probe,
            runner=runner,
            canary=parameters.canary,
            proc_root=proc_root,
        ),
        partial(exclusive_scope_probe, runner=runner, canary=parameters.canary),
        partial(
            interface_probe,
            runner=runner,
            snapshot=snapshot,
            canary_veth_index=canary_veth_index(runner=runner, pid=canary),
        ),
        partial(firewall_probe, runner=runner, snapshot=snapshot),
    )


def record_preflight(
    *, destination: Path, runner: GuardCommandRunner, proc_root: Path = PROC_ROOT
) -> None:
    """Record what a sample compares against: k3s's containerd and the interfaces.

    Taken into the run's own `before/` directory, beside the firewall
    and sysctl snapshot and before the first package step, because
    these are the baselines the witness and the interface probe
    compare each sample against — and a baseline taken after a package
    step would already carry what it exists to detect.
    """
    write_witness_snapshot(destination=destination, runner=runner, proc_root=proc_root)
    write_interface_snapshot(destination=destination, runner=runner)


def take_sample(
    *,
    runner: GuardCommandRunner,
    paths: GuardPaths,
    proc_root: Path = PROC_ROOT,
    containerd_paths: Sequence[Path] = CONTAINERD_PATHS,
) -> Mapping[str, object]:
    """One observation sample of this host, against THIS run's own records."""
    run = read_reservation(paths=paths) or ""
    return build_sample(
        probes=host_probes(
            runner=runner,
            snapshot=paths.snapshot_dir(run=run),
            parameters=read_probe_parameters(paths=paths, run=run),
            proc_root=proc_root,
            containerd_paths=containerd_paths,
        )
    )
