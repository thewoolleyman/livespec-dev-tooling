"""The reuse-outcome detector reports costly coverage-consumer fallbacks."""

from __future__ import annotations

import importlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType

__all__: list[str] = []

_MODULE = "livespec_dev_tooling.reuse_outcome_detector"
_MODULE_PATH = (
    Path(__file__).resolve().parents[2] / "livespec_dev_tooling" / "reuse_outcome_detector.py"
)
_NOW = datetime(2026, 11, 12, 12, 0, tzinfo=timezone.utc)


def _detector() -> ModuleType:
    """Import the detector only after proving the shipped module exists."""
    assert _MODULE_PATH.is_file()
    return importlib.import_module(_MODULE)


def test_a_non_reused_mandatory_consumer_names_its_run_job_and_outcome() -> None:
    """A fallback is an immediate maintainer-facing event, not a green CI detail."""
    detector = _detector()
    assert hasattr(detector, "detect_notifications")
    notifications = detector.detect_notifications(
        now=_NOW,
        outcomes=(
            detector.ReuseOutcome(
                repository="thewoolleyman/livespec-dev-tooling",
                run_id="42",
                job_id="check-coverage",
                outcome="missing_receipt",
                duration_seconds=901,
                completed_at=_NOW - timedelta(minutes=10),
            ),
        ),
        jobs=(),
        detector_last_success=_NOW,
        schedule_interval=timedelta(minutes=10),
    )

    assert [notification.message for notification in notifications] == [
        "coverage reuse fallback repository=thewoolleyman/livespec-dev-tooling "
        "run=42 job=check-coverage outcome=missing_receipt"
    ]
