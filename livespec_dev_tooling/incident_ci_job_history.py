"""Independently observe a RETAINED historical CI job; never current PR or latest attempt."""

from __future__ import annotations

from typing import Any

from livespec_dev_tooling._incident_ci_attachment_store import raw_fact
from livespec_dev_tooling.budgeted_gh import github_api_url
from livespec_dev_tooling.incident_ci_job_identity import attempt_jobs, forge_object, forge_record
from livespec_dev_tooling.incident_forge_reads import ForgeRead

__all__: list[str] = ["classify_snapshot", "observe_retained_job"]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-si6uu7
_GITHUB_ACTIONS_APP = 15368
_ACTIVE = frozenset({"queued", "in_progress", "waiting", "requested", "pending"})
_TERMINAL = {
    "success": "successful",
    "failure": "failed",
    "timed_out": "failed",
    "startup_failure": "failed",
    "skipped": "skipped",
    "cancelled": "cancelled",
}


def observe_retained_job(*, binding: dict[str, Any], read: ForgeRead) -> tuple[str, dict[str, Any]]:
    """Read the exact retained attempt, job and check through the budgeted forge."""
    root = f"repos/{binding['repository']}"
    attempt_path = f"{root}/actions/runs/{binding['run_id']}/attempts/{binding['run_attempt']}"
    check_path = f"{root}/check-runs/{binding['check_run_id']}"
    attempt = forge_record(read=read, path=attempt_path)
    jobs = attempt_jobs(read=read, path=f"{attempt_path}/jobs")
    check = forge_record(read=read, path=check_path)
    if not attempt or jobs is None or not check:
        return _facts(status="unavailable", reason="retained forge observation unavailable")
    matched = [v for v in jobs if v.get("id") == binding["job_id"]]
    job = matched[0] if len(matched) == 1 else {}
    if not (
        _attempt(attempt=attempt, binding=binding)
        and _job(job=job, binding=binding, url=github_api_url(path=check_path))
        and _check(check=check, binding=binding)
    ):
        return _facts(status="conflict", reason="forge identity contradicts retained attachment")
    raw = (job.get("status"), job.get("conclusion"), check.get("status"), check.get("conclusion"))
    if not all(raw_fact(value=value) for value in raw):
        return _facts(status="unavailable", reason="malformed forge job or check status")
    status, reason = classify_snapshot(
        job_status=raw[0], job_conclusion=raw[1], check_status=raw[2], check_conclusion=raw[3]
    )
    return _facts(
        status=status,
        reason=reason,
        job_status=raw[0],
        job_conclusion=raw[1],
        check_status=raw[2],
        check_conclusion=raw[3],
    )


def classify_snapshot(
    *, job_status: Any, job_conclusion: Any, check_status: Any, check_conclusion: Any
) -> tuple[str, str]:
    """Success needs BOTH completed views to conclude success; nothing defaults to it."""
    if job_status is None or check_status is None:
        return "unavailable", "job or check status absent"
    if job_status in _ACTIVE and check_status in _ACTIVE:
        return "pending", "job and check not completed"
    if job_status != "completed" or check_status != "completed":
        return "conflict", "incoherent job and check completion"
    if job_conclusion != check_conclusion:
        return "conflict", "job and check conclusions disagree"
    status = _TERMINAL.get(job_conclusion) if isinstance(job_conclusion, str) else None
    if status is None:
        return "unavailable", "unclassified completed conclusion"
    return status, "job and check concluded " + job_conclusion


def _facts(
    *,
    status: str,
    reason: str,
    job_status: str | None = None,
    job_conclusion: str | None = None,
    check_status: str | None = None,
    check_conclusion: str | None = None,
) -> tuple[str, dict[str, Any]]:
    return status, {
        "snapshot_status": status,
        "reason": reason,
        "job_status": job_status,
        "job_conclusion": job_conclusion,
        "check_status": check_status,
        "check_conclusion": check_conclusion,
    }


def _repo(*, value: Any, binding: dict[str, Any]) -> bool:
    repo = forge_object(value=value)
    owner = forge_object(value=repo.get("owner"))
    return (
        repo.get("full_name") == binding["repository"]
        and type(repo.get("id")) is int
        and repo.get("id") == binding["repository_id"]
        and type(owner.get("id")) is int
        and owner.get("id") == binding["repository_owner_id"]
    )


def _attempt(*, attempt: dict[str, Any], binding: dict[str, Any]) -> bool:
    return (
        type(attempt.get("id")) is int
        and attempt.get("id") == binding["run_id"]
        and type(attempt.get("run_attempt")) is int
        and attempt.get("run_attempt") == binding["run_attempt"]
        and type(attempt.get("check_suite_id")) is int
        and attempt.get("check_suite_id") == binding["check_suite_id"]
        and attempt.get("head_sha") == binding["head_sha"]
        and attempt.get("event") == "pull_request"
        and _repo(value=attempt.get("repository"), binding=binding)
    )


def _job(*, job: dict[str, Any], binding: dict[str, Any], url: str) -> bool:
    return (
        type(job.get("id")) is int
        and type(job.get("run_id")) is int
        and job.get("run_id") == binding["run_id"]
        and job.get("check_run_url") == url
        and job.get("head_sha") == binding["head_sha"]
    )


def _check(*, check: dict[str, Any], binding: dict[str, Any]) -> bool:
    app, suite = forge_object(value=check.get("app")), forge_object(value=check.get("check_suite"))
    return (
        type(check.get("id")) is int
        and check.get("id") == binding["check_run_id"]
        and check.get("head_sha") == binding["head_sha"]
        and type(app.get("id")) is int
        and app.get("id") == _GITHUB_ACTIONS_APP
        and app.get("slug") == "github-actions"
        and type(suite.get("id")) is int
        and suite.get("id") == binding["check_suite_id"]
    )
