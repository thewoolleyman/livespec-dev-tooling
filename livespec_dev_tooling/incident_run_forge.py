"""Bounded read-only collection of one original GitHub Actions run attempt."""

from __future__ import annotations

import base64
import hashlib
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from livespec_dev_tooling._incident_run_types import (
    EvidenceRefusal,
    ObservedJob,
    OriginalRun,
    RunSnapshot,
)
from livespec_dev_tooling.incident_ci_job_identity import attempt_jobs
from livespec_dev_tooling.incident_forge_reads import ForgeRead

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))
from returns.io import impure_safe  # noqa: E402
from returns.pipeline import is_successful  # noqa: E402
from returns.unsafe import unsafe_perform_io  # noqa: E402

__all__: list[str] = ["ForgeRunReader"]
_MISSING_SOURCE = "original workflow source missing"

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-kobmka
# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-jvfb7x


def _object(*, value: object) -> dict[str, object]:
    return cast("dict[str, object]", value) if isinstance(value, dict) else {}


def _refuse(*, detail: str) -> EvidenceRefusal:
    return EvidenceRefusal(code="incident-original-run-unavailable", detail=detail)


@impure_safe
def _source_digest(*, response: object) -> str:
    row = _object(value=response)
    if row.get("encoding") != "base64" or not isinstance(row.get("content"), str):
        raise ValueError(_MISSING_SOURCE)
    content = cast("str", row["content"])
    source = base64.b64decode("".join(content.split()), validate=True)
    return hashlib.sha256(source).hexdigest()


def _job(*, value: object) -> ObservedJob | None:
    row = _object(value=value)
    if (
        not all(isinstance(row.get(k), str) and row[k] for k in ("name", "status", "html_url"))
        or type(row.get("id")) is not int
        or cast("int", row["id"]) <= 0
        or (row.get("conclusion") is not None and not isinstance(row["conclusion"], str))
    ):
        return None
    return ObservedJob(
        name=cast("str", row["name"]),
        job_id=cast("int", row["id"]),
        status=cast("str", row["status"]),
        conclusion=cast("str | None", row.get("conclusion")),
        evidence_url=cast("str", row["html_url"]),
    )


@dataclass(frozen=True, kw_only=True)
class ForgeRunReader:
    """Reads through the controller's forge access, never candidate-supplied argv.

    The provider performs GETs only, with a read-only token. It cannot cancel,
    rerun, delete or replace the original run. The original attempt endpoint
    excludes later job reruns.
    The graph digest is checked against actual workflow bytes at the original SHA.
    """

    read: ForgeRead
    budget_seconds: float = 45

    def __call__(self, original: OriginalRun) -> RunSnapshot | EvidenceRefusal:
        if self.budget_seconds <= 0:
            return _refuse(detail="invalid provisioned forge collection budget")
        deadline = time.monotonic() + self.budget_seconds
        base = (
            f"repos/{original.repository}/actions/runs/{original.run_id}"
            f"/attempts/{original.run_attempt}"
        )
        read = self._read(endpoint=base, deadline=deadline)
        if isinstance(read, EvidenceRefusal):
            return read
        metadata = _object(value=read)
        if (
            metadata.get("id") != original.run_id
            or metadata.get("run_attempt") != original.run_attempt
            or metadata.get("head_sha") != original.merge_sha
            or _object(value=metadata.get("repository")).get("full_name") != original.repository
            or metadata.get("path") != original.workflow_path
            or not isinstance(metadata.get("status"), str)
        ):
            return _refuse(detail="forge returned another run, attempt, repository or revision")
        source_check = self._check_source(original=original, deadline=deadline)
        if source_check is not None:
            return source_check
        jobs = self._jobs(base=base, deadline=deadline)
        if isinstance(jobs, EvidenceRefusal):
            return jobs
        return RunSnapshot(
            repository=original.repository,
            run_id=original.run_id,
            run_attempt=original.run_attempt,
            head_sha=original.merge_sha,
            status=cast("str", metadata["status"]),
            jobs=jobs,
            graph_digest=original.graph_digest,
            complete_listing=True,
        )

    def _check_source(self, *, original: OriginalRun, deadline: float) -> EvidenceRefusal | None:
        source = self._read(
            endpoint=f"repos/{original.repository}/contents/{original.workflow_path}?ref={original.merge_sha}",
            deadline=deadline,
        )
        if isinstance(source, EvidenceRefusal):
            return source
        digest = _source_digest(response=source)
        if not is_successful(digest) or unsafe_perform_io(digest.unwrap()) != original.graph_digest:
            return _refuse(detail="expected graph is not bound to actual original workflow source")
        return None

    def _read(self, *, endpoint: str, deadline: float) -> object:
        return _DeadlineRead(read=self.read, deadline=deadline).fetch(endpoint=endpoint)

    def _jobs(self, *, base: str, deadline: float) -> tuple[ObservedJob, ...] | EvidenceRefusal:
        rows = attempt_jobs(
            read=_DeadlineRead(read=self.read, deadline=deadline), path=f"{base}/jobs"
        )
        if rows is None:
            return _refuse(detail="original-attempt job listing is unavailable or incomplete")
        decoded = [_job(value=row) for row in rows]
        if any(job is None for job in decoded):
            return _refuse(detail="malformed original-attempt job")
        return tuple(cast("list[ObservedJob]", decoded))


@dataclass(frozen=True, kw_only=True)
class _DeadlineRead:
    """One forge read held to this collection's one deadline; also the jobs pager's `ForgeRead`."""

    read: ForgeRead
    deadline: float

    def fetch(self, *, endpoint: str) -> object:
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            return _refuse(detail="original-run collection budget exhausted; no complete listing")
        value = self.read(endpoint)
        if value is None:
            return _refuse(detail="authenticated original-run request failed; no complete listing")
        return value

    def __call__(self, endpoint: str) -> object:
        value = self.fetch(endpoint=endpoint)
        return None if isinstance(value, EvidenceRefusal) else value
