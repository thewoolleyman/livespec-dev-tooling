"""Authenticate early GitHub job callbacks without querying candidate code."""

from __future__ import annotations

import hashlib
import hmac
from typing import cast

from livespec_dev_tooling._incident_observer_types import LeafCompletion
from livespec_dev_tooling.incident_strict_json import IncidentJsonRefusalError, strict_json

__all__: list[str] = ["verify_leaf_completion"]
_MAX_CALLBACK_BYTES = 1_000_000

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-47ij37


def verify_leaf_completion(
    *, body: bytes, signature: str, event: str, delivery_id: str, secret: bytes
) -> LeafCompletion | None:
    """Verify raw callback bytes before trusting routing or job identity.

    The secret belongs to the independent controller's webhook adapter. No
    workflow-completed event, aggregate verdict, or fresh forge call is needed.
    """
    if not secret or event != "workflow_job" or not delivery_id or len(body) > _MAX_CALLBACK_BYTES:
        return None
    expected = "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature.encode(), expected.encode()):
        return None
    record = _read_object(body=body)
    if record is None or record.get("action") != "completed":
        return None
    return _parse_job(record=record, delivery_id=delivery_id)


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


def _read_object(*, body: bytes) -> dict[str, object] | None:
    try:
        record: object = strict_json(text=body, limit=None)
    except IncidentJsonRefusalError:
        return None
    return cast("dict[str, object]", record) if isinstance(record, dict) else None
