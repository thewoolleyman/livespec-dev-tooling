"""Plan the CI infrastructure re-runs of one completed CI run.

The gathering lives in livespec-dev-tooling's
`.github/workflows/reusable-ci-infra-rerun.yml`. It records the jobs of every
attempt of the run, fetches the logs of the current attempt's failed jobs this
module names, and performs the re-runs this module plans. The decision itself is
here and touches no network, so a recorded run always replays to the same plan.

A failed job is re-run only when its FIRST failed step is the step a classifier
covers AND its log carries one of that classifier's signatures. Every other
failure is LEFT, so its failure stays the run's verdict. A test or build failure
can never match: no classifier covers a step that runs repository code.

Each classifier carries its own waits, one per automatic attempt, so the length
of its waits is its attempt cap and the waits grow. A job's attempt number counts
the distinct job ids of the same name that failed at the classifier's step across
the run's attempts, so a job GitHub copies unchanged into a later attempt (a
failed job that attempt did not re-run) is not counted twice.

THE SEAM. A second cause is one more `CLASSIFIERS` entry. The workflow asks this
module which jobs need logs and what to re-run, so neither the workflow nor any
caller changes when a classifier is added (livespec-dev-tooling-khlrw3 adds the
`Initialize containers` registry-error classifier this way).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, cast

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

from livespec_dev_tooling._ci_infra_rerun_plan import (  # noqa: E402  — vendor-path-aware.
    CLASSIFIERS,
    FAILURE,
    JobClassifier,
    LeftJob,
    PlannedRerun,
    RecordedJob,
    RerunPlan,
    Signature,
    jobs_needing_logs,
    plan_payload,
    plan_reruns,
    summary_lines,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__: list[str] = [
    "CLASSIFIERS",
    "JobClassifier",
    "LeftJob",
    "PlannedRerun",
    "RecordedJob",
    "RerunPlan",
    "Signature",
    "jobs_needing_logs",
    "main",
    "parse_jobs",
    "plan_payload",
    "plan_reruns",
    "summary_lines",
]


def _failure_details(*, steps: object) -> tuple[str | None, bool] | None:
    """Return the first failed step and whether a following step had started."""
    if not isinstance(steps, list):
        return None
    first_failed_step: str | None = None
    later_step_started = False
    for step in cast("list[object]", steps):
        if not isinstance(step, dict):
            return None
        record = cast("dict[str, object]", step)
        name = record.get("name")
        if not isinstance(name, str):
            return None
        conclusion = record.get("conclusion")
        if first_failed_step is None and conclusion == FAILURE:
            first_failed_step = name
        elif first_failed_step is not None and conclusion not in {None, "skipped"}:
            later_step_started = True
    return first_failed_step, later_step_started


def _parse_job(*, raw: object) -> RecordedJob | None:
    if not isinstance(raw, dict):
        return None
    record = cast("dict[str, object]", raw)
    attempt = record.get("attempt")
    job_id = record.get("id")
    name = record.get("name")
    conclusion = record.get("conclusion")
    failure_details = _failure_details(steps=record.get("steps"))
    if (
        not isinstance(attempt, int)
        or not isinstance(job_id, int)
        or not isinstance(name, str)
        or failure_details is None
    ):
        return None
    first_failed_step, later_step_started = failure_details
    return RecordedJob(
        attempt=attempt,
        job_id=job_id,
        name=name,
        conclusion=conclusion if isinstance(conclusion, str) else "",
        first_failed_step=first_failed_step,
        later_step_started=later_step_started,
    )


def parse_jobs(*, payload: object) -> tuple[RecordedJob, ...] | None:
    """The recorded jobs, or None when any record is malformed (fail closed)."""
    if not isinstance(payload, list):
        return None
    parsed = [_parse_job(raw=raw) for raw in cast("list[object]", payload)]
    if any(job is None for job in parsed):
        return None
    return tuple(cast("list[RecordedJob]", parsed))


def _read_jobs(*, path: Path) -> tuple[RecordedJob, ...] | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        payload: object = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parse_jobs(payload=payload)


def _read_logs(*, logs_dir: Path, job_ids: Sequence[int]) -> dict[int, str]:
    logs: dict[int, str] = {}
    for job_id in job_ids:
        path = logs_dir / f"{job_id}.log"
        if path.is_file():
            logs[job_id] = path.read_text(encoding="utf-8", errors="replace")
    return logs


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m livespec_dev_tooling.ci_infra_rerun",
        description="Plan the CI infrastructure re-runs of one completed CI run.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    log_jobs = commands.add_parser("log-jobs", help="print the job ids whose logs to fetch")
    _ = log_jobs.add_argument("--jobs", type=Path, required=True)
    _ = log_jobs.add_argument("--run-attempt", type=int, required=True)
    plan = commands.add_parser("plan", help="write the re-run plan and its summary")
    _ = plan.add_argument("--jobs", type=Path, required=True)
    _ = plan.add_argument("--run-attempt", type=int, required=True)
    _ = plan.add_argument("--logs-dir", type=Path, required=True)
    _ = plan.add_argument("--plan-out", type=Path, required=True)
    _ = plan.add_argument("--summary-out", type=Path, required=True)
    _ = plan.add_argument("--repository", required=True)
    _ = plan.add_argument("--run-id", required=True)
    return parser


def main(*, argv: list[str] | None = None) -> int:
    """Run one subcommand; 1 and no output file when the recorded jobs are malformed."""
    log = structlog.get_logger("ci_infra_rerun")
    args = _build_parser().parse_args(argv)
    jobs_path = cast("Path", args.jobs)
    run_attempt = cast("int", args.run_attempt)
    jobs = _read_jobs(path=jobs_path)
    if jobs is None:
        log.error("recorded jobs unreadable or malformed; planned nothing", jobs=str(jobs_path))
        return 1
    needing = jobs_needing_logs(jobs=jobs, run_attempt=run_attempt)
    if args.command == "log-jobs":
        print("\n".join(str(job_id) for job_id in needing))  # noqa: T201 — the workflow reads stdout.
        return 0
    logs = _read_logs(logs_dir=cast("Path", args.logs_dir), job_ids=needing)
    plan = plan_reruns(jobs=jobs, run_attempt=run_attempt, logs=logs)
    _ = cast("Path", args.plan_out).write_text(
        json.dumps(plan_payload(plan=plan)) + "\n", encoding="utf-8"
    )
    lines = summary_lines(
        plan=plan, repository=cast("str", args.repository), run_id=cast("str", args.run_id)
    )
    _ = cast("Path", args.summary_out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    log.info("planned CI infrastructure re-runs", reruns=len(plan.reruns), left=len(plan.left))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
