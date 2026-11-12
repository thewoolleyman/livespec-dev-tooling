"""Consumer scenarios for mandatory coverage-reuse monitoring."""

from __future__ import annotations

import importlib
from datetime import datetime, timedelta, timezone
from types import ModuleType

import pytest

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_NOW = datetime(2026, 11, 12, 12, 0, tzinfo=timezone.utc)
_REPOSITORY = "thewoolleyman/livespec-dev-tooling"


def _detector() -> ModuleType:
    """Load the consumer-facing detector only inside each scenario."""
    return importlib.import_module("livespec_dev_tooling.reuse_outcome_detector")


def _job(
    *,
    detector: ModuleType,
    completed_at: datetime,
    duration_seconds: int,
    runner_label: str = "k3s",
) -> object:
    """Create one mandatory master coverage consumer job."""
    return detector.CiJob(
        repository=_REPOSITORY,
        run_id="42",
        job_id="coverage-job",
        name="check-coverage",
        runner_label=runner_label,
        duration_seconds=duration_seconds,
        completed_at=completed_at,
        is_master=True,
        is_mandatory_coverage_consumer=True,
    )


def test_a_master_consumer_without_an_outcome_names_its_repository_and_job() -> None:
    """A missing outcome is distinct from a recorded successful reuse."""
    detector = _detector()
    assert hasattr(detector, "detect_notifications")
    notifications = detector.detect_notifications(
        now=_NOW,
        outcomes=(),
        jobs=(
            _job(
                detector=detector,
                completed_at=_NOW - timedelta(minutes=1),
                duration_seconds=60,
            ),
        ),
        detector_last_success=_NOW,
        schedule_interval=timedelta(minutes=10),
    )

    assert [item.message for item in notifications] == [
        "coverage reuse evidence missing repository=thewoolleyman/livespec-dev-tooling "
        "job=coverage-job"
    ]


def test_a_same_runner_p90_step_change_notifies_but_a_lane_move_does_not() -> None:
    """Durations compare only the same job name and runner label."""
    detector = _detector()
    assert hasattr(detector, "detect_notifications")
    current = tuple(
        _job(detector=detector, completed_at=_NOW - timedelta(hours=index), duration_seconds=720)
        for index in range(1, 5)
    )
    baseline = tuple(
        _job(
            detector=detector,
            completed_at=_NOW - timedelta(days=2, hours=index),
            duration_seconds=120,
        )
        for index in range(4)
    )
    hosted = tuple(
        _job(
            detector=detector,
            completed_at=_NOW - timedelta(hours=index),
            duration_seconds=1200,
            runner_label="hosted",
        )
        for index in range(1, 5)
    )
    notifications = detector.detect_notifications(
        now=_NOW,
        outcomes=(),
        jobs=(*current, *baseline, *hosted),
        detector_last_success=_NOW,
        schedule_interval=timedelta(minutes=10),
    )

    assert [item.message for item in notifications if item.kind == "duration_step"] == [
        "CI duration step job=check-coverage runner=k3s current_p90_seconds=720 "
        "baseline_p90_seconds=120"
    ]


def test_a_stale_detector_names_itself() -> None:
    """The independent heartbeat reports a detector older than two intervals."""
    detector = _detector()
    assert hasattr(detector, "detect_notifications")
    notifications = detector.detect_notifications(
        now=_NOW,
        outcomes=(),
        jobs=(),
        detector_last_success=_NOW - timedelta(minutes=21),
        schedule_interval=timedelta(minutes=10),
    )

    assert [item.message for item in notifications] == ["coverage reuse detector stale"]
