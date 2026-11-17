"""The reproduction queue's quotas are disarmed or one gate of one to two units.

`cluster-queue-repro-gates.yaml` holds one flavor per gate node. A repro gate is
a claim on a node the per-node CPU budget must count, so no flavor may carry a
partial gate unit or room for two concurrent repro gates. The unit is read from
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


def test_every_repro_flavor_is_disarmed_or_admits_one_gate_of_at_most_two_units() -> None:
    """A repro flavor is zero, or holds one gate: at least one unit, at most two units.

    The bounds are derived from the gates-cq unit, so a repository declaring a larger
    gate_cpu can be admitted without the test pinning any committed quota value.
    """
    unit_cpu, unit_memory = _unit()
    off_shape = {
        name: (cpu, memory)
        for name, (cpu, memory) in _repro_quotas().items()
        if (cpu, memory) != (0, 0)
        and not (unit_cpu <= cpu <= 2 * unit_cpu and unit_memory <= memory <= 2 * unit_memory)
    }
    assert not off_shape, (unit_cpu, unit_memory, off_shape)


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
