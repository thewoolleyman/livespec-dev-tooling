"""The terminal block and the JSON record the flake-retry plugin leaves behind."""

from __future__ import annotations

from pathlib import Path

import pytest

from livespec_dev_tooling.flake_retry_announcement import (
    announce,
    retry_summary,
    write_retry_records,
)
from livespec_dev_tooling.flake_retry_records import RetryResult


class _Reporter:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def write_sep(self, sep: str, title: str) -> None:
        self.lines.append(f"{sep}{title}")

    def write_line(self, line: str) -> None:
        self.lines.append(line)


def _result() -> RetryResult:
    return RetryResult(nodeid="t.py::flaky", attempts=2, outcome="passed")


def test_a_session_with_nothing_to_report_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    reporter = _Reporter()

    announce(terminalreporter=reporter, root=tmp_path, results=[])  # type: ignore[arg-type]

    assert (reporter.lines, (tmp_path / "tmp").exists()) == ([], False)


def test_a_withheld_session_says_why_and_annotates_on_github(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    reporter = _Reporter()

    announce(
        terminalreporter=reporter,  # type: ignore[arg-type]
        root=tmp_path,
        results=[],
        withheld="a justfile change",
        withheld_by_nodeid={"t.py::failed": "an unparseable module"},
    )

    assert reporter.lines == [
        "=FLAKE-RETRY-WITHHELD",
        "no failing test is retried this session: a justfile change",
        "::warning::FLAKE-RETRY-WITHHELD a justfile change",
        "=FLAKE-RETRY-WITHHELD",
        "t.py::failed: an unparseable module",
        "::warning::FLAKE-RETRY-WITHHELD t.py::failed: an unparseable module",
    ]


def test_a_retried_test_is_recorded_summarised_and_annotated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    reporter = _Reporter()
    results = [_result()]

    announce(terminalreporter=reporter, root=tmp_path, results=results)  # type: ignore[arg-type]

    record = tmp_path / "tmp" / "flake-retries" / "retries.jsonl"
    assert (
        record.is_file(),
        reporter.lines[0],
        reporter.lines[1:-1] == retry_summary(results=results).splitlines()[1:],
        reporter.lines[-1],
    ) == (True, "=FLAKE-RETRIED", True, "::warning::FLAKE-RETRIED t.py::flaky")


def test_the_record_path_is_returned_and_holds_the_result(tmp_path: Path) -> None:
    written = write_retry_records(repo_root=tmp_path, results=[_result()])

    assert "t.py::flaky" in written.read_text(encoding="utf-8")
