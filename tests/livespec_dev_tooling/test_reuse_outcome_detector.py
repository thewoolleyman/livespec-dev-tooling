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
