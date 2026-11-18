"""Red coverage for the master-health publisher's episode clock."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, cast

import pytest

import livespec_dev_tooling.master_health_publisher as publisher
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


@dataclass
class _AlertForge:
    """Minimal forge seam for publisher issue reconciliation."""

    issues: list[dict[str, Any]] = field(default_factory=list)
    check_runs: list[dict[str, Any]] = field(default_factory=list)
    malformed_search: bool = False

    def create_check_run(self, **payload: Any) -> None:
        self.check_runs.append(payload)

    def find_open_issues(self, **query: str) -> list[dict[str, Any]]:
        if self.malformed_search:
            return cast(list[dict[str, Any]], {"not": "a sequence"})
        return [
            issue
            for issue in self.issues
            if issue.get("open", True)
            and all(
                value in issue.get("labels", []) if key == "label" else issue.get(key) == value
                for key, value in query.items()
            )
        ]

    def create_issue(self, *, title: str, labels: list[str]) -> None:
        self.issues.append({"title": title, "labels": labels, "open": True})

    def close_issue(self, *, issue: dict[str, Any], comment: str) -> None:
        issue["open"] = False
        issue["comment"] = comment


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


def test_expired_external_alert_is_deduplicated_and_green_closes_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The publisher owns the clock and closes the episode's needs-attention issue."""
    monkeypatch.setattr(
        publisher,
        "_publication_time",
        lambda: datetime(2026, 11, 18, tzinfo=timezone.utc),
    )
    forge = _AlertForge()
    first = publish_master_health(
        forge=forge,
        head_sha="a" * 40,
        run_id=418,
        ci_green_passed=True,
        jobs=[{"name": "check-python", "result": "failure", "external_only": True}],
        episode={"earliest_run_id": 417, "started_at": "2026-11-16T23:59:59Z"},
    )
    second = publish_master_health(
        forge=forge,
        head_sha="a" * 40,
        run_id=419,
        ci_green_passed=True,
        jobs=[{"name": "check-python", "result": "failure", "external_only": True}],
        episode={"earliest_run_id": 417, "started_at": "2026-11-16T23:59:59Z"},
    )
    _ = publish_master_health(
        forge=forge,
        head_sha="b" * 40,
        run_id=420,
        ci_green_passed=True,
        jobs=[{"name": "check-python", "result": "success"}],
    )

    assert (first["expired"], second["expired"]) == (True, True)
    assert forge.issues == [
        {
            "title": "master-green: external episode 417",
            "labels": ["master-green-external-red"],
            "open": False,
            "comment": "Closing because master-health is green.",
        }
    ]


def test_unreadable_alert_search_and_episode_id_do_not_create_an_episode_issue() -> None:
    """Malformed issue responses and malformed episode ids cannot create alert duplicates."""
    forge = _AlertForge(malformed_search=True)

    _ = publish_master_health(
        forge=forge,
        head_sha="a" * 40,
        run_id=417,
        ci_green_passed=True,
        jobs=[{"name": "check-python", "result": "failure", "external_only": True}],
    )
    _ = publish_master_health(
        forge=forge,
        head_sha="a" * 40,
        run_id=418,
        ci_green_passed=True,
        jobs=[{"name": "check-python", "result": "failure", "external_only": True}],
        episode={"earliest_run_id": "not-an-id", "started_at": "2026-11-17T00:00:00Z"},
        expired=True,
    )

    assert forge.issues == [
        {
            "title": "master-green: episode unreadable",
            "labels": ["master-green-external-red"],
            "open": True,
        }
    ]


def test_malformed_episode_clock_never_expires_an_external_episode() -> None:
    """Only a timezone-aware timestamp can start the external-red clock."""
    forge = _AlertForge()

    for started_at in (None, "not-a-timestamp", "2026-11-17T00:00:00"):
        summary = publish_master_health(
            forge=forge,
            head_sha="a" * 40,
            run_id=418,
            ci_green_passed=True,
            jobs=[{"name": "check-python", "result": "failure", "external_only": True}],
            episode={"earliest_run_id": 417, "started_at": started_at},
        )

        assert summary["expired"] is False

    assert forge.issues == []
