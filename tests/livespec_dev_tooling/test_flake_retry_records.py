"""Tests for compact flake-retry record values."""

from __future__ import annotations

import json

from livespec_dev_tooling.flake_retry_records import (
    RetryResult,
    failure_from,
    records_json,
    summary,
)


def test_record_values_preserve_bounded_failure_text_in_json_and_summary() -> None:
    """Each failed attempt remains available in both retry output forms."""
    failure = failure_from(longrepr="AssertionError: first attempt\nfull traceback")
    result = RetryResult(
        nodeid="tests/test_example.py::test_flaky",
        attempts=2,
        outcome="passed",
        failures=(failure,),
    )

    assert json.loads(records_json(results=(result,))) == {
        "attempts": 2,
        "failures": [{"cut": False, "text": "AssertionError: first attempt\nfull traceback"}],
        "nodeid": "tests/test_example.py::test_flaky",
        "outcome": "passed",
    }
    assert summary(results=(result,)) == (
        "FLAKE-RETRIED\n"
        "tests/test_example.py::test_flaky: 2 attempts, passed\n"
        "  AssertionError: first attempt"
    )


def test_failure_from_cuts_oversized_text() -> None:
    """Artifact-bound failure text keeps an explicit truncation signal."""
    failure = failure_from(longrepr="x" * 4001)

    assert failure.cut is True
    assert failure.text == "x" * 4000
