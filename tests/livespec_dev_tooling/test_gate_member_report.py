"""Unit tests for `livespec_dev_tooling/_gate_member_report.py`."""

from __future__ import annotations

import pytest

from livespec_dev_tooling._gate_member_report import (
    CHECK_MEMBERS_PREFIX,
    GATE_MEMBERS_PREFIX,
    format_member_line,
    parse_member_report,
    passed_members,
)

__all__: list[str] = []


def test_a_formatted_gate_line_parses_back_in_order() -> None:
    """The one line names every member that ran, in order, with its verdict."""
    line = format_member_line(
        prefix=GATE_MEMBERS_PREFIX, ran=[("check-b", True), ("check-a", False)]
    )

    assert line == 'LIVESPEC_GATE_MEMBERS {"check-b": "passed", "check-a": "failed"}'
    assert parse_member_report(output=f"noise\n{line}\n") == (
        ("check-b", "passed"),
        ("check-a", "failed"),
    )


def test_the_last_gate_line_wins_and_a_carriage_return_is_ignored() -> None:
    """A member's captured output can carry an earlier line verbatim."""
    output = (
        'LIVESPEC_GATE_MEMBERS {"check-old": "passed"}\n'
        'LIVESPEC_GATE_MEMBERS {"check-new": "passed"}\r\n'
    )

    assert parse_member_report(output=output) == (("check-new", "passed"),)


def test_the_aggregates_own_line_is_not_the_jobs_report() -> None:
    """Only the gate Job's line counts, never the dispatcher line it re-prints."""
    line = format_member_line(prefix=CHECK_MEMBERS_PREFIX, ran=[("check-a", True)])

    assert parse_member_report(output=f"{line}\n") is None


@pytest.mark.parametrize(
    "payload",
    [
        "{not json",
        '["check-a"]',
        "{}",
        '{"check-a": "skipped"}',
        '{"": "passed"}',
    ],
    ids=["malformed", "not-an-object", "empty", "unknown-verdict", "unnamed-member"],
)
def test_a_report_that_cannot_be_read_whole_names_no_member(*, payload: str) -> None:
    """A partial or malformed report must not let a later reader skip a member."""
    assert parse_member_report(output=f"{GATE_MEMBERS_PREFIX}{payload}\n") is None


def test_passed_members_keeps_only_the_members_that_passed() -> None:
    """A member the Job ran and failed is not covered by its verdict."""
    report = (("check-a", "passed"), ("check-b", "failed"), ("check-c", "passed"))

    assert passed_members(report=report) == ("check-a", "check-c")
