"""Consumer contract for the scheduled coverage-reuse detector."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

import pytest

from livespec_dev_tooling import reuse_outcome_detector
from livespec_dev_tooling.budgeted_gh import GhRead

__all__: list[str] = []


_REPOSITORY = "thewoolleyman/livespec-dev-tooling"
_SINCE = "2026-11-12T18:00:00Z"
_RUN_FLOOR = "2026-11-12T12:00:00Z"


def _read_responses(*, responses: list[GhRead]) -> Callable[..., GhRead]:
    """Build one budgeted-client seam that returns recorded answers in order."""
    answers = iter(responses)

    def read(*, args: list[str]) -> GhRead:
        _ = args
        return next(answers)

    return read


def test_a_recorded_fallback_reaches_the_notification_output_within_the_schedule_bound(
    *, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """The runnable detector reads job metadata and emits the required notification."""
    responses = iter(
        [
            GhRead(returncode=0, stdout='[{"databaseId":42}]', stderr=""),
            GhRead(
                returncode=0,
                stdout=(
                    '{"jobs":[{"id":84,"name":"check-coverage",'
                    '"completed_at":"2026-11-12T20:50:00Z"}]}'
                ),
                stderr="",
            ),
            GhRead(
                returncode=0,
                stdout=(
                    "LIVESPEC_COVERAGE_REUSE_OUTCOME "
                    '{"repository":"thewoolleyman/livespec-dev-tooling",'
                    '"run_id":"42","job_id":"check-coverage",'
                    '"duration_ms":721000,"outcome":"missing_receipt"}\n'
                ),
                stderr="",
            ),
        ]
    )

    def _read(*, args: list[str]) -> GhRead:
        _ = args
        return next(responses)

    status = reuse_outcome_detector.main(
        argv=["--repo", _REPOSITORY, "--state-file", str(tmp_path / "detector.json")],
        read=_read,
        now=lambda: datetime(2026, 11, 12, 21, 0, tzinfo=timezone.utc),
    )

    captured = capsys.readouterr()
    assert status == 0
    assert json.loads(captured.out) == {
        "notification": (
            "coverage reuse fallback: repository=thewoolleyman/livespec-dev-tooling "
            "run=42 job=84 outcome=missing_receipt"
        )
    }
    assert json.loads((tmp_path / "detector.json").read_text(encoding="utf-8")) == {
        "last_success": "2026-11-12T21:00:00Z"
    }


@pytest.mark.parametrize(
    "responses",
    [
        [GhRead(returncode=1, stdout="", stderr="runs unavailable")],
        [
            GhRead(returncode=0, stdout='[{"databaseId":42}]', stderr=""),
            GhRead(returncode=1, stdout="", stderr="jobs unavailable"),
        ],
        [
            GhRead(returncode=0, stdout='[{"databaseId":42}]', stderr=""),
            GhRead(
                returncode=0,
                stdout=(
                    '{"jobs":[{"id":84,"name":"check-coverage",'
                    '"completed_at":"2026-11-12T18:30:00Z"}]}'
                ),
                stderr="",
            ),
            GhRead(returncode=1, stdout="", stderr="logs unavailable"),
        ],
        [
            GhRead(returncode=0, stdout='[{"databaseId":42}]', stderr=""),
            GhRead(
                returncode=0,
                stdout='{"jobs":[{"id":84,"name":"check-coverage","completed_at":"done"}]}',
                stderr="",
            ),
            GhRead(returncode=0, stdout="not an outcome\n", stderr=""),
        ],
    ],
)
def test_an_unreadable_github_document_stops_the_detector(*, responses: list[GhRead]) -> None:
    """A budgeted read that did not answer cannot become a silent clean detector pass."""
    assert (
        reuse_outcome_detector.gather(
            repository=_REPOSITORY,
            since=_SINCE,
            read=_read_responses(responses=responses),
        )
        is None
    )


def test_non_consumer_incomplete_and_invalid_records_are_not_notifications() -> None:
    """Only completed mandatory consumers with their valid record yield a detector input."""
    outcomes = reuse_outcome_detector.gather(
        repository=_REPOSITORY,
        since=_SINCE,
        read=_read_responses(
            responses=[
                GhRead(returncode=0, stdout='[{"databaseId":42}]', stderr=""),
                GhRead(
                    returncode=0,
                    stdout=(
                        '{"jobs":['
                        '{"id":81,"name":"check-python","completed_at":"2026-11-12T18:30:00Z"},'
                        '{"id":82,"name":"check-coverage","completed_at":null},'
                        '{"id":83,"name":"check-coverage","completed_at":"2026-11-12T18:30:00Z"},'
                        '{"id":84,"name":"check-coverage","completed_at":"2026-11-12T18:31:00Z"}'
                        "]}"
                    ),
                    stderr="",
                ),
                GhRead(returncode=0, stdout="not an outcome\n", stderr=""),
                GhRead(
                    returncode=0,
                    stdout=(
                        "LIVESPEC_COVERAGE_REUSE_OUTCOME "
                        '{"repository":"thewoolleyman/livespec-dev-tooling",'
                        '"run_id":"42","job_id":"check-coverage",'
                        '"duration_ms":1,"outcome":"reused"}\n'
                    ),
                    stderr="",
                ),
            ]
        ),
    )

    assert outcomes is not None
    assert (
        reuse_outcome_detector.evaluate(
            outcomes=outcomes,
            jobs=[],
            now="now",
            last_success="then",
            interval_seconds=900,
        )
        == []
    )


def test_invalid_schedule_or_failed_gather_does_not_mark_the_detector_successful(
    *, tmp_path: Path
) -> None:
    """The host cannot claim completion when its cadence or reads are invalid."""
    state = tmp_path / "detector.json"

    assert (
        reuse_outcome_detector.main(
            argv=["--repo", _REPOSITORY, "--interval-seconds", "1801"],
            read=_read_responses(responses=[]),
        )
        == 2
    )
    assert (
        reuse_outcome_detector.main(
            argv=["--repo", _REPOSITORY, "--state-file", str(state)],
            read=_read_responses(responses=[GhRead(returncode=1, stdout="", stderr="unavailable")]),
        )
        == 1
    )
    assert not state.exists()


def test_run_discovery_is_windowed_and_a_full_listing_is_never_read_as_complete() -> None:
    """Discovery narrows to the recent window and refuses a listing that may be truncated."""
    seen: list[list[str]] = []

    def read(*, args: list[str]) -> GhRead:
        seen.append(args)
        runs = [{"databaseId": run_id} for run_id in range(1_000)]
        return GhRead(returncode=0, stdout=json.dumps(runs), stderr="")

    assert reuse_outcome_detector.gather(repository=_REPOSITORY, since=_SINCE, read=read) is None
    assert f">={_RUN_FLOOR}" in seen[0]
    assert len(seen) == 1


def test_a_long_running_run_is_inspected_and_only_jobs_completed_in_the_window_are_read() -> None:
    """A run created before the window is listed; its job is graded on its own completion."""
    seen: list[list[str]] = []
    answers = iter(
        [
            GhRead(returncode=0, stdout='[{"databaseId":42}]', stderr=""),
            GhRead(
                returncode=0,
                stdout=(
                    '{"jobs":['
                    '{"id":83,"name":"check-coverage","completed_at":"2026-11-12T17:59:59Z"},'
                    '{"id":84,"name":"check-coverage","completed_at":"2026-11-12T18:00:00Z"}'
                    "]}"
                ),
                stderr="",
            ),
            GhRead(
                returncode=0,
                stdout=(
                    "LIVESPEC_COVERAGE_REUSE_OUTCOME "
                    '{"repository":"thewoolleyman/livespec-dev-tooling",'
                    '"run_id":"42","job_id":"check-coverage",'
                    '"duration_ms":721000,"outcome":"missing_receipt"}\n'
                ),
                stderr="",
            ),
        ]
    )

    def read(*, args: list[str]) -> GhRead:
        seen.append(args)
        return next(answers, GhRead(returncode=1, stdout="", stderr="unexpected read"))

    outcomes = reuse_outcome_detector.gather(
        repository=_REPOSITORY,
        since=_SINCE,
        read=read,
    )

    assert outcomes is not None
    assert [outcome["job_id"] for outcome in outcomes] == [84]
    assert f">={_RUN_FLOOR}" in seen[0]
    assert all("jobs/83/" not in " ".join(args) for args in seen)
