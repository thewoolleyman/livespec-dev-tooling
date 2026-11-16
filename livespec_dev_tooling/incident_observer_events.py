"""Authenticate early GitHub job callbacks without querying candidate code."""

from __future__ import annotations

import hashlib
import hmac
from typing import cast

from livespec_dev_tooling._incident_observer_types import LeafCompletion
from livespec_dev_tooling.incident_strict_json import IncidentJsonRefusalError, strict_json

__all__: list[str] = ["classify_callback", "completion_run_attempt", "verify_leaf_completion"]
_MAX_CALLBACK_BYTES = 1_000_000

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-47ij37


def _authenticated(
    *, body: bytes, signature: str, event: str, delivery_id: str, secret: bytes
) -> dict[str, object] | None:
    """The JSON object of a correctly signed `workflow_job` delivery, or None."""
    if not secret or event != "workflow_job" or not delivery_id or len(body) > _MAX_CALLBACK_BYTES:
        return None
    expected = "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature.encode(), expected.encode()):
        return None
    return _read_object(body=body)


def verify_leaf_completion(
    *, body: bytes, signature: str, event: str, delivery_id: str, secret: bytes
) -> LeafCompletion | None:
    """Verify raw callback bytes before trusting routing or job identity.

    The secret belongs to the independent controller's webhook adapter. No
    workflow-completed event, aggregate verdict, or fresh forge call is needed.
    """
    record = _authenticated(
        body=body, signature=signature, event=event, delivery_id=delivery_id, secret=secret
    )
    if record is None or record.get("action") != "completed":
        return None
    return _parse_job(record=record, delivery_id=delivery_id)


def _ignored_job_action(
    *, body: bytes, signature: str, event: str, delivery_id: str, secret: bytes, repository: str
) -> str | None:
    """The action of a correctly signed job delivery for `repository` that is not a completion.

    The webhook delivers every `workflow_job` action, so `queued` and `in_progress` arrive
    beside `completed`. Those are authenticated and simply not leaf completions: answering
    them as refusals made the hook's last response read as an outage (sbxun3). Anything
    unauthenticated, for another repository, or malformed returns None and stays refused.
    """
    record = _authenticated(
        body=body, signature=signature, event=event, delivery_id=delivery_id, secret=secret
    )
    action = None if record is None else record.get("action")
    named = None if record is None else record.get("repository")
    full = cast("dict[str, object]", named).get("full_name") if isinstance(named, dict) else None
    ok = isinstance(action, str) and action != "completed" and full == repository
    return f"workflow_job action {action} is not a completion" if ok else None


def _parse_job(*, record: dict[str, object], delivery_id: str) -> LeafCompletion | None:
    job = record.get("workflow_job")
    repository = record.get("repository")
    if not isinstance(job, dict) or not isinstance(repository, dict):
        return None
    job = cast("dict[str, object]", job)
    repository = cast("dict[str, object]", repository)
    name, sha, branch = (job.get(key) for key in ("name", "head_sha", "head_branch"))
    conclusion, repo = job.get("conclusion"), repository.get("full_name")
    run_id, job_id = job.get("run_id"), job.get("id")
    if not all(isinstance(value, str) and value for value in (name, sha, branch, conclusion, repo)):
        return None
    if type(run_id) is not int or type(job_id) is not int or run_id <= 0 or job_id <= 0:
        return None
    if job.get("status") != "completed":
        return None
    return LeafCompletion(
        delivery_id=delivery_id,
        repository=cast("str", repo),
        head_sha=cast("str", sha),
        branch=cast("str", branch),
        run_id=run_id,
        job_id=job_id,
        job_name=cast("str", name),
        conclusion=cast("str", conclusion),
    )


def classify_callback(
    *, body: bytes, signature: str, event: str, delivery_id: str, secret: bytes, repository: str
) -> LeafCompletion | str | None:
    """A leaf completion, the reason a signed non-completion is ignored, or None (refused)."""
    completion = verify_leaf_completion(
        body=body, signature=signature, event=event, delivery_id=delivery_id, secret=secret
    )
    if completion is not None:
        return completion
    return _ignored_job_action(
        body=body,
        signature=signature,
        event=event,
        delivery_id=delivery_id,
        secret=secret,
        repository=repository,
    )


def completion_run_attempt(*, body: bytes) -> int | None:
    """The run attempt of an already verified `workflow_job` callback body, or None.

    Call only after `verify_leaf_completion` accepted the same bytes: this reads the
    attempt the leaf completion does not carry, and authenticates nothing itself.
    """
    record = _read_object(body=body)
    job = record.get("workflow_job") if record is not None else None
    attempt = cast("dict[str, object]", job).get("run_attempt") if isinstance(job, dict) else None
    return attempt if type(attempt) is int and attempt > 0 else None


def _read_object(*, body: bytes) -> dict[str, object] | None:
    try:
        record: object = strict_json(text=body, limit=None)
    except IncidentJsonRefusalError:
        return None
    return cast("dict[str, object]", record) if isinstance(record, dict) else None
