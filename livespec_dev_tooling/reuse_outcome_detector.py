"""Evaluate recorded mandatory coverage-reuse outcomes for maintainer notices."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

__all__: list[str] = ["Notice", "evaluate"]


@dataclass(frozen=True, kw_only=True)
class Notice:
    """One notification that the host-side delivery adapter must send."""

    message: str


def _timestamp(*, value: object) -> datetime | None:
    """Parse a GitHub timestamp without letting malformed input stop a scan."""
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _has_recorded_outcome(*, job: dict[str, object], outcomes: Sequence[dict[str, object]]) -> bool:
    """Return whether the job has its one structured reuse outcome."""
    job_id = job.get("job_id")
    repository = job.get("repository")
    return any(
        outcome.get("job_id") == job_id and outcome.get("repository") == repository
        for outcome in outcomes
    )


def _missing_outcome_notices(
    *, outcomes: Sequence[dict[str, object]], jobs: Sequence[dict[str, object]], now: datetime
) -> list[Notice]:
    """Report recent master consumers which supplied no outcome record."""
    oldest = now - timedelta(days=1)
    return [
        Notice(
            message=(
                "coverage reuse outcome missing: "
                f"repository={job['repository']} job={job['job_id']}"
            )
        )
        for job in jobs
        if job.get("mandatory_coverage_consumer") is True
        and job.get("branch") == "master"
        and (completed := _timestamp(value=job.get("completed_at"))) is not None
        and completed >= oldest
        and not _has_recorded_outcome(job=job, outcomes=outcomes)
    ]


def evaluate(
    *,
    outcomes: Sequence[dict[str, object]],
    jobs: Sequence[dict[str, object]],
    now: str,
    last_success: str,
    interval_seconds: int,
) -> list[Notice]:
    """Render every recorded mandatory-consumer fallback as a notification."""
    _ = (last_success, interval_seconds)
    fallback_notices = [
        Notice(
            message=(
                "coverage reuse fallback: "
                f"repository={outcome['repository']} run={outcome['run_id']} "
                f"job={outcome['job_id']} outcome={outcome['outcome']}"
            )
        )
        for outcome in outcomes
        if outcome.get("outcome") != "reused"
    ]
    current_time = _timestamp(value=now)
    if current_time is None:
        return fallback_notices
    missing_notices = _missing_outcome_notices(
        outcomes=outcomes,
        jobs=jobs,
        now=current_time,
    )
    return [*fallback_notices, *missing_notices]
