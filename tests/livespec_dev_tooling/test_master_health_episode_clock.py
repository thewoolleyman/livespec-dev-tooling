"""Red coverage for the master-health publisher's episode clock."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from livespec_dev_tooling.master_health_publisher import publish_master_health


@dataclass
class _Forge:
    """Record the bounded reads the publisher needs to derive one episode."""

    check_runs: list[dict[str, Any]] = field(default_factory=list)
    reads: list[tuple[str, int | None]] = field(default_factory=list)

    def create_check_run(self, **payload: Any) -> None:
        self.check_runs.append(payload)

    def list_master_push_runs(self) -> list[dict[str, Any]]:
        self.reads.append(("runs", None))
        return [
            {
                "id": 418,
                "head_sha": "a" * 40,
                "conclusion": "failure",
                "completed_at": "2026-11-17T12:00:00Z",
            },
            {
                "id": 417,
                "head_sha": "b" * 40,
                "conclusion": "cancelled",
                "completed_at": "2026-11-17T11:55:00Z",
            },
            {
                "id": 416,
                "head_sha": "c" * 40,
                "conclusion": "failure",
                "completed_at": "2026-11-17T11:50:00Z",
            },
        ]

    def read_master_health(self, run_id: int) -> dict[str, Any] | None:
        self.reads.append(("master-health", run_id))
        if run_id != 416:
            return None
        return {
            "run_id": 416,
            "head_sha": "c" * 40,
            "verdict": "external",
            "episode": {
                "earliest_run_id": 400,
                "started_at": "2026-11-17T09:00:00Z",
            },
        }


def test_external_head_carries_the_nearest_episode_past_a_cancelled_run() -> None:
    """One runs read and one carrier read preserve the existing episode clock."""
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
            }
        ],
    )

    assert summary["episode"] == {
        "earliest_run_id": 400,
        "started_at": "2026-11-17T09:00:00Z",
    }
    assert forge.reads == [("runs", None), ("master-health", 416)]
