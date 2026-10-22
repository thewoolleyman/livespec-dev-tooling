"""Tests for the delegated gate Job-status decoder."""

from __future__ import annotations

import json

from returns.pipeline import is_successful

from livespec_dev_tooling.gate_remote_job_status import terminal_condition

__all__: list[str] = []


def test_a_terminal_job_status_keeps_the_jobs_reported_clock_readings() -> None:
    """The decoder preserves the status reply that supplied a terminal condition."""
    payload = json.dumps(
        {
            "status": {
                "startTime": "2026-10-22T10:00:00Z",
                "completionTime": "2026-10-22T10:01:00Z",
                "conditions": [{"type": "Complete", "status": "True"}],
            }
        }
    )

    decoded = terminal_condition(argv=("kubectl",), payload=payload, step="await-gate-terminal")

    assert is_successful(decoded)
    terminal = decoded.unwrap()
    assert terminal is not None
    assert terminal.status["startTime"] == "2026-10-22T10:00:00Z"
    assert terminal.status["completionTime"] == "2026-10-22T10:01:00Z"
