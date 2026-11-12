"""Tests for compact flake-retry record values."""

from __future__ import annotations

import json
from pathlib import Path

_RECORDS_MODULE = (
    Path(__file__).resolve().parents[2] / "livespec_dev_tooling" / "flake_retry_records.py"
)


def test_record_values_preserve_bounded_failure_text_in_json_and_summary() -> None:
    """Each failed attempt remains available in both retry output forms."""
    assert _RECORDS_MODULE.is_file()
    from livespec_dev_tooling.flake_retry_records import (
        RetryResult,
        failure_from,
        records_json,
        summary,
    )

    failure = failure_from(longrepr="AssertionError: first attempt\nfull traceback")
    cut_failure = failure_from(longrepr="x" * 4001)
    result = RetryResult(
        nodeid="tests/test_example.py::test_flaky",
        attempts=2,
        outcome="passed",
        failures=(failure, cut_failure),
    )

    assert json.loads(records_json(results=(result,))) == {
        "attempts": 2,
        "failures": [
            {"cut": False, "text": "AssertionError: first attempt\nfull traceback"},
            {"cut": True, "text": "x" * 4000},
        ],
        "nodeid": "tests/test_example.py::test_flaky",
        "outcome": "passed",
    }
    assert summary(results=(result,)) == (
        "FLAKE-RETRIED\n"
        "tests/test_example.py::test_flaky: 2 attempts, passed\n"
        "  AssertionError: first attempt\n"
        "  " + "x" * 4000
    )
