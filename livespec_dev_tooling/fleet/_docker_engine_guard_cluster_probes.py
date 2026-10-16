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
from pathlib import Path
from typing import TYPE_CHECKING, Final

from livespec_dev_tooling.fleet._docker_engine_guard_sample import ProbeResult
from livespec_dev_tooling.fleet._docker_engine_guard_units import unit_active_states

if TYPE_CHECKING:
    from collections.abc import Sequence

    from livespec_dev_tooling.fleet._docker_engine_guard_runner import GuardCommandRunner

__all__: list[str] = [
    "ACTIVE",
    "NODE_READY_PROBE",
    "NODE_STATUS_KUBECONFIG",
    "NODE_STATUS_TIMEOUT_SECONDS",
    "READY_CONDITION",
    "REQUIRED_UNITS",
    "SERVICES_PROBE",
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
