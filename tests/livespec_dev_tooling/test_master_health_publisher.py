"""Unit coverage for the informational ci-green master-health publisher."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from livespec_dev_tooling.master_health_publisher import publish_master_health


@dataclass
class _Forge:
    """Record the one check-run write the publisher is allowed to make."""

    check_runs: list[dict[str, Any]] = field(default_factory=list)

    def create_check_run(self, **payload: Any) -> None:
        self.check_runs.append(payload)


def test_publishes_a_non_required_external_master_health_summary() -> None:
    """An evidenced external gating failure remains neutral, not a required gate."""
    forge = _Forge()

    summary = publish_master_health(
        forge=forge,
        head_sha="a" * 40,
        run_id=418,
        ci_green_passed=True,
        jobs=[
            {
                "name": "check-python",
                "result": "failure",
                "external_only": True,
                "defect_findings": 0,
                "records": [{"cause": "network"}],
            }
        ],
        episode={"earliest_run_id": 417},
        expired=True,
    )

    assert summary == {
        "verdict": "external",
        "head_sha": "a" * 40,
        "run_id": 418,
        "episode": {"earliest_run_id": 417},
        "expired": True,
        "jobs": [
            {
                "name": "check-python",
                "external_only": True,
                "defect_findings": 0,
                "records": [{"cause": "network"}],
            }
        ],
    }
    assert forge.check_runs == [
        {
            "name": "master-health",
            "head_sha": "a" * 40,
            "status": "completed",
            "conclusion": "neutral",
            "output": {
                "title": "master-health: external",
                "summary": json.dumps(summary, separators=(",", ":"), sort_keys=True),
            },
        }
    ]
