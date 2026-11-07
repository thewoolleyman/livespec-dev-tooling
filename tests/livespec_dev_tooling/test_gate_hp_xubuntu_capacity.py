"""The delegated-gate queue can use hp-xubuntu without cold gate volumes."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import yaml

__all__: list[str] = []

_REPO = Path(__file__).resolve().parents[2]
_GATES_QUEUE = _REPO / "ci-runner" / "k3s" / "phase2" / "kueue" / "cluster-queue-gates.yaml"
_WARM_CACHE = _REPO / "ci-runner" / "k3s" / "phase2" / "warm-cache" / "warm-cache-cronjob.yaml"
_INVENTORY = _REPO / "ansible" / "inventory" / "legacy.yml"


def _named_document(documents: list[dict[str, Any]], *, kind: str, name: str) -> dict[str, Any]:
    """Return exactly one parsed Kubernetes document by kind and name."""
    matched = [
        document
        for document in documents
        if document.get("kind") == kind
        and isinstance(document.get("metadata"), dict)
        and cast(dict[str, Any], document["metadata"]).get("name") == name
    ]
    assert len(matched) == 1, f"expected one {kind}/{name}; found {len(matched)}"
    return matched[0]


def _documents(path: Path) -> list[dict[str, Any]]:
    """Load one multi-document Kubernetes manifest with mapping-only documents."""
    parsed = list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
    assert parsed and all(isinstance(document, dict) for document in parsed)
    return cast(list[dict[str, Any]], parsed)


def _ci_pool_hosts() -> set[str]:
    """Return the ci_pool group's hosts from the committed Ansible inventory."""
    inventory = cast(dict[str, Any], yaml.safe_load(_INVENTORY.read_text(encoding="utf-8")))
    pending: list[dict[str, Any]] = [inventory]
    while pending:
        node = pending.pop()
        for name, child in node.items():
            if not isinstance(child, dict):
                continue
            child_map = cast(dict[str, Any], child)
            if name == "ci_pool":
                return set(cast(dict[str, Any], child_map.get("hosts") or {}))
            pending.append(child_map)
    raise AssertionError("the committed inventory declares no ci_pool group")


def test_gates_cluster_queue_has_a_quota_lane_for_each_pool_node() -> None:
    """Every ci_pool node, including one that joins later, gets its own gate lane.

    A node that joins ci_pool without a gates flavor fails here, so its gate
    posture is decided in the same change that adds it. The lane sizes are
    committed capacity values, so only their shape is asserted.
    """
    documents = _documents(_GATES_QUEUE)
    flavors = {
        cast(dict[str, Any], document["metadata"])["name"]: cast(dict[str, Any], document["spec"])[
            "nodeLabels"
        ]["kubernetes.io/hostname"]
        for document in documents
        if document.get("kind") == "ResourceFlavor"
    }
    assert sorted(flavors.values()) == sorted(_ci_pool_hosts())

    queue = _named_document(documents, kind="ClusterQueue", name="gates-cq")
    resource_group = cast(list[dict[str, Any]], queue["spec"]["resourceGroups"])[0]
    queue_flavors = cast(list[dict[str, Any]], resource_group["flavors"])
    assert sorted(flavor["name"] for flavor in queue_flavors) == sorted(flavors)
    for flavor in queue_flavors:
        quota = {resource["name"]: resource["nominalQuota"] for resource in flavor["resources"]}
        assert set(quota) == {"cpu", "memory"}
        assert isinstance(quota["cpu"], int) and quota["cpu"] > 0
        assert isinstance(quota["memory"], str) and quota["memory"].endswith("Gi")
        assert int(quota["memory"].removesuffix("Gi")) > 0


def test_every_gates_flavor_admits_by_topology_so_tas_is_implied() -> None:
    """Every gates-cq flavor names the hostname Topology, so unannotated gates get TAS."""
    documents = _documents(_GATES_QUEUE)
    topology = _named_document(documents, kind="Topology", name="gates-hostname")
    assert topology["spec"]["levels"] == [{"nodeLabel": "kubernetes.io/hostname"}]
    queue = _named_document(documents, kind="ClusterQueue", name="gates-cq")
    queue_flavors = [
        flavor["name"]
        for group in cast(list[dict[str, Any]], queue["spec"]["resourceGroups"])
        for flavor in group["flavors"]
    ]
    topologies = {
        name: _named_document(documents, kind="ResourceFlavor", name=name)["spec"].get(
            "topologyName"
        )
        for name in queue_flavors
    }
    assert set(topologies.values()) == {"gates-hostname"}
    kinds = [document["kind"] for document in documents]
    assert kinds.index("Topology") < kinds.index("ResourceFlavor")


def test_hp_warm_uv_publisher_uses_its_runner_volume_root() -> None:
    """A gate admitted to hp receives the local-path UV seed instead of a cold volume."""
    daemon_set = _named_document(
        _documents(_WARM_CACHE), kind="DaemonSet", name="warm-uv-cache-populate-hp"
    )
    pod_spec = daemon_set["spec"]["template"]["spec"]
    expressions = pod_spec["affinity"]["nodeAffinity"][
        "requiredDuringSchedulingIgnoredDuringExecution"
    ]["nodeSelectorTerms"][0]["matchExpressions"]
    assert expressions == [
        {
            "key": "kubernetes.io/hostname",
            "operator": "In",
            "values": ["hp-xubuntu"],
        }
    ]
    warm_volume = next(volume for volume in pod_spec["volumes"] if volume["name"] == "warm")
    assert warm_volume["hostPath"]["path"] == "/srv/sandbox-storage/runner-workvols/.warm"
    environment = pod_spec["containers"][0]["env"]
    environment_values = {
        entry["name"]: entry["value"] for entry in environment if "value" in entry
    }
    assert {
        "WARM_ROOT": "/warm",
        "REPOS_FILE": "/config/repos.txt",
        "KEEP_GENERATIONS": "2",
        "WARM_CACHE_UV_ONLY": "true",
    }.items() <= environment_values.items()
