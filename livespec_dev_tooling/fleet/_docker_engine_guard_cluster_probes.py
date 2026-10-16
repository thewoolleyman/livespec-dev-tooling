"""The probes that ask the CLUSTER and the service manager about this host.

Governing specification: `SPECIFICATION/non-functional-requirements.md`
section "Docker engine install guard", "Probes" -- "Services", "Node
Ready" and the placement half of "DNS". Governing design:
`docs/docker-engine-guard-design.md` Mechanism 3 as corrected by R8 and
F7.

These three share a module because they share a QUESTION: is this host
still a working member of the cluster it was a member of before the
install. None of them enters a pod's network namespace -- those probes
live next door -- and none of them touches Docker.

Stdlib only, Python 3.10 syntax.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Final

from livespec_dev_tooling.fleet._docker_engine_guard_sample import ProbeResult
from livespec_dev_tooling.fleet._docker_engine_guard_units import unit_active_states

if TYPE_CHECKING:
    from livespec_dev_tooling.fleet._docker_engine_guard_runner import GuardCommandRunner

__all__: list[str] = [
    "ACTIVE",
    "COREDNS_PREFIX",
    "DNS_PLACEMENT_PROBE",
    "NODE_READY_PROBE",
    "NODE_STATUS_KUBECONFIG",
    "NODE_STATUS_TIMEOUT_SECONDS",
    "PLACEMENT_TIMEOUT_SECONDS",
    "READY_CONDITION",
    "REQUIRED_UNITS",
    "RUNNING",
    "SERVICES_PROBE",
    "coredns_nodes",
    "coredns_placement_argv",
    "dns_placement_probe",
    "node_ready_probe",
    "node_status_argv",
    "services_probe",
]

# The two units the guarded host's own life depends on, whatever else the
# fleet declares. `k3s-agent` is the CI pool agent this machine exists to
# run, and `tailscaled` serves the only remote access path there is --
# the whole guard exists because nobody can reach this host physically.
REQUIRED_UNITS: Final[tuple[str, ...]] = (
    "k3s-agent.service",
    "tailscaled.service",
)

ACTIVE: Final[str] = "active"

SERVICES_PROBE: Final[str] = "services"
NODE_READY_PROBE: Final[str] = "node-ready"
DNS_PLACEMENT_PROBE: Final[str] = "dns-placement"

# The name every CoreDNS replica's pod carries, and the phase a replica
# has to be in to answer a query at all.
COREDNS_PREFIX: Final[str] = "coredns"
RUNNING: Final[str] = "Running"

# The columns `get pods -o wide` prints, zero-based: NAME, READY,
# STATUS, RESTARTS, AGE, IP, NODE.
_STATUS_COLUMN: Final[int] = 2
_NODE_COLUMN: Final[int] = 6

# One delegated read over SSH to the k3s server. Longer than a local
# API round trip because it carries a connection setup with it.
PLACEMENT_TIMEOUT_SECONDS: Final[int] = 30

# The pool's node-status credential, which the k3s agent already carries
# (design, measured state 2026-10-15).
NODE_STATUS_KUBECONFIG: Final[Path] = Path("/etc/rancher/k3s/node-status-kubeconfig")

# One API round trip. Long enough for a server under a reconciler's
# sweep, short enough that a sample cannot outlive its own interval.
NODE_STATUS_TIMEOUT_SECONDS: Final[int] = 15

READY_CONDITION: Final[str] = "Ready"

# How the API server spells a satisfied condition. It is a STRING and
# not a boolean in the Node object, and the third value -- `Unknown` --
# is exactly what a node whose kubelet has stopped reporting shows, so
# the comparison is against this one spelling rather than against
# anything falsy.
_TRUE: Final[str] = "True"


def services_probe(*, runner: GuardCommandRunner, must_stay_running: Sequence[str]) -> ProbeResult:
    """Whether the two required units and every declared one are active.

    `activating` and `failed` are NOT active, and the difference matters
    to whoever reads the failure: the first is a unit on its way back and
    the second is one that gave up, so each unit is reported with the
    state it was actually in rather than merely as "not active".

    The declared units are appended to the required two and de-duplicated
    IN ORDER, so a fleet variable that names `k3s-agent` again costs one
    read rather than two and the recorded argv sequence stays the same
    whatever the declaration repeats.
    """
    units = tuple(dict.fromkeys((*REQUIRED_UNITS, *must_stay_running)))
    states = unit_active_states(runner=runner, units=units)
    stopped = tuple(f"{unit} is {states[unit]}" for unit in units if states[unit] != ACTIVE)
    return ProbeResult(name=SERVICES_PROBE, passed=not stopped, error="; ".join(stopped))


def node_status_argv(*, node: str) -> tuple[str, ...]:
    """The node-status credential's ONE authorized read: this node's own status.

    `get --raw` rather than `get node`, because the committed grant is
    `get`/`patch` on `nodes/status` for this node alone (design R8) --
    an ordinary `get node` is a read of the `nodes` collection the
    credential cannot make, and a probe that attempted it would report
    the host as unhealthy on every sample of a perfectly healthy run.
    """
    return (
        "k3s",
        "kubectl",
        "--kubeconfig",
        str(NODE_STATUS_KUBECONFIG),
        "get",
        "--raw",
        f"/api/v1/nodes/{node}/status",
    )


def node_ready_probe(*, runner: GuardCommandRunner, node: str) -> ProbeResult:
    """Whether the cluster still reports this node's own `Ready` condition true.

    Reported as Node Ready and NEVER substituted by a kubelet healthz:
    healthz answers that the kubelet process is alive, while `Ready` is
    the cluster's own verdict on whether this node can take work -- and
    a Docker install that broke the pod network leaves the first true
    and the second false.

    The condition is selected by its TYPE. A node carries several
    conditions in an order the API server does not promise, so a probe
    reading the first or the only one would read `MemoryPressure` on
    some samples and `Ready` on others.
    """
    answer = runner(argv=node_status_argv(node=node), timeout_seconds=NODE_STATUS_TIMEOUT_SECONDS)
    if answer.returncode != 0:
        return ProbeResult(
            name=NODE_READY_PROBE,
            passed=False,
            error=f"the node status read exited {answer.returncode}",
        )
    conditions = json.loads(answer.stdout)["status"]["conditions"]
    reported = tuple(
        str(condition["status"]) for condition in conditions if condition["type"] == READY_CONDITION
    )
    ready = reported == (_TRUE,)
    return ProbeResult(
        name=NODE_READY_PROBE,
        passed=ready,
        error="" if ready else f"the node's Ready condition reads {reported}",
    )


def coredns_placement_argv(*, server: str) -> tuple[str, ...]:
    """Where CoreDNS runs, read by DELEGATING the question to the k3s server.

    The guarded host's own node-status credential cannot list pods --
    its grant is this node's status and nothing else (design R8) -- so
    the placement is read where a credential for it exists. `BatchMode`
    so a host whose key is not accepted fails at once instead of
    waiting on a password prompt no sample can answer.
    """
    return (
        "ssh",
        "-o",
        "BatchMode=yes",
        server,
        "k3s",
        "kubectl",
        "get",
        "pods",
        "-n",
        "kube-system",
        "-o",
        "wide",
    )


def _coredns_node(*, fields: Sequence[str]) -> Sequence[str]:
    """The node of one `get pods -o wide` row, when it is a RUNNING CoreDNS pod.

    Three kinds of row answer nothing: the header, a pod that is not
    CoreDNS, and a CoreDNS replica that is Terminating -- the last one
    matters most, because a replica on its way out cannot answer a
    query and counting it would let a same-node placement read as
    cross-node. Every answer is a one-element SLICE, so a row shorter
    than the node column answers nothing without a guard of its own.
    """
    name = fields[:1]
    status = list(fields[_STATUS_COLUMN : _STATUS_COLUMN + 1])
    node = fields[_NODE_COLUMN : _NODE_COLUMN + 1]
    return node if name and name[0].startswith(COREDNS_PREFIX) and status == [RUNNING] else ()


def coredns_nodes(*, runner: GuardCommandRunner, server: str) -> tuple[str, ...]:
    """Every node a running CoreDNS replica answers from, in the order listed."""
    answer = runner(
        argv=coredns_placement_argv(server=server), timeout_seconds=PLACEMENT_TIMEOUT_SECONDS
    )
    return tuple(
        node for raw in answer.stdout.splitlines() for node in _coredns_node(fields=raw.split())
    )


def dns_placement_probe(*, runner: GuardCommandRunner, server: str, node: str) -> ProbeResult:
    """Whether the DNS probe is still answered from ANOTHER node.

    Read at the preflight and again at the end of the window, because
    CoreDNS can move in between (design F7). A backend on this node is
    reported as same-node and does not count toward confirmation; no
    running backend at all is a failure, because the cluster then has
    no DNS for the probe to prove anything with.
    """
    backends = coredns_nodes(runner=runner, server=server)
    if not backends:
        return ProbeResult(
            name=DNS_PLACEMENT_PROBE,
            passed=False,
            error="no running CoreDNS backend was found through the k3s server",
        )
    here = tuple(name for name in backends if name == node)
    return ProbeResult(
        name=DNS_PLACEMENT_PROBE,
        passed=True,
        error=(
            f"CoreDNS answers from this node {here}, so the DNS probe is same-node" if here else ""
        ),
        counts_toward_confirmation=not here,
    )
