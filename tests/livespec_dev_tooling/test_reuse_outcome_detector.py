"""The mandatory coverage-reuse detector reports non-reuse outcomes."""

from __future__ import annotations

import importlib
from pathlib import Path

__all__: list[str] = []


_MODULE_PATH = (
    Path(__file__).resolve().parents[2] / "livespec_dev_tooling" / "reuse_outcome_detector.py"
)


def test_non_reused_coverage_outcome_names_repository_run_job_and_outcome() -> None:
    """A mandatory consumer fallback is a maintainer-visible notification."""
    assert _MODULE_PATH.is_file()
    detector = importlib.import_module("livespec_dev_tooling.reuse_outcome_detector")

    notices = detector.evaluate(
        outcomes=[
            {
                "repository": "thewoolleyman/livespec-dev-tooling",
                "run_id": 42,
                "job_id": 84,
                "outcome": "missing_receipt",
                "duration_seconds": 721,
            }
        ],
        jobs=[],
        now="2026-11-12T21:00:00Z",
        last_success="2026-11-12T20:55:00Z",
        interval_seconds=900,
    )

    assert [notice.message for notice in notices] == [
        "coverage reuse fallback: repository=thewoolleyman/livespec-dev-tooling "
        "run=42 job=84 outcome=missing_receipt"
    ]


def test_missing_mandatory_consumer_outcome_names_the_repository_and_job() -> None:
    """A completed master consumer without evidence is visible to the maintainer."""
    detector = importlib.import_module("livespec_dev_tooling.reuse_outcome_detector")

    notices = detector.evaluate(
        outcomes=[],
        jobs=[
            {
                "repository": "thewoolleyman/livespec-dev-tooling",
                "run_id": 42,
                "job_id": 84,
                "name": "check-coverage",
                "mandatory_coverage_consumer": True,
                "branch": "master",
                "completed_at": "2026-11-12T20:55:00Z",
            }
        ],
        now="2026-11-12T21:00:00Z",
        last_success="2026-11-12T20:55:00Z",
        interval_seconds=900,
    )

    assert [notice.message for notice in notices] == [
        "coverage reuse outcome missing: repository=thewoolleyman/livespec-dev-tooling " "job=84"
    ]


def test_master_consumer_timestamp_without_a_timezone_is_accepted() -> None:
    """GitHub evidence without a UTC suffix still identifies a recent missing record."""
    detector = importlib.import_module("livespec_dev_tooling.reuse_outcome_detector")

    notices = detector.evaluate(
        outcomes=[],
        jobs=[
            {
                "repository": "thewoolleyman/livespec-dev-tooling",
                "job_id": 84,
                "mandatory_coverage_consumer": True,
                "branch": "master",
                "completed_at": "2026-11-12T20:55:00",
            }
        ],
        now="2026-11-12T21:00:00Z",
        last_success="2026-11-12T20:55:00Z",
        interval_seconds=900,
    )

    assert [notice.message for notice in notices] == [
        "coverage reuse outcome missing: repository=thewoolleyman/livespec-dev-tooling " "job=84"
    ]


def test_malformed_detector_clock_leaves_the_recorded_fallback_visible() -> None:
    """Bad heartbeat input cannot hide a real fallback record."""
    detector = importlib.import_module("livespec_dev_tooling.reuse_outcome_detector")

    notices = detector.evaluate(
        outcomes=[
            {
                "repository": "thewoolleyman/livespec-dev-tooling",
                "run_id": 42,
                "job_id": 84,
                "outcome": "tree_mismatch",
            }
        ],
        jobs=[],
        now="not-a-timestamp",
        last_success="2026-11-12T20:55:00Z",
        interval_seconds=900,
    )

    assert [notice.message for notice in notices] == [
        "coverage reuse fallback: repository=thewoolleyman/livespec-dev-tooling "
        "run=42 job=84 outcome=tree_mismatch"
    ]


def test_duration_regression_names_job_and_compares_24_hour_p90_to_7_day_baseline() -> None:
    """A material regression is visible even when other jobs remain normal."""
    detector = importlib.import_module("livespec_dev_tooling.reuse_outcome_detector")

    notices = detector.evaluate(
        outcomes=[],
        jobs=[
            {
                "repository": "thewoolleyman/livespec-dev-tooling",
                "job_id": 84,
                "name": "check-coverage",
                "runner_label": "k3s",
                "completed_at": "2026-11-12T20:55:00Z",
                "duration_seconds": 1_260,
            },
            {
                "repository": "thewoolleyman/livespec-dev-tooling",
                "job_id": 85,
                "name": "check-coverage",
                "runner_label": "k3s",
                "completed_at": "2026-11-08T20:55:00Z",
                "duration_seconds": 300,
            },
            {
                "repository": "thewoolleyman/livespec-dev-tooling",
                "job_id": 86,
                "name": "check-lint",
                "runner_label": "k3s",
                "completed_at": "2026-11-12T20:55:00Z",
                "duration_seconds": 600,
            },
            {
                "repository": "thewoolleyman/livespec-dev-tooling",
                "job_id": 87,
                "name": "check-lint",
                "runner_label": "k3s",
                "completed_at": "2026-11-08T20:55:00Z",
                "duration_seconds": 300,
            },
        ],
        now="2026-11-12T21:00:00Z",
        last_success="2026-11-12T20:55:00Z",
        interval_seconds=900,
    )

    assert [notice.message for notice in notices] == [
        "CI duration regression: job=check-coverage runner=k3s "
        "p90_24h_seconds=1260 baseline_7d_seconds=300"
    ]


def test_stale_detector_heartbeat_names_the_detector() -> None:
    """A missed detector schedule cannot remain silent for longer than two intervals."""
    detector = importlib.import_module("livespec_dev_tooling.reuse_outcome_detector")

    notices = detector.evaluate(
        outcomes=[],
        jobs=[],
        now="2026-11-12T21:00:00Z",
        last_success="2026-11-12T20:29:00Z",
        interval_seconds=900,
    )

    assert [notice.message for notice in notices] == [
        "coverage reuse outcome detector stale: last_success=2026-11-12T20:29:00Z "
        "interval_seconds=900"
    ]
