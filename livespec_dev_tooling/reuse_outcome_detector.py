"""Report mandatory coverage consumers whose recorded outcome was not reused.

The host invokes this module on a schedule with its fleet repository roster.
It reads completed runs, job metadata, and the consumer job log through the
budgeted GitHub client, then emits JSON notification records for a later
delivery adapter.  It deliberately owns no delivery channel or receipt.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Final, cast

from livespec_dev_tooling.budgeted_gh import GhRead, gh_read
from livespec_dev_tooling.ci_coverage_reuse import (
    COVERAGE_CONSUMER_JOB_ID,
    coverage_reuse_outcome,
)

__all__: list[str] = ["Notice", "evaluate", "gather", "main"]

_DEFAULT_INTERVAL_SECONDS: Final = 900
_MAX_INTERVAL_SECONDS: Final = 1_800
_DEFAULT_STATE_FILE: Final = Path("/var/lib/livespec/coverage-reuse-detector.json")
_LOOKBACK: Final = timedelta(hours=3)
_RUN_LIMIT: Final = 1_000
_Read = Callable[..., GhRead]


@dataclass(frozen=True, kw_only=True)
class Notice:
    """One notification that the host-side delivery adapter must send."""

    message: str


def evaluate(
    *,
    outcomes: Sequence[dict[str, object]],
    jobs: Sequence[dict[str, object]],
    now: str,
    last_success: str,
    interval_seconds: int,
) -> list[Notice]:
    """Render every recorded mandatory-consumer fallback as a notification."""
    _ = (jobs, now, last_success, interval_seconds)
    return [
        Notice(
            message=(
                "coverage reuse fallback: "
                f"repository={outcome['repository']} run={outcome['run_id']} "
                f"job={outcome['job_id']} outcome={outcome['outcome']}"
            )
        )
        for outcome in outcomes
        if outcome["outcome"] != "reused"
    ]


def gather(*, repository: str, since: str, read: _Read = gh_read) -> list[dict[str, object]] | None:
    """Gather completed mandatory-consumer outcomes for one fleet repository.

    Discovery is windowed to runs created at or after `since` rather than to
    the latest N runs, so unrelated later runs cannot push a consumer out of
    view.  A listing that fills the run limit may be truncated, so it is read
    as unanswered rather than as complete.
    """
    runs = read(
        args=[
            "run",
            "list",
            "--repo",
            repository,
            "--status",
            "completed",
            "--created",
            f">={since}",
            "--limit",
            str(_RUN_LIMIT),
            "--json",
            "databaseId",
        ]
    )
    if runs.returncode != 0:
        return None
    listed = cast("list[dict[str, object]]", json.loads(runs.stdout))
    if len(listed) >= _RUN_LIMIT:
        return None
    recorded: list[dict[str, object]] = []
    for run in listed:
        run_id = int(cast("int | str", run["databaseId"]))
        jobs = read(
            args=[
                "api",
                f"repos/{repository}/actions/runs/{run_id}/jobs?per_page=100",
                "--paginate",
            ]
        )
        if jobs.returncode != 0:
            return None
        for page in _pages(text=jobs.stdout):
            for job in cast("list[dict[str, object]]", page.get("jobs", [])):
                if job.get("name") != COVERAGE_CONSUMER_JOB_ID or not job.get("completed_at"):
                    continue
                job_id = int(cast("int | str", job["id"]))
                log = read(args=["api", f"repos/{repository}/actions/jobs/{job_id}/logs"])
                if log.returncode != 0:
                    return None
                outcome = coverage_reuse_outcome(
                    repo=repository,
                    run_id=run_id,
                    job_name=job.get("name"),
                    log=log.stdout,
                )
                if outcome is not None:
                    recorded.append({**outcome, "job_id": job_id})
    return recorded


def main(
    *,
    argv: Sequence[str] | None = None,
    read: _Read = gh_read,
    now: Callable[[], datetime] = lambda: datetime.now(tz=timezone.utc),
) -> int:
    """Emit fallback notification records and save this detector's completion state."""
    parser = argparse.ArgumentParser(description=__doc__)
    _ = parser.add_argument("--repo", action="append", required=True)
    _ = parser.add_argument("--state-file", type=Path, default=_DEFAULT_STATE_FILE)
    _ = parser.add_argument("--interval-seconds", type=int, default=_DEFAULT_INTERVAL_SECONDS)
    arguments = parser.parse_args(argv)
    if arguments.interval_seconds <= 0 or arguments.interval_seconds > _MAX_INTERVAL_SECONDS:
        return 2
    started = now().astimezone(timezone.utc)
    since = (started - _LOOKBACK).isoformat().replace("+00:00", "Z")
    outcomes: list[dict[str, object]] = []
    for repository in cast("list[str]", arguments.repo):
        gathered = gather(repository=repository, since=since, read=read)
        if gathered is None:
            return 1
        outcomes.extend(gathered)
    completed_at = now().astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    notices = evaluate(
        outcomes=outcomes,
        jobs=[],
        now=completed_at,
        last_success="",
        interval_seconds=arguments.interval_seconds,
    )
    _write_state(path=cast("Path", arguments.state_file), completed_at=completed_at)
    for notice in notices:
        _ = sys.stdout.write(f"{json.dumps({'notification': notice.message})}\n")
    return 0


def _pages(*, text: str) -> list[dict[str, object]]:
    """Parse GitHub CLI's newline-delimited paginated API response."""
    return [cast("dict[str, object]", json.loads(page)) for page in text.splitlines() if page]


def _write_state(*, path: Path, completed_at: str) -> None:
    """Atomically persist the last fully successful detector run for stale detection."""
    _ = path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    _ = temporary.write_text(json.dumps({"last_success": completed_at}) + "\n", encoding="utf-8")
    _ = temporary.replace(path)


if __name__ == "__main__":
    raise SystemExit(main())
