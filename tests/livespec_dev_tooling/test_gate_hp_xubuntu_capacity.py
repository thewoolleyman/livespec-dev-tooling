"""The delegated-gate queue can use hp-xubuntu without cold gate volumes."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import yaml

__all__: list[str] = []

_REPO = Path(__file__).resolve().parents[2]
_GATES_QUEUE = _REPO / "ci-runner" / "k3s" / "phase2" / "kueue" / "cluster-queue-gates.yaml"
_WARM_CACHE = _REPO / "ci-runner" / "k3s" / "phase2" / "warm-cache" / "warm-cache-cronjob.yaml"


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


def test_gates_cluster_queue_has_a_quota_lane_for_each_gate_node() -> None:
    """Kueue can admit one gate on hp alongside gmktec's three-gate lane."""
    documents = _documents(_GATES_QUEUE)
    flavors = {
        cast(dict[str, Any], document["metadata"])["name"]: cast(dict[str, Any], document["spec"])[
            "nodeLabels"
        ]["kubernetes.io/hostname"]
        for document in documents
        if document.get("kind") == "ResourceFlavor"
    }
    assert flavors == {
        "gates-flavor": "gmktec-xubuntu",
        "gates-hp-flavor": "hp-xubuntu",
    }

    queue = _named_document(documents, kind="ClusterQueue", name="gates-cq")
    resource_group = cast(list[dict[str, Any]], queue["spec"]["resourceGroups"])[0]
    quotas = {
        flavor["name"]: {
            resource["name"]: resource["nominalQuota"] for resource in flavor["resources"]
        }
        for flavor in resource_group["flavors"]
    }
    assert quotas == {
        "gates-flavor": {"cpu": 15, "memory": "24Gi"},
        "gates-hp-flavor": {"cpu": 5, "memory": "8Gi"},
    }


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
