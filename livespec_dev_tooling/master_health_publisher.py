"""Publish ci-green's informational master-health check run.

The aggregate ``ci-green`` status remains the required merge gate.  This
publisher records the separate, non-required explanation of that status so a
reader can distinguish a defect from a fully evidenced external failure.
"""

# ruff: noqa: PLR0913

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

__all__: list[str] = ["publish_master_health"]

_SUCCESSFUL_RESULTS = frozenset({"success", "skipped"})


def publish_master_health(
    *,
    forge: Any,
    head_sha: str,
    run_id: int,
    ci_green_passed: bool,
    jobs: Sequence[Mapping[str, Any]],
    episode: Mapping[str, Any] | None = None,
    expired: bool = False,
) -> dict[str, Any]:
    """Publish one completed ``master-health`` run and return its summary.

    ``external`` is deliberately unavailable when ci-green's own reads failed:
    an aggregate which did not establish its inputs is a defect even if every
    reported gating job appears green.
    """
    failed_jobs = [job for job in jobs if job.get("result") not in _SUCCESSFUL_RESULTS]
    verdict = (
        "green"
        if ci_green_passed and not failed_jobs
        else "external"
        if ci_green_passed and all(bool(job.get("external_only")) for job in failed_jobs)
        else "defect"
    )
    summary: dict[str, Any] = {
        "verdict": verdict,
        "head_sha": head_sha,
        "run_id": run_id,
        "episode": None if verdict == "green" else episode,
        "expired": False if verdict == "green" else expired,
        "jobs": [
            {
                "name": job.get("name"),
                "external_only": bool(job.get("external_only")),
                "defect_findings": job.get("defect_findings", 0),
                "records": job.get("records", []),
            }
            for job in jobs
        ],
    }
    forge.create_check_run(
        name="master-health",
        head_sha=head_sha,
        status="completed",
        conclusion="success" if verdict == "green" else "neutral",
        output={
            "title": f"master-health: {verdict}",
            "summary": json.dumps(summary, separators=(",", ":"), sort_keys=True),
        },
    )
    return summary
