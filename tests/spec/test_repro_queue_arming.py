"""The reproduction queue's quotas are whole gate units, at most one per node.

`cluster-queue-repro-gates.yaml` holds one flavor per gate node. A repro gate is
a claim on a node the per-node CPU budget must count, so no flavor may carry a
partial gate unit or more than one concurrent repro gate. The unit is read from
the gates-cq annotations and no quota literal is asserted
(livespec-dev-tooling-cwrg3v).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

__all__: list[str] = []

pytestmark = pytest.mark.integration

_KUEUE = Path(__file__).resolve().parents[2] / "ci-runner" / "k3s" / "phase2" / "kueue"
_MEMORY = re.compile(r"^(?P<amount>0|[1-9][0-9]*)Gi$")


def _documents(*, name: str) -> list[dict[str, Any]]:
    loaded: list[dict[str, Any] | None] = list(
        yaml.safe_load_all((_KUEUE / name).read_text(encoding="utf-8"))
    )
    return [document for document in loaded if document]


def _unit() -> tuple[int, int]:
    [queue] = [
        d
        for d in _documents(name="cluster-queue-gates.yaml")
        if d["kind"] == "ClusterQueue" and d["metadata"]["name"] == "gates-cq"
    ]
    annotations: dict[str, str] = queue["metadata"]["annotations"]
    memory = _MEMORY.match(annotations["ci-runner.io/gate-unit-memory"])
    assert memory is not None
    return int(annotations["ci-runner.io/gate-unit-cpu"]), int(memory["amount"])


def _repro_quotas() -> dict[str, tuple[int, int]]:
    [queue] = [
        d for d in _documents(name="cluster-queue-repro-gates.yaml") if d["kind"] == "ClusterQueue"
    ]
    quotas: dict[str, tuple[int, int]] = {}
    for group in queue["spec"]["resourceGroups"]:
        for flavor in group["flavors"]:
            by_name = {str(r["name"]): r["nominalQuota"] for r in flavor["resources"]}
            memory = _MEMORY.match(str(by_name["memory"]))
            assert memory is not None, flavor["name"]
            quotas[str(flavor["name"])] = (int(by_name["cpu"]), int(memory["amount"]))
    return quotas


# The one declared gate size above the default unit: livespec-orchestrator-beads-fabro
# declares gate_cpu = 10 / gate_memory = 8Gi, so a repro of it needs one flavor that
# admits that size (its Job was never admitted against 5 cpu, 2026-11-17).
_LARGE_DECLARED_GATE = (10, 8)


def test_every_repro_flavor_holds_zero_one_gate_unit_or_the_large_declared_gate() -> None:
    """A repro flavor is disarmed (zero), one whole unit, or the one large declared gate."""
    unit = _unit()
    off_unit = {
        name: quota
        for name, quota in _repro_quotas().items()
        if quota not in {(0, 0), unit, _LARGE_DECLARED_GATE}
    }
    assert not off_unit, (unit, off_unit)


def test_every_repro_flavor_is_pinned_to_its_node_by_hostname() -> None:
    """Each flavor selects one hostname, and the four gate nodes each have a flavor."""
    flavors = [
        d
        for d in _documents(name="cluster-queue-repro-gates.yaml")
        if d["kind"] == "ResourceFlavor"
    ]
    hosts = {str(f["spec"]["nodeLabels"]["kubernetes.io/hostname"]) for f in flavors}
    expected = {"gamingpc-xubuntu", "poweredge-xubuntu", "gmktec-xubuntu", "hp-xubuntu"}
    assert hosts == expected, hosts
