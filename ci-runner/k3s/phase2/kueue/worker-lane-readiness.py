#!/usr/bin/env python3
"""Print the enrolled workers that may offer capacity to every worker lane.

The queue converger and the factory-admission reconciler consume this one
classification.  A worker which Kubernetes no longer considers Ready, or which
has its unreachable taint, must not offer a new gate, CI, or factory admission.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

WORKER_CLASS = "homelab-worker.livespec.dev/class"
UNREACHABLE = "node.kubernetes.io/unreachable"


def is_ready(node: dict[str, Any]) -> bool:
    """Whether an enrolled worker can offer a new lane admission."""
    conditions = (node.get("status") or {}).get("conditions") or []
    ready = next(
        (condition.get("status") for condition in conditions if condition.get("type") == "Ready"),
        None,
    )
    taints = (node.get("spec") or {}).get("taints") or []
    unreachable = any(taint.get("key") == UNREACHABLE for taint in taints)
    return ready == "True" and not unreachable


def worker_rows(nodes: list[dict[str, Any]]) -> list[tuple[str, str, str, str, str]]:
    """Return (state, name, arch, slots, gate_share) for enrolled workers."""
    rows: list[tuple[str, str, str, str, str]] = []
    for node in nodes:
        metadata = node.get("metadata") or {}
        labels = metadata.get("labels") or {}
        if labels.get(WORKER_CLASS) != "worker":
            continue
        status = node.get("status") or {}
        capacity = status.get("capacity") or {}
        rows.append(
            (
                "ready" if is_ready(node) else "not-ready",
                str(metadata.get("name", "<unnamed>")),
                str(labels.get("kubernetes.io/arch", "")),
                str(capacity.get("ci-runner.io/churn-slot", "")),
                str(labels.get("homelab-worker.livespec.dev/gate-share-millicores", "")),
            )
        )
    return rows


def main() -> int:
    arguments = sys.argv[1:]
    if len(arguments) > 1:
        raise SystemExit(f"usage: {Path(sys.argv[0]).name} [nodes.json]")  # noqa: TRY003
    source = Path(arguments[0]) if arguments else None
    try:
        document = json.loads(source.read_text(encoding="utf-8") if source else sys.stdin.read())
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"could not read Node list: {error}") from error  # noqa: TRY003
    for row in worker_rows(document.get("items") or []):
        print("\t".join(row))  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
