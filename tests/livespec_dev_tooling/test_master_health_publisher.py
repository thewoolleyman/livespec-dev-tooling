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


@dataclass
class _EpisodeForge:
    """In-memory forge responses for master-push episode-clock scenarios."""

    runs: list[dict[str, Any]]
    master_health: dict[int, object] = field(default_factory=dict)
    check_runs: list[dict[str, Any]] = field(default_factory=list)
    reads: list[tuple[str, int | None]] = field(default_factory=list)

    def create_check_run(self, **payload: Any) -> None:
        self.check_runs.append(payload)

    def list_master_push_runs(self) -> list[dict[str, Any]]:
        self.reads.append(("runs", None))
        return self.runs

    def read_master_health(self, run_id: int) -> object:
        self.reads.append(("master-health", run_id))
        return self.master_health.get(run_id)


def _external_summary(*, forge: Any, run_id: int) -> dict[str, Any]:
    """Publish an external result so its episode is derived from forge history."""
    return publish_master_health(
        forge=forge,
        head_sha="a" * 40,
        run_id=run_id,
        ci_green_passed=True,
        jobs=[{"name": "check-python", "result": "failure", "external_only": True}],
    )


@dataclass
class _MalformedRunsForge:
    """Forge whose recent-runs response has an unexpected JSON shape."""

    check_runs: list[dict[str, Any]] = field(default_factory=list)

    def create_check_run(self, **payload: Any) -> None:
        self.check_runs.append(payload)

    def list_master_push_runs(self) -> object:
        return {"runs": "not-a-sequence"}


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


def test_episode_starts_at_the_oldest_failure_after_a_success() -> None:
    """The preceding success starts a fresh episode at its oldest failed run."""
    forge = _EpisodeForge(
        runs=[
            {"id": 418, "conclusion": "failure", "completed_at": "2026-11-17T12:00:00Z"},
            {"id": 417, "conclusion": "failure", "completed_at": "2026-11-17T11:00:00Z"},
            {"id": 416, "conclusion": "success", "completed_at": "2026-11-17T10:00:00Z"},
        ]
    )

    summary = _external_summary(forge=forge, run_id=418)

    assert summary["episode"] == {
        "earliest_run_id": 417,
        "started_at": "2026-11-17T11:00:00Z",
    }
    assert forge.reads == [("runs", None), ("master-health", 417)]


def test_episode_is_null_after_two_prior_runs_do_not_carry_one() -> None:
    """Two checked non-carriers bound the historical master-health reads."""
    forge = _EpisodeForge(
        runs=[
            {"id": 418, "conclusion": "failure", "completed_at": "2026-11-17T12:00:00Z"},
            {"id": 417, "conclusion": "failure", "completed_at": "2026-11-17T11:00:00Z"},
            {"id": 416, "conclusion": "failure", "completed_at": "2026-11-17T10:00:00Z"},
        ],
        master_health={417: {"episode": None}, 416: {"episode": "not-a-mapping"}},
    )

    summary = _external_summary(forge=forge, run_id=418)

    assert summary["episode"] is None
    assert forge.reads == [
        ("runs", None),
        ("master-health", 417),
        ("master-health", 416),
    ]


def test_episode_skips_non_carrier_runs_when_finding_a_prior_episode() -> None:
    """Cancelled, skipped and unfinished runs are transparent to the clock."""
    episode = {"earliest_run_id": 400, "started_at": "2026-11-17T09:00:00Z"}
    forge = _EpisodeForge(
        runs=[
            {"id": 418, "conclusion": "failure", "completed_at": "2026-11-17T12:00:00Z"},
            {"id": 417, "conclusion": "cancelled", "completed_at": "2026-11-17T11:30:00Z"},
            {"id": 416, "conclusion": "skipped", "completed_at": "2026-11-17T11:00:00Z"},
            {"id": 415, "status": "in_progress", "completed_at": None},
            {"id": 414, "conclusion": "failure", "completed_at": "2026-11-17T10:00:00Z"},
        ],
        master_health={414: {"episode": episode}},
    )

    summary = _external_summary(forge=forge, run_id=418)

    assert summary["episode"] == episode
    assert forge.reads == [("runs", None), ("master-health", 414)]


def test_rerun_keeps_its_earlier_master_health_episode() -> None:
    """A re-run consults only its own earlier published master-health record."""
    episode = {"earliest_run_id": 400, "started_at": "2026-11-17T09:00:00Z"}
    forge = _EpisodeForge(
        runs=[
            {
                "id": 418,
                "conclusion": "failure",
                "completed_at": "2026-11-17T12:00:00Z",
                "run_attempt": 2,
            },
            {"id": 417, "conclusion": "success", "completed_at": "2026-11-17T11:00:00Z"},
        ],
        master_health={418: {"episode": episode}},
    )

    summary = _external_summary(forge=forge, run_id=418)

    assert summary["episode"] == episode
    assert forge.reads == [("runs", None), ("master-health", 418)]


def test_no_prior_history_leaves_the_episode_unknown() -> None:
    """A newest run with no prior history has no carried or fresh episode."""
    forge = _EpisodeForge(
        runs=[{"id": 418, "conclusion": "failure", "completed_at": "2026-11-17T12:00:00Z"}]
    )

    summary = _external_summary(forge=forge, run_id=418)

    assert summary["episode"] is None
    assert forge.reads == [("runs", None)]


def test_malformed_prior_run_cannot_start_an_episode() -> None:
    """An incomplete oldest run produces no malformed episode payload."""
    forge = _EpisodeForge(
        runs=[
            {"id": 418, "conclusion": "failure", "completed_at": "2026-11-17T12:00:00Z"},
            {"id": "417", "conclusion": "failure", "completed_at": "2026-11-17T11:00:00Z"},
            {"id": 416, "conclusion": "success", "completed_at": "2026-11-17T10:00:00Z"},
        ]
    )

    summary = _external_summary(forge=forge, run_id=418)

    assert summary["episode"] is None
    assert forge.reads == [("runs", None)]


def test_malformed_recent_runs_response_leaves_the_episode_unknown() -> None:
    """Only a JSON sequence can supply master-push history to the clock."""
    forge = _MalformedRunsForge()

    summary = _external_summary(forge=forge, run_id=418)

    assert summary["episode"] is None
    assert len(forge.check_runs) == 1
