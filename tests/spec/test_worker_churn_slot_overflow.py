"""CI overflow onto a container worker, `SPECIFICATION/non-functional-requirements.md`, "Homelab worker nodes".

The "Live production load" bullet and the scenario "CI overflows onto a container worker only when
fleet capacity is full" (v181, livespec-dev-tooling-eorpen). These read the committed Kueue
manifests, the ARC release table of `converge-ci-stack.sh` and `workload-arch.conf`, and assert:

- the fleet churn-slot flavor matches every K3s pool node and no container worker;
- the arm64 worker flavor selects the worker class and architecture and carries the class-taint
  toleration Kueue adds only to a pod it admits on that flavor;
- the worker queue holds the worker flavor's rendered quota and nothing else;
- a repository's queue lists the worker flavor exactly when its release line includes arm64, and
  then AFTER the fleet flavor at nominalQuota 0, so it reaches the worker only by borrowing.
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
_KUEUE = _PHASE2 / "kueue"
_FLEET = "churn-slot-flavor"
_WORKER = "churn-slot-worker-arm64-flavor"
_CLASS_TAINT = "homelab-worker.livespec.dev/class"
_CHURN = "ci-runner.io/churn-slot"

# Node labels as the production cluster reports them (read 2026-11-10 from poweredge-xubuntu):
# a K3s pool node, and macbook-m4-max-homelab-worker, a container worker running upstream kubelet.
_POOL_NODE = {
    "k3s-role": "arc-runner-host",
    "kubernetes.io/arch": "amd64",
    "node.kubernetes.io/instance-type": "k3s",
}
_ARM64_WORKER = {
    "k3s-role": "arc-runner-host",
    "kubernetes.io/arch": "arm64",
    _CLASS_TAINT: "worker",
}
_AMD64_WORKER = {**_ARM64_WORKER, "kubernetes.io/arch": "amd64"}


def _documents(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8").replace("@WORKER_CHURN_SLOTS@", "0")
    return [d for d in yaml.safe_load_all(text) if d]


def _flavors() -> dict[str, dict[str, Any]]:
    docs = _documents(_KUEUE / "resource-flavor.yaml")
    return {d["metadata"]["name"]: d["spec"] for d in docs if d["kind"] == "ResourceFlavor"}


def _matches(*, node: dict[str, str], flavor: dict[str, Any]) -> bool:
    return all(node.get(key) == value for key, value in flavor["nodeLabels"].items())


def _churn_flavors(queue: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    return [
        (flavor["name"], resource)
        for group in queue["spec"]["resourceGroups"]
        if _CHURN in group.get("coveredResources", [])
        for flavor in group["flavors"]
        for resource in flavor["resources"]
        if resource["name"] == _CHURN
    ]


def _release_arches() -> dict[str, set[str]]:
    lines = (_PHASE2 / "workload-arch.conf").read_text(encoding="utf-8").splitlines()
    fields = [line.split() for line in lines if line.startswith("release ")]
    return {f[1]: set(f[2].split(",")) for f in fields}


def _release_queues() -> dict[str, str]:
    """Each ARC release's ClusterQueue: release -> values file -> queue-name label -> LocalQueue."""
    converge = (_PHASE2 / "reconstruct" / "converge-ci-stack.sh").read_text(encoding="utf-8")
    values = dict(
        re.findall(r'^\s*\[([a-z0-9-]+)\]="(values-[a-z0-9-]+\.yaml)"', converge, re.MULTILINE)
    )
    local_queues = {
        d["metadata"]["name"]: d["spec"]["clusterQueue"]
        for path in [
            *_KUEUE.glob("cluster-queue-*.yaml"),
            *(_KUEUE / "worker").glob("cluster-queue-*.yaml"),
        ]
        for d in _documents(path)
        if d["kind"] == "LocalQueue"
    }
    queues: dict[str, str] = {}
    for release, file in values.items():
        label = re.search(
            r"kueue\.x-k8s\.io/queue-name:\s*(\S+)",
            (_PHASE2 / "arc" / file).read_text(encoding="utf-8"),
        )
        if label:
            queues[release] = local_queues[label.group(1)]
    return queues


def _fleet_queues() -> dict[str, dict[str, Any]]:
    return {
        d["metadata"]["name"]: d
        for path in _KUEUE.glob("cluster-queue-*.yaml")
        for d in _documents(path)
        if d["kind"] == "ClusterQueue" and _churn_flavors(d)
    }


def test_the_fleet_flavor_matches_every_pool_node_and_no_container_worker() -> None:
    fleet = _flavors()[_FLEET]
    assert _matches(node=_POOL_NODE, flavor=fleet)
    assert not _matches(node=_ARM64_WORKER, flavor=fleet)
    assert not _matches(node=_AMD64_WORKER, flavor=fleet)


def test_the_worker_flavor_selects_arm64_workers_and_tolerates_the_class_taint() -> None:
    worker = _flavors()[_WORKER]
    assert _matches(node=_ARM64_WORKER, flavor=worker)
    assert not _matches(node=_AMD64_WORKER, flavor=worker)
    assert not _matches(node=_POOL_NODE, flavor=worker)
    assert {
        "key": _CLASS_TAINT,
        "operator": "Equal",
        "value": "worker",
        "effect": "NoSchedule",
    } in (worker.get("tolerations", []))
    assert "nodeTaints" not in worker


def test_the_worker_queue_holds_only_the_worker_flavor_at_its_rendered_quota() -> None:
    raw = (_KUEUE / "worker" / "cluster-queue-livespec-dev-tooling-arm64.yaml").read_text(
        encoding="utf-8"
    )
    assert "nominalQuota: @WORKER_CHURN_SLOTS@" in raw
    queue = next(
        d
        for d in _documents(_KUEUE / "worker" / "cluster-queue-livespec-dev-tooling-arm64.yaml")
        if d["kind"] == "ClusterQueue"
    )
    assert [name for name, _ in _churn_flavors(queue)] == [_WORKER]


def test_no_fleet_queue_lists_the_worker_flavor_unless_its_releases_all_include_arm64() -> None:
    arches = _release_arches()
    feeding: dict[str, set[str]] = {}
    for release, queue in _release_queues().items():
        feeding.setdefault(queue, set()).add(release)
    fleet = _fleet_queues()
    assert fleet
    for name, queue in fleet.items():
        releases = feeding.get(name, set())
        eligible = bool(releases) and all("arm64" in arches[r] for r in releases)
        listed = [flavor for flavor, _ in _churn_flavors(queue)]
        assert listed[0] == _FLEET, name
        assert (_WORKER in listed) == eligible, (
            f"{name} (fed by {sorted(releases)}): lists the worker flavor iff every release "
            "feeding it declares arm64 in workload-arch.conf"
        )


def test_an_eligible_queue_reaches_the_worker_only_by_borrowing_after_the_fleet_flavor() -> None:
    for name, queue in _fleet_queues().items():
        listed = _churn_flavors(queue)
        names = [flavor for flavor, _ in listed]
        if _WORKER not in names:
            continue
        assert names == [_FLEET, _WORKER], name
        worker = dict(listed)[_WORKER]
        assert worker["nominalQuota"] == 0, name
        assert "borrowingLimit" not in worker, name


def test_every_release_feeding_a_queue_is_declared_in_workload_arch_conf() -> None:
    assert set(_release_queues()) <= set(_release_arches())
