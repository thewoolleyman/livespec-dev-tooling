#!/usr/bin/env python3
"""Print the committed node-memory budget without enforcing it.

The report intentionally exits successfully for over-committed nodes.  It is
an adoption aid, not an admission gate: gmktec's committed factory ceiling is
larger than it can hold beside its committed gate lanes.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml

_ROOT = Path(__file__).resolve().parents[3]
_BUDGET = _ROOT / "ci-runner/k3s/phase2/node-memory-budget.yaml"
_FACTORY_HOST = _ROOT / "ansible/inventory/host_vars/gmktec-xubuntu.yml"
_HOST_VARS = _ROOT / "ansible/inventory/host_vars"


def _load_yaml(path: Path) -> Any:
    with path.open(encoding="utf-8") as source:
        return yaml.safe_load(source)


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


def report() -> tuple[list[str], list[tuple[str, float]]]:
    """Return report rows and committed over-commit findings."""
    budget = _load_yaml(_BUDGET)["nodes"]
    factory_request = factory_pod_request_gib()
    rows = [
        "Memory budget report (REPORT-ONLY; no fleet admission check is armed).",
        "Factory memory is the committed ceiling, not live pod demand.",
        "node | allocatable | gates | repro | factory | system | total | status",
    ]
    findings: list[tuple[str, float]] = []
    for node, configured in budget.items():
        gates = float(configured["gate_memory_gib"])
        repro = float(configured["repro_memory_gib"])
        factory = round(factory_pod_budget(node, configured) * factory_request, 1)
        system = float(configured["system_memory_gib"])
        allocatable = float(configured["allocatable_memory_gib"])
        total = gates + repro + factory + system
        shortfall = total - allocatable
        status = "fits" if shortfall <= 0 else f"OVER by {shortfall:.1f}Gi"
        rows.append(
            " | ".join(
                (
                    node,
                    f"{allocatable:.2f}Gi",
                    f"{gates:.1f}Gi",
                    f"{repro:.1f}Gi",
                    f"{factory:.1f}Gi",
                    f"{system:.1f}Gi",
                    f"{total:.1f}Gi",
                    status,
                )
            )
        )
        if shortfall > 0:
            findings.append((node, shortfall))
    return rows, findings


def main() -> int:
    _ = argparse.ArgumentParser(description=__doc__).parse_args()
    rows, findings = report()
    _ = sys.stdout.write("\n".join(rows) + "\n")
    for node, shortfall in findings:
        _ = sys.stdout.write(f"OVER-COMMITTED: {node} shortfall={shortfall:.1f}Gi\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
