"""Tests for the delegated gate Job-status decoder."""

from __future__ import annotations

import json

from returns.pipeline import is_successful
from returns.result import Failure

from livespec_dev_tooling.gate_remote_job_status import admitted, terminal_condition

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


def test_admission_accepts_unsuspension_or_the_kueue_condition_or_a_start_time() -> None:
    """Kueue can expose admission through each supported Job status signal."""
    payloads = (
        {"spec": {"suspend": False}, "status": {}},
        {
            "spec": {"suspend": True},
            "status": {"conditions": [{"type": "Admitted", "status": "True"}]},
        },
        {"spec": {"suspend": True}, "status": {"startTime": "2026-10-22T10:00:00Z"}},
    )

    for payload in payloads:
        outcome = admitted(
            argv=("kubectl",), payload=json.dumps(payload), step="await-gate-terminal"
        )

        assert is_successful(outcome)
        assert outcome.unwrap()


def test_admission_refuses_an_unreadable_job_status() -> None:
    """A malformed status cannot be guessed to be admitted."""
    outcome = admitted(argv=("kubectl",), payload="not json", step="await-gate-terminal")

    assert isinstance(outcome, Failure)
    assert "unreadable job status" in outcome.failure().detail
