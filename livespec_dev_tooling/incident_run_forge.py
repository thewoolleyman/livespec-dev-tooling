"""Bounded read-only collection of one original GitHub Actions run attempt."""

from __future__ import annotations

import base64
import hashlib
import json
import subprocess
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
from livespec_dev_tooling.budgeted_gh import gh_read

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))
from returns.io import impure_safe  # noqa: E402
from returns.pipeline import is_successful  # noqa: E402
from returns.unsafe import unsafe_perform_io  # noqa: E402

__all__: list[str] = ["ForgeRunReader"]
_MAX_RESPONSE_BYTES = 4_000_000
_RESPONSE_TOO_LARGE = "original-run response exceeds collection budget"
_MISSING_SOURCE = "original workflow source missing"
_READ_FAILED = "authenticated original-run request failed"

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-kobmka


@impure_safe
def _request(*, command: tuple[str, ...] | None, endpoint: str, timeout: float) -> object:
    if command is None:
        result = gh_read(args=["api", endpoint], timeout=timeout)
        if result.returncode != 0:
            raise RuntimeError(_READ_FAILED)
    else:
        result = subprocess.run(  # noqa: S603 -- provisioned local provider, never candidate argv.
            [*command, endpoint],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=True,
        )
    if len(result.stdout) > _MAX_RESPONSE_BYTES:
        raise ValueError(_RESPONSE_TOO_LARGE)
    return cast(object, json.loads(result.stdout))


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
    """Provision with an approved read credential, never candidate-supplied argv.

    The provider performs GETs only. It cannot cancel, rerun, delete or replace
    the original run. The original attempt endpoint excludes later job reruns.
    The graph digest is checked against actual workflow bytes at the original SHA.
    """

    command: tuple[str, ...] | None = None
    budget_seconds: float = 45
    max_pages: int = 20

    def __call__(self, original: OriginalRun) -> RunSnapshot | EvidenceRefusal:
        if self.command == () or self.budget_seconds <= 0 or self.max_pages <= 0:
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
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return _refuse(detail="original-run collection budget exhausted; no complete listing")
        read = _request(command=self.command, endpoint=endpoint, timeout=min(10, remaining))
        if not is_successful(read):
            return _refuse(detail="authenticated original-run request failed; no complete listing")
        return unsafe_perform_io(read.unwrap())

    def _jobs(self, *, base: str, deadline: float) -> tuple[ObservedJob, ...] | EvidenceRefusal:
        jobs: list[ObservedJob] = []
        expected_total: int | None = None
        for page in range(1, self.max_pages + 1):
            read = self._page(base=base, page=page, deadline=deadline)
            if isinstance(read, EvidenceRefusal):
                return read
            total, batch = read
            if expected_total is not None and total != expected_total:
                return _refuse(detail="original-attempt job listing changed while paginating")
            expected_total = total
            jobs.extend(batch)
            if len(jobs) == expected_total:
                return tuple(jobs)
            if not batch or len(jobs) > expected_total:
                return _refuse(detail="incomplete or overflowing original-attempt listing")
        return _refuse(detail="original-attempt job listing exceeds page budget")

    def _page(
        self, *, base: str, page: int, deadline: float
    ) -> tuple[int, list[ObservedJob]] | EvidenceRefusal:
        read = self._read(endpoint=f"{base}/jobs?per_page=100&page={page}", deadline=deadline)
        if isinstance(read, EvidenceRefusal):
            return read
        row = _object(value=read)
        total, batch = row.get("total_count"), row.get("jobs")
        if type(total) is not int or not isinstance(batch, list) or total < 0:
            return _refuse(detail="malformed original-attempt jobs page")
        decoded = [_job(value=value) for value in cast("list[object]", batch)]
        if any(job is None for job in decoded):
            return _refuse(detail="malformed original-attempt job")
        return total, cast("list[ObservedJob]", decoded)
