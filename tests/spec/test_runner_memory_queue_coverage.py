"""Runner-memory admission remains aligned between ARC and Kueue.

ARC runner pods are admitted through the LocalQueue named in their values file.
Every resource requested by the runner container therefore has to be covered by
the paired ClusterQueue; otherwise Kueue leaves that resource uncovered at
admission and the Kubernetes scheduler can overpack the node.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

__all__: list[str] = []

pytestmark = pytest.mark.integration

_PHASE2 = Path(__file__).resolve().parents[2] / "ci-runner" / "k3s" / "phase2"
_ARC = _PHASE2 / "arc"
_KUEUE = _PHASE2 / "kueue"
_MEMORY = "memory"


def _documents(path: Path) -> list[dict[str, Any]]:
    """Load one committed Kueue manifest, including its worker quota template."""
    text = (
        path.read_text(encoding="utf-8")
        .replace("@WORKER_CHURN_SLOTS@", "0")
        .replace("@WORKER_MEMORY_QUOTA@", "0Mi")
    )
    return [document for document in yaml.safe_load_all(text) if document]


def _local_queues() -> dict[str, str]:
    """Map each committed LocalQueue to the ClusterQueue that admits it."""
    return {
        document["metadata"]["name"]: document["spec"]["clusterQueue"]
        for path in [
            *_KUEUE.glob("cluster-queue-*.yaml"),
            *(_KUEUE / "worker").glob("cluster-queue-*.yaml"),
        ]
        for document in _documents(path)
        if document.get("kind") == "LocalQueue"
    }


def _cluster_queues() -> dict[str, set[str]]:
    """Map every committed ClusterQueue to the resources it covers."""
    return {
        document["metadata"]["name"]: {
            resource
            for group in document["spec"].get("resourceGroups", [])
            for resource in group.get("coveredResources", [])
        }
        for path in [
            *_KUEUE.glob("cluster-queue-*.yaml"),
            *(_KUEUE / "worker").glob("cluster-queue-*.yaml"),
        ]
        for document in _documents(path)
        if document.get("kind") == "ClusterQueue"
    }


def _routed_runner_requests() -> dict[str, tuple[str, set[str]]]:
    """Return each Kueue-routed scale set's ClusterQueue and runner requests."""
    local_queues = _local_queues()
    routed: dict[str, tuple[str, set[str]]] = {}
    for path in sorted(_ARC.glob("values-*.yaml")):
        values = yaml.safe_load(path.read_text(encoding="utf-8"))
        label = (
            values.get("template", {})
            .get("metadata", {})
            .get("labels", {})
            .get("kueue.x-k8s.io/queue-name")
        )
        if label is None or label not in local_queues:
            continue
        [runner] = [
            container
            for container in values["template"]["spec"]["containers"]
            if container["name"] == "runner"
        ]
        requests = set(runner.get("resources", {}).get("requests", {}))
        routed[path.name] = (local_queues[label], requests)
    return routed


def test_every_kueue_routed_runner_requests_memory_that_its_clusterqueue_covers() -> None:
    """Runner memory is requested and included in the queue's admission resources."""
    queues = _cluster_queues()
    missing_memory: list[str] = []
    uncovered: dict[str, list[str]] = {}
    for values_file, (queue, requests) in _routed_runner_requests().items():
        if _MEMORY not in requests:
            missing_memory.append(values_file)
        missing = sorted(requests - queues[queue])
        if missing:
            uncovered[values_file] = missing

    assert not missing_memory, (
        "every Kueue-routed runner pod must request memory so Kubernetes accounts for "
        f"its measured working set; missing_memory={missing_memory}"
    )
    assert not uncovered, (
        "every resource requested by a Kueue-routed runner must be covered by its "
        f"ClusterQueue; uncovered={uncovered}"
    )
