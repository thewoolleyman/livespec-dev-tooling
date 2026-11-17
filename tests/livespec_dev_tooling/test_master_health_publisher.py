"""Unit coverage for the informational ci-green master-health publisher.

The contract separates ci-green's required status from the non-required
``master-health`` check run.  A failed ci-green is therefore a defect even when
every gating job returned success: publishing ``green`` there would let the
master-health consumer accept a red aggregate.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from livespec_dev_tooling.master_health_publisher import publish_master_health

_HEAD_SHA = "a" * 40
_RUN_ID = 418


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
        head_sha=_HEAD_SHA,
        run_id=_RUN_ID,
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
        "head_sha": _HEAD_SHA,
        "run_id": _RUN_ID,
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
            "head_sha": _HEAD_SHA,
            "status": "completed",
            "conclusion": "neutral",
            "output": {
                "title": "master-health: external",
                "summary": json.dumps(summary, separators=(",", ":"), sort_keys=True),
            },
        }
    ]


def test_red_ci_green_publishes_neutral_defect_master_health() -> None:
    """A failed ci-green is defect even with wholly green gating jobs."""
    forge = _Forge()

    _ = publish_master_health(
        forge=forge,
        head_sha=_HEAD_SHA,
        run_id=_RUN_ID,
        ci_green_passed=False,
        jobs=[
            {
                "name": "check-python",
                "result": "success",
                "external_only": False,
                "defect_findings": 0,
                "records": [],
            }
        ],
    )

    assert len(forge.check_runs) == 1
    published = forge.check_runs[0]
    assert published["name"] == "master-health"
    assert published["head_sha"] == _HEAD_SHA
    assert published["conclusion"] == "neutral"
    assert published["output"]["title"] == "master-health: defect"
    assert json.loads(published["output"]["summary"])["verdict"] == "defect"


def test_green_publishes_success_with_no_episode() -> None:
    """No failed gating job and a passing ci-green is green, success, no episode."""
    forge = _Forge()

    summary = publish_master_health(
        forge=forge,
        head_sha=_HEAD_SHA,
        run_id=_RUN_ID,
        ci_green_passed=True,
        jobs=[{"name": "check-python", "result": "success"}],
        episode={"earliest_run_id": 417},
        expired=True,
    )

    assert summary["verdict"] == "green"
    assert summary["episode"] is None
    assert summary["expired"] is False
    assert forge.check_runs[0]["conclusion"] == "success"
    assert forge.check_runs[0]["output"]["title"] == "master-health: green"


def test_one_defect_job_among_external_jobs_reads_defect() -> None:
    """Every failed gating job must be external-only for the verdict to be external."""
    forge = _Forge()

    summary = publish_master_health(
        forge=forge,
        head_sha=_HEAD_SHA,
        run_id=_RUN_ID,
        ci_green_passed=True,
        jobs=[
            {"name": "a", "result": "failure", "external_only": True},
            {"name": "b", "result": "failure", "external_only": False, "defect_findings": 1},
        ],
    )

    assert summary["verdict"] == "defect"
    assert forge.check_runs[0]["conclusion"] == "neutral"
    assert forge.check_runs[0]["output"]["title"] == "master-health: defect"
