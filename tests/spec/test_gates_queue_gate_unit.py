"""The gates-cq gate unit and the fleet lane quotas it sizes.

`cluster-queue-gates.yaml` declares the GATE UNIT, what one gate counts as, in
two annotations on `gates-cq`. Every fleet flavor's cpu and memory quotas must
be the same whole number of those units, so the unit lives in ONE committed
place: `converge-worker-queues.sh` reads it to size the worker flavors, and
these tests fail, naming the flavor, when a fleet literal stops being a whole
number of units. They assert that DERIVATION and never a literal quota or unit
value, as `SPECIFICATION/contracts.md` requires of tests over committed
configuration. The gmktec `gates-flavor` floor of three default-size gate Jobs
is the gate lane headroom rule of the delegated pre-push gate contract in that
same file, and the renderer's default request fitting inside one unit keeps a
default gate from counting as more than one (plan gate-job-resources,
livespec-dev-tooling-brggiu).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

__all__: list[str] = []

pytestmark = pytest.mark.integration

_PHASE2 = Path(__file__).resolve().parents[2] / "ci-runner" / "k3s" / "phase2"
_QUEUE_FILE = _PHASE2 / "kueue" / "cluster-queue-gates.yaml"
_RENDERER = _PHASE2 / "gates" / "render-gate-job.sh"
_HEADROOM_LANE = "gates-flavor"
_HEADROOM_GATES = 3
_MEMORY = re.compile(r"^(?P<amount>0|[1-9][0-9]*)Gi$")
_RENDERER_DEFAULTS = re.compile(
    r'^cpu="(?P<cpu>[0-9]+)"; memory="(?P<memory>[^"]+)";', re.MULTILINE
)


def _gibibytes(*, quantity: str) -> int:
    match = _MEMORY.match(quantity)
    assert match is not None, f"{quantity!r} is not a whole number of Gi"
    return int(match["amount"])


def _gates_cq() -> dict[str, Any]:
    documents: list[dict[str, Any]] = list(
        yaml.safe_load_all(_QUEUE_FILE.read_text(encoding="utf-8"))
    )
    [queue] = [
        d
        for d in documents
        if d and d.get("kind") == "ClusterQueue" and d["metadata"]["name"] == "gates-cq"
    ]
    return queue


def _unit(*, queue: dict[str, Any]) -> tuple[int, int]:
    annotations: dict[str, str] = queue["metadata"]["annotations"]
    return (
        int(annotations["ci-runner.io/gate-unit-cpu"]),
        _gibibytes(quantity=annotations["ci-runner.io/gate-unit-memory"]),
    )


def _fleet_lanes(*, queue: dict[str, Any]) -> dict[str, tuple[int, int]]:
    groups: list[dict[str, Any]] = queue["spec"]["resourceGroups"]
    [group] = [g for g in groups if "cpu" in g["coveredResources"]]
    lanes: dict[str, tuple[int, int]] = {}
    flavors: list[dict[str, Any]] = group["flavors"]
    for flavor in flavors:
        resources: list[dict[str, Any]] = flavor["resources"]
        quotas = {str(r["name"]): r["nominalQuota"] for r in resources}
        lanes[flavor["name"]] = (int(quotas["cpu"]), _gibibytes(quantity=str(quotas["memory"])))
    return lanes


def _renderer_default() -> tuple[int, int]:
    match = _RENDERER_DEFAULTS.search(_RENDERER.read_text(encoding="utf-8"))
    assert match is not None, "render-gate-job.sh carries no cpu/memory defaults line"
    return int(match["cpu"]), _gibibytes(quantity=match["memory"])


def test_every_fleet_gate_lane_is_the_same_whole_number_of_gate_units_in_cpu_and_memory() -> None:
    queue = _gates_cq()
    unit_cpu, unit_memory = _unit(queue=queue)
    lanes = _fleet_lanes(queue=queue)
    assert lanes
    drifted = {
        name: (cpu, memory)
        for name, (cpu, memory) in lanes.items()
        if cpu % unit_cpu or memory % unit_memory or cpu // unit_cpu != memory // unit_memory
    }
    assert not drifted, (
        f"these gates-cq flavors are not a whole, matching number of gate units "
        f"({unit_cpu} cpu, {unit_memory}Gi): {drifted}"
    )


def test_the_gmktec_lane_holds_three_default_size_gate_jobs() -> None:
    lanes = _fleet_lanes(queue=_gates_cq())
    default_cpu, default_memory = _renderer_default()
    cpu, memory = lanes[_HEADROOM_LANE]
    assert (
        cpu >= _HEADROOM_GATES * default_cpu
    ), f"{_HEADROOM_LANE}: cpu quota {cpu} is below {_HEADROOM_GATES} default gate Jobs"
    assert (
        memory >= _HEADROOM_GATES * default_memory
    ), f"{_HEADROOM_LANE}: memory quota {memory}Gi is below {_HEADROOM_GATES} default gate Jobs"


def test_a_default_size_gate_job_fits_inside_one_gate_unit() -> None:
    unit_cpu, unit_memory = _unit(queue=_gates_cq())
    default_cpu, default_memory = _renderer_default()
    assert default_cpu <= unit_cpu
    assert default_memory <= unit_memory
