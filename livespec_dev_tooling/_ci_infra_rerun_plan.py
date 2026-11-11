"""The network-free re-run decision behind `ci_infra_rerun`.

`ci_infra_rerun` holds the command line and the reading of what the workflow
recorded; this module holds the classifiers and the plan. Its docstring explains
the rules, the attempt counting and the classifier seam.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

__all__: list[str] = [
    "CLASSIFIERS",
    "FAILURE",
    "JobClassifier",
    "LeftJob",
    "PlannedRerun",
    "RecordedJob",
    "RerunPlan",
    "Signature",
    "jobs_needing_logs",
    "plan_payload",
    "plan_reruns",
    "summary_lines",
]

FAILURE = "failure"


@dataclass(frozen=True, kw_only=True)
class Signature:
    """One named log signature: a job whose log has a matching line carries it."""

    name: str
    pattern: re.Pattern[str]


@dataclass(frozen=True, kw_only=True)
class JobClassifier:
    """A re-run cause: the step it covers, its signatures, and one wait per attempt."""

    cause: str
    step: str
    signatures: tuple[Signature, ...]
    waits_seconds: tuple[int, ...]


_ACTION_DOWNLOAD_429 = (
    r"Failed to download (?:action|archive) 'https://codeload\.github\.com/[^']*'"
    r".*429 \(Too Many Requests\)"
)

# The Set-up-job action-download rate limit (livespec-dev-tooling-cetyrq).
# The runner logs each refused download as a warning naming the codeload URL
# and the 429, then fails the step; `An action could not be found` is the
# runner's error when the archive host answers for a pinned action with
# nothing. Recorded 2026-11-03 13:33Z on livespec-orchestrator-beads-fabro job
# 125948122947 (run 41645065357), one of ten such failures in one burst.
_SETUP_JOB_ACTION_DOWNLOAD = JobClassifier(
    cause="set-up-job action download",
    step="Set up job",
    signatures=(
        Signature(
            name="action-download-429",
            pattern=re.compile(_ACTION_DOWNLOAD_429),
        ),
        Signature(
            name="action-not-found",
            pattern=re.compile(r"##\[error\]An action could not be found\b"),
        ),
    ),
    waits_seconds=(120, 300, 600),
)

CLASSIFIERS: tuple[JobClassifier, ...] = (_SETUP_JOB_ACTION_DOWNLOAD,)


@dataclass(frozen=True, kw_only=True)
class RecordedJob:
    """One job of one attempt of the run, as the workflow recorded it."""

    attempt: int
    job_id: int
    name: str
    conclusion: str
    first_failed_step: str | None


@dataclass(frozen=True, kw_only=True)
class PlannedRerun:
    """A job to re-run, with the attempt it starts and why it matched."""

    job_id: int
    name: str
    cause: str
    signature: str
    attempt: int
    max_attempts: int
    wait_seconds: int
    matched_line: str


@dataclass(frozen=True, kw_only=True)
class LeftJob:
    """A failed job this mechanism leaves, so its failure stays the verdict."""

    job_id: int
    name: str
    reason: str


@dataclass(frozen=True, kw_only=True)
class RerunPlan:
    """What to re-run and what to leave for one completed run."""

    reruns: tuple[PlannedRerun, ...]
    left: tuple[LeftJob, ...]

    @property
    def wait_seconds(self) -> int:
        """The wait before the re-runs: the longest any planned re-run asks for."""
        return max((rerun.wait_seconds for rerun in self.reruns), default=0)


def _classifier_for(*, step: str | None) -> JobClassifier | None:
    return next((clf for clf in CLASSIFIERS if clf.step == step), None)


def _current_failures(*, jobs: Sequence[RecordedJob], run_attempt: int) -> list[RecordedJob]:
    return [job for job in jobs if job.attempt == run_attempt and job.conclusion == FAILURE]


def jobs_needing_logs(*, jobs: Sequence[RecordedJob], run_attempt: int) -> tuple[int, ...]:
    """The current attempt's failed jobs whose first failed step some classifier covers."""
    return tuple(
        job.job_id
        for job in _current_failures(jobs=jobs, run_attempt=run_attempt)
        if _classifier_for(step=job.first_failed_step) is not None
    )


def _match(*, classifier: JobClassifier, log_text: str) -> tuple[str, str] | None:
    for line in log_text.splitlines():
        for signature in classifier.signatures:
            if signature.pattern.search(line):
                return signature.name, line.strip()
    return None


def _attempt_number(
    *, jobs: Sequence[RecordedJob], job: RecordedJob, classifier: JobClassifier
) -> int:
    return len(
        {
            other.job_id
            for other in jobs
            if other.name == job.name
            and other.conclusion == FAILURE
            and other.first_failed_step == classifier.step
            and other.attempt <= job.attempt
        }
    )


def _plan_one(
    *, jobs: Sequence[RecordedJob], job: RecordedJob, logs: Mapping[int, str]
) -> PlannedRerun | LeftJob:
    classifier = _classifier_for(step=job.first_failed_step)
    if classifier is None:
        reason = f"failed at step {job.first_failed_step!r}, which no re-run classifier covers"
        return LeftJob(job_id=job.job_id, name=job.name, reason=reason)
    log_text = logs.get(job.job_id)
    if log_text is None:
        reason = f"failed at {classifier.step!r}, but its log was not readable"
        return LeftJob(job_id=job.job_id, name=job.name, reason=reason)
    matched = _match(classifier=classifier, log_text=log_text)
    if matched is None:
        reason = f"failed at {classifier.step!r} without a {classifier.cause} signature"
        return LeftJob(job_id=job.job_id, name=job.name, reason=reason)
    attempt = _attempt_number(jobs=jobs, job=job, classifier=classifier)
    cap = len(classifier.waits_seconds)
    if attempt > cap:
        reason = f"already re-run {cap} times for {classifier.cause}; the attempt cap is reached"
        return LeftJob(job_id=job.job_id, name=job.name, reason=reason)
    signature, line = matched
    return PlannedRerun(
        job_id=job.job_id,
        name=job.name,
        cause=classifier.cause,
        signature=signature,
        attempt=attempt,
        max_attempts=cap,
        wait_seconds=classifier.waits_seconds[attempt - 1],
        matched_line=line,
    )


def plan_reruns(
    *, jobs: Sequence[RecordedJob], run_attempt: int, logs: Mapping[int, str]
) -> RerunPlan:
    """Classify every failed job of the run's current attempt into re-run or left."""
    outcomes = [
        _plan_one(jobs=jobs, job=job, logs=logs)
        for job in _current_failures(jobs=jobs, run_attempt=run_attempt)
    ]
    return RerunPlan(
        reruns=tuple(o for o in outcomes if isinstance(o, PlannedRerun)),
        left=tuple(o for o in outcomes if isinstance(o, LeftJob)),
    )


def plan_payload(*, plan: RerunPlan) -> dict[str, object]:
    """The plan as the JSON object the workflow reads."""
    return {
        "rerun_count": len(plan.reruns),
        "left_count": len(plan.left),
        "wait_seconds": plan.wait_seconds,
        "reruns": [asdict(rerun) for rerun in plan.reruns],
        "left": [asdict(left) for left in plan.left],
    }


def summary_lines(*, plan: RerunPlan, repository: str, run_id: str) -> list[str]:
    """The run log and step summary lines: one per re-run, one per job left."""
    lines = [f"CI infrastructure re-run reconciler: {repository} run {run_id}"]
    lines.extend(
        (
            f"- re-run job {r.name!r} (id {r.job_id}): attempt {r.attempt} of {r.max_attempts} "
            f"after a {r.wait_seconds}s wait, cause {r.cause}, signature {r.signature}: "
            f"{r.matched_line}"
        )
        for r in plan.reruns
    )
    lines.extend(
        f"- left for its owner: job {left.name!r} (id {left.job_id}): {left.reason}"
        for left in plan.left
    )
    if not plan.reruns and not plan.left:
        lines.append("- no failed job in the run's current attempt")
    return lines
