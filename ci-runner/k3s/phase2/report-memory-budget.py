#!/usr/bin/env python3
"""Print the committed node-memory budget without enforcing it.

The report intentionally exits successfully for over-committed nodes.  It is
an adoption aid, not an admission gate: the committed gmktec factory ceiling
is presently larger than the node can hold beside its committed gate lanes.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import yaml

_ROOT = Path(__file__).resolve().parents[3]
_BUDGET = _ROOT / "ci-runner/k3s/phase2/node-memory-budget.yaml"
_GATES = _ROOT / "ci-runner/k3s/phase2/kueue/cluster-queue-gates.yaml"
_REPRO = _ROOT / "ci-runner/k3s/phase2/kueue/cluster-queue-repro-gates.yaml"
_FACTORY_HOST = _ROOT / "ansible/inventory/host_vars/gmktec-xubuntu.yml"
_HOST_VARS = _ROOT / "ansible/inventory/host_vars"
_PROFILES = _ROOT / "ci-runner/k3s/phase0-bare-metal/profiles"
_QUEUES = _ROOT / "ci-runner/k3s/phase2/kueue"
_RUNNER_VALUES = _ROOT / "ci-runner/k3s/phase2/arc"
_SLOT_CAPACITY = re.compile(r"^ADMISSION_CAPACITY_C=(\d+)", re.MULTILINE)


class MemoryQuantityError(ValueError):
    """A committed memory quantity did not use a reportable unit."""


def _load_yaml(path: Path) -> Any:
    with path.open(encoding="utf-8") as source:
        return yaml.safe_load(source)


def _memory_gib(value: str | int | float) -> float:
    """Convert the committed Kubernetes memory spelling to GiB."""
    text = str(value)
    if text.endswith("Gi"):
        return float(text.removesuffix("Gi"))
    if text.endswith("Mi"):
        return float(text.removesuffix("Mi")) / 1024
    raise MemoryQuantityError(value)


def _flavor_memory(paths: Iterable[Path]) -> dict[str, float]:
    """Read each Kueue ResourceFlavor's committed memory quota."""
    quotas: dict[str, float] = {}
    for path in paths:
        for document in yaml.safe_load_all(path.read_text(encoding="utf-8")):
            if not document or document.get("kind") != "ClusterQueue":
                continue
            for group in document["spec"].get("resourceGroups", []):
                for flavor in group.get("flavors", []):
                    for resource in flavor.get("resources", []):
                        if resource["name"] == "memory":
                            quotas[flavor["name"]] = _memory_gib(resource["nominalQuota"])
    return quotas


def factory_pod_request_gib() -> float:
    """Read the factory provider's request once, in its committed MiB unit."""
    host = _load_yaml(_FACTORY_HOST)
    fleet = host["fabro_server_instances"][0]
    request_mib = fleet["sandbox_providers"]["kubernetes"]["process_spec"]["memory_mb"]
    return float(request_mib) / 1024


def factory_pod_budget(node: str, configured: dict[str, Any]) -> int:
    """Read a node ceiling from host_vars unless it has no factory placement."""
    if "factory_pod_budget" in configured:
        return int(configured["factory_pod_budget"])
    host_vars = _load_yaml(_HOST_VARS / f"{node}.yml")
    return int(host_vars["factory_pod_budget"])


def runner_slots(node: str) -> int:
    """Read a node's committed churn-slot capacity from its phase0 profile."""
    profile = (_PROFILES / f"{node}.env").read_text(encoding="utf-8")
    (capacity,) = _SLOT_CAPACITY.findall(profile)
    return int(capacity)


def _queue_slots() -> tuple[dict[str, str], dict[str, int]]:
    """Read each LocalQueue's ClusterQueue and each ClusterQueue's churn slots."""
    local_queues: dict[str, str] = {}
    churn_slots: dict[str, int] = {}
    for path in _QUEUES.glob("cluster-queue-*.yaml"):
        for document in yaml.safe_load_all(path.read_text(encoding="utf-8")):
            if document["kind"] == "LocalQueue":
                local_queues[document["metadata"]["name"]] = document["spec"]["clusterQueue"]
            if document["kind"] == "ClusterQueue":
                for group in document["spec"].get("resourceGroups", []):
                    for flavor in group["flavors"]:
                        for resource in flavor["resources"]:
                            if resource["name"] == "ci-runner.io/churn-slot":
                                churn_slots[document["metadata"]["name"]] = resource["nominalQuota"]
    return local_queues, churn_slots


def runner_request_gib() -> float:
    """Return a churn slot's expected runner memory request in GiB.

    Each fleet queue's committed runner request is weighted by that queue's
    committed churn-slot quota, so the figure follows the cohort's own mix.  A
    runner is not the cohort's per-slot memory quota: that quota is a fleet-wide
    cap, not a request any pod makes.
    """
    local_queues, churn_slots = _queue_slots()
    weighted = 0.0
    slots = 0
    for path in _RUNNER_VALUES.glob("values-*.yaml"):
        values = _load_yaml(path)
        template = values.get("template", {})
        queue = template.get("metadata", {}).get("labels", {}).get("kueue.x-k8s.io/queue-name")
        quota = churn_slots.get(local_queues.get(queue, ""), 0)
        if quota == 0:
            continue
        runner = next(c for c in template["spec"]["containers"] if c["name"] == "runner")
        weighted += quota * _memory_gib(runner["resources"]["requests"]["memory"])
        slots += quota
    return weighted / slots


def runner_memory_gib(node: str, configured: dict[str, Any]) -> float:
    """Return a node's CI-runner claim: its committed slots times the request."""
    if "runner_memory_gib" in configured:
        return float(configured["runner_memory_gib"])
    return runner_slots(node) * runner_request_gib()


def report() -> tuple[list[str], list[tuple[str, float]]]:
    """Return human-readable rows and the committed over-commit findings."""
    budget = _load_yaml(_BUDGET)["nodes"]
    flavors = _flavor_memory([_GATES, _REPRO])
    factory_request = factory_pod_request_gib()
    rows = [
        "Memory budget report (REPORT-ONLY; no fleet admission check is armed).",
        "Factory memory is the committed ceiling, not live pod demand; runners are "
        "committed churn slots times the slot-weighted committed runner request.",
        "node | allocatable | gates | repro | factory | runners | system | total | status",
    ]
    findings: list[tuple[str, float]] = []
    for node, configured in budget.items():
        gates = float(
            configured["gate_memory_gib"]
            if "gate_memory_gib" in configured
            else flavors[configured["gate_flavor"]]
        )
        repro = float(
            configured["repro_memory_gib"]
            if "repro_memory_gib" in configured
            else flavors[configured["repro_flavor"]]
        )
        factory = factory_pod_budget(node, configured) * factory_request
        runners = runner_memory_gib(node, configured)
        system = float(configured["system_memory_gib"])
        allocatable = float(configured["allocatable_memory_gib"])
        total = gates + repro + factory + runners + system
        shortfall = total - allocatable
        status = "fits" if shortfall <= 0 else f"OVER by {shortfall:.1f}Gi"
        rows.append(
            f"{node} | {allocatable:.2f}Gi | {gates:.1f}Gi | {repro:.1f}Gi | "
            f"{factory:.1f}Gi | {runners:.1f}Gi | {system:.1f}Gi | {total:.1f}Gi | {status}"
        )
        if shortfall > 0:
            findings.append((node, shortfall))
    return rows, findings


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    rows, findings = report()
    sys.stdout.write("\n".join(rows) + "\n")
    for node, shortfall in findings:
        sys.stdout.write(f"OVER-COMMITTED: {node} shortfall={shortfall:.1f}Gi\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
