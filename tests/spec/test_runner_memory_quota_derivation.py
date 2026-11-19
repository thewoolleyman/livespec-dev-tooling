"""Keep ARC runner memory requests and Kueue's documented headroom aligned."""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

import pytest
import yaml

__all__: list[str] = []

pytestmark = pytest.mark.integration

_PHASE2 = Path(__file__).resolve().parents[2] / "ci-runner" / "k3s" / "phase2"
_ARC = _PHASE2 / "arc"
_KUEUE = _PHASE2 / "kueue"
_DERIVATION = _KUEUE / "DERIVATION.md"
_WORKER_QUEUE = "livespec-dev-tooling-arm64-cq"
_MEMORY_REQUESTS = {
    "values-fabro.yaml": "6Gi",
    "values-livespec-console-beads-fabro.yaml": "2.75Gi",
    "values-livespec-dev-tooling-arm64.yaml": "4.25Gi",
    "values-livespec-dev-tooling-master.yaml": "4.25Gi",
    "values-livespec-dev-tooling.yaml": "4.25Gi",
    "values-livespec-driver-claude.yaml": "512Mi",
    "values-livespec-driver-codex.yaml": "512Mi",
    "values-livespec-driver-pi.yaml": "512Mi",
    "values-livespec-orchestrator-beads-fabro.yaml": "6Gi",
    "values-livespec-orchestrator-git-jsonl.yaml": "1Gi",
    "values-livespec-orchestrator-master.yaml": "6Gi",
    "values-livespec-overseer.yaml": "2.25Gi",
    "values-livespec-runtime.yaml": "1.25Gi",
    "values-livespec.yaml": "1.5Gi",
    "values-poweredge-xubuntu-k3s.yaml": "512Mi",
}
_HEADROOM_ROW = re.compile(
    r"^\| `(?P<flavor>headroom-[^`]+)` \| [^|]+ \| "
    r"(?P<allocatable>[0-9.]+) \| (?P<factory>[0-9.]+) \| "
    r"(?P<gates>[0-9.]+) \| [^|]+ \| (?P<quota>[0-9]+)Gi \|$",
    re.MULTILINE,
)


def _documents(path: Path) -> list[dict[str, Any]]:
    """Load a Kueue manifest, giving its worker placeholder a test value."""
    text = (
        path.read_text(encoding="utf-8")
        .replace("@WORKER_CHURN_SLOTS@", "0")
        .replace("@WORKER_MEMORY_QUOTA@", "0Mi")
    )
    return [document for document in yaml.safe_load_all(text) if document]


def _cluster_queues() -> dict[str, dict[str, Any]]:
    """Return ClusterQueues paired to a committed ARC LocalQueue."""
    documents = [
        document
        for path in [
            *_KUEUE.glob("cluster-queue-*.yaml"),
            *(_KUEUE / "worker").glob("cluster-queue-*.yaml"),
        ]
        for document in _documents(path)
    ]
    routed_local_queues = {
        values.get("template", {})
        .get("metadata", {})
        .get("labels", {})
        .get("kueue.x-k8s.io/queue-name")
        for path in _ARC.glob("values-*.yaml")
        if (values := yaml.safe_load(path.read_text(encoding="utf-8")))
    }
    runner_queue_names = {
        document["spec"]["clusterQueue"]
        for document in documents
        if document.get("kind") == "LocalQueue"
        and document.get("metadata", {}).get("namespace") == "arc-runners"
        and document["metadata"]["name"] in routed_local_queues
    }
    return {
        document["metadata"]["name"]: document
        for document in documents
        if document.get("kind") == "ClusterQueue"
        and document["metadata"]["name"] in runner_queue_names
    }


def _memory_quotas(document: dict[str, Any]) -> dict[str, str]:
    """Return a ClusterQueue's memory quotas keyed by ResourceFlavor."""
    return {
        flavor["name"]: str(resource["nominalQuota"])
        for group in document["spec"].get("resourceGroups", [])
        if "memory" in group.get("coveredResources", [])
        for flavor in group.get("flavors", [])
        for resource in flavor.get("resources", [])
        if resource["name"] == "memory"
    }


def _derived_x86_memory_quotas() -> dict[str, str]:
    """Parse and recompute the rounded node headroom in DERIVATION.md."""
    quotas: dict[str, str] = {}
    for match in _HEADROOM_ROW.finditer(_DERIVATION.read_text(encoding="utf-8")):
        allocatable = float(match["allocatable"])
        used = float(match["factory"]) + float(match["gates"])
        quota = int(match["quota"])
        assert quota == max(0, math.floor(allocatable - used)), match.group(0)
        quotas[match["flavor"]] = f"{quota}Gi"
    return quotas


def test_every_runner_values_file_requests_its_recorded_peak_without_a_limit() -> None:
    """Runner values reserve their p95 working set but retain burst headroom."""
    for filename, expected_request in _MEMORY_REQUESTS.items():
        values = yaml.safe_load((_ARC / filename).read_text(encoding="utf-8"))
        [runner] = [
            container
            for container in values["template"]["spec"]["containers"]
            if container["name"] == "runner"
        ]
        resources = runner.get("resources", {})
        assert resources.get("requests", {}).get("memory") == expected_request
        assert "memory" not in resources.get("limits", {})


def _churn_slots(document: dict[str, Any]) -> int:
    """Return a ClusterQueue's nominal churn slots on the fleet flavor."""
    return sum(
        int(resource["nominalQuota"])
        for group in document["spec"].get("resourceGroups", [])
        if "ci-runner.io/churn-slot" in group.get("coveredResources", [])
        for flavor in group.get("flavors", [])
        if flavor["name"] == "churn-slot-flavor"
        for resource in flavor.get("resources", [])
    )


def test_runner_queue_memory_quotas_are_slots_times_the_cohort_memory_per_slot() -> None:
    """Every x86 runner queue covers ONE unpinned flavor sized from its churn slots.

    A hostname-pinned memory flavor per node made Kueue pin runners to the first
    flavor that fit while the churn slots live on the node, so the single flavor
    carries no nodeLabels and the cohort total is the summed per-node headroom.
    """
    headroom = _derived_x86_memory_quotas()
    assert set(headroom) == {
        "headroom-gamingpc",
        "headroom-gmktec",
        "headroom-hp",
        "headroom-poweredge",
    }
    assert headroom["headroom-gmktec"] == "0Gi"
    cohort_gi = sum(int(value.removesuffix("Gi")) for value in headroom.values())

    flavor = next(
        document
        for document in _documents(_KUEUE / "resource-flavor.yaml")
        if document["metadata"]["name"] == "runner-memory-flavor"
    )
    assert "nodeLabels" not in flavor.get("spec", {})
    assert not [
        document
        for document in _documents(_KUEUE / "resource-flavor.yaml")
        if document["metadata"]["name"].startswith("runner-memory-")
        and document["metadata"]["name"] != "runner-memory-flavor"
    ]

    queues = {name: queue for name, queue in _cluster_queues().items() if name != _WORKER_QUEUE}
    assert queues
    total_slots = sum(_churn_slots(queue) for queue in queues.values())
    per_slot_gi = cohort_gi // total_slots
    assert per_slot_gi >= 1
    for name, queue in queues.items():
        assert _memory_quotas(queue) == {
            "runner-memory-flavor": f"{_churn_slots(queue) * per_slot_gi}Gi"
        }, name
    assert sum(_churn_slots(q) * per_slot_gi for q in queues.values()) <= cohort_gi


def test_arm64_runner_queue_covers_one_recorded_runner_request() -> None:
    """The committed worker template keeps memory declared beside its churn slot."""
    worker_queue = _cluster_queues()[_WORKER_QUEUE]
    assert _memory_quotas(worker_queue) == {"churn-slot-worker-arm64-flavor": "0Mi"}
    template = (_KUEUE / "worker" / "cluster-queue-livespec-dev-tooling-arm64.yaml").read_text(
        encoding="utf-8"
    )
    assert "nominalQuota: @WORKER_MEMORY_QUOTA@" in template


def test_the_documented_per_slot_worker_memory_is_the_arm64_runner_request() -> None:
    """DERIVATION.md's per-slot figure is the arm64 runner request, in Mi."""
    values = yaml.safe_load(
        (_ARC / "values-livespec-dev-tooling-arm64.yaml").read_text(encoding="utf-8")
    )
    [runner] = [c for c in values["template"]["spec"]["containers"] if c["name"] == "runner"]
    request = runner["resources"]["requests"]["memory"]
    assert request.endswith("Gi")
    per_slot_mi = int(float(request.removesuffix("Gi")) * 1024)
    documented = re.search(r"`churn slots x (?P<mi>\d+)Mi`", _DERIVATION.read_text("utf-8"))
    assert documented is not None
    assert int(documented["mi"]) == per_slot_mi
