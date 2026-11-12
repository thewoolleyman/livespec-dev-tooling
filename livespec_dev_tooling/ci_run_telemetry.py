#!/usr/bin/env python3
"""Export a GitHub Actions run and its completed jobs as Honeycomb OTLP spans.

The module replaces the fleet's drift-prone repository-local CI telemetry
exporters.  It accepts recorded GitHub documents for deterministic tests; when
those documents are not supplied, it reads the same run and jobs data through
the shared budgeted GitHub client used by the rest of this package.
"""

from __future__ import annotations

import argparse
import http.client
import json
import os
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Final, cast

from livespec_dev_tooling.budgeted_gh import gh_read

__all__: list[str] = ["main"]

_DATASET: Final = "github-ci"
_NAMESPACE: Final = "livespec-family"
_HONEYCOMB_HOST: Final = "api.honeycomb.io"
_HONEYCOMB_PATH: Final = "/v1/traces"
_SCOPE_NAME: Final = "livespec.github-ci-export"
_SCOPE_VERSION: Final = "1.0.0"
_HTTP_OK: Final = 200
_POST_TIMEOUT_SECONDS: Final = 30.0


def _arguments(*, argv: Sequence[str] | None) -> argparse.Namespace:
    """Parse CLI arguments, taking CI defaults from the established environment."""
    parser = argparse.ArgumentParser(description=__doc__)
    _ = parser.add_argument("--repo", default=os.environ.get("REPO", ""))
    _ = parser.add_argument("--run-id", type=int, default=os.environ.get("RUN_ID") or None)
    _ = parser.add_argument("--run-json", type=Path)
    _ = parser.add_argument("--jobs-json", type=Path)
    _ = parser.add_argument(
        "--ingest-key",
        default=os.environ.get("HONEYCOMB_GITHUB_CI_INGEST_KEY_LIVESPEC", ""),
    )
    return parser.parse_args(argv)


def _hex_id(*, value: int, width: int) -> str:
    """Render GitHub's integer identifier as a fixed-width valid OTLP id."""
    return f"{value:0{width}x}"


def _nanoseconds(*, timestamp: object) -> str:
    """Convert an ISO-8601 GitHub timestamp to the OTLP JSON nanosecond string."""
    parsed = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    utc = parsed.astimezone(timezone.utc)
    seconds = int(utc.timestamp())
    return str(seconds * 1_000_000_000 + utc.microsecond * 1_000)


def _attribute(*, key: str, value: object, value_type: str = "stringValue") -> dict[str, object]:
    """Build one OTLP JSON attribute in the legacy exporter's value representation."""
    return {"key": key, "value": {value_type: str(value)}}


def _status(*, conclusion: object) -> int:
    """Map GitHub's successful conclusion to OTLP OK and every other value to error."""
    return 1 if conclusion == "success" else 2


def _run_span(*, repo: str, run_id: int, run: dict[str, object]) -> dict[str, object]:
    """Build the root ``ci.run`` span with the shell exporter's fields."""
    conclusion = run.get("conclusion", "")
    return {
        "traceId": _hex_id(value=run_id, width=32),
        "spanId": _hex_id(value=run_id, width=16),
        "name": "ci.run",
        "kind": 1,
        "startTimeUnixNano": _nanoseconds(timestamp=run.get("startedAt") or run["createdAt"]),
        "endTimeUnixNano": _nanoseconds(timestamp=run["updatedAt"]),
        "attributes": [
            _attribute(key="repo", value=repo),
            _attribute(key="ci.run_id", value=run_id, value_type="intValue"),
            _attribute(key="ci.conclusion", value=conclusion),
            _attribute(key="ci.title", value=run.get("displayTitle", "")),
            _attribute(key="git.commit.sha", value=run.get("headSha", "")),
            _attribute(key="git.branch", value=run.get("headBranch", "")),
            _attribute(key="ci.event", value=run.get("event", "")),
        ],
        "status": {"code": _status(conclusion=conclusion)},
    }


def _created_by_job_id(*, jobs: dict[str, object]) -> dict[int, object]:
    """Index REST job creation times unavailable in ``gh run view`` data."""
    records = cast(list[dict[str, object]], jobs.get("jobs", []))
    return {
        int(cast(int | str, record["id"])): record["created_at"]
        for record in records
        if "id" in record and "created_at" in record
    }


def _job_span(
    *,
    repo: str,
    run_id: int,
    job: dict[str, object],
    created_by_id: dict[int, object],
) -> dict[str, object] | None:
    """Build a child span only when the GitHub job has completed."""
    started_at = job.get("startedAt")
    completed_at = job.get("completedAt")
    if not started_at or not completed_at:
        return None
    job_id = int(cast(int | str, job["databaseId"]))
    start_ns = int(_nanoseconds(timestamp=started_at))
    created_at = created_by_id.get(job_id)
    queue_ms = 0
    if created_at:
        queue_ms = max(0, (start_ns - int(_nanoseconds(timestamp=created_at))) // 1_000_000)
    conclusion = job.get("conclusion", "")
    return {
        "traceId": _hex_id(value=run_id, width=32),
        "spanId": _hex_id(value=job_id, width=16),
        "parentSpanId": _hex_id(value=run_id, width=16),
        "name": f"ci.job.{job.get('name', '')}",
        "kind": 1,
        "startTimeUnixNano": str(start_ns),
        "endTimeUnixNano": _nanoseconds(timestamp=completed_at),
        "attributes": [
            _attribute(key="repo", value=repo),
            _attribute(key="ci.run_id", value=run_id, value_type="intValue"),
            _attribute(key="ci.job.name", value=job.get("name", "")),
            _attribute(key="ci.job.conclusion", value=conclusion),
            _attribute(key="ci.job.queue_ms", value=queue_ms, value_type="intValue"),
        ],
        "status": {"code": _status(conclusion=conclusion)},
    }


def _payload(
    *, repo: str, run_id: int, run: dict[str, object], jobs: dict[str, object]
) -> dict[str, object]:
    """Build the complete OTLP/HTTP JSON document used by the former shell exporter."""
    created_by_id = _created_by_job_id(jobs=jobs)
    job_spans = [
        span
        for job in cast(list[dict[str, object]], run.get("jobs", []))
        if (
            span := _job_span(
                repo=repo,
                run_id=run_id,
                job=job,
                created_by_id=created_by_id,
            )
        )
        is not None
    ]
    return {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        _attribute(key="service.name", value=_DATASET),
                        _attribute(key="service.namespace", value=_NAMESPACE),
                    ]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": _SCOPE_NAME, "version": _SCOPE_VERSION},
                        "spans": [_run_span(repo=repo, run_id=run_id, run=run), *job_spans],
                    }
                ],
            }
        ]
    }


def _read_json(*, path: Path) -> dict[str, object]:
    """Load one recorded GitHub JSON response."""
    return cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))


def _github_documents(
    *, repo: str, run_id: int
) -> tuple[dict[str, object], dict[str, object]] | None:
    """Read the run and each paginated REST jobs response through the shared client."""
    run_response = gh_read(
        args=[
            "run",
            "view",
            str(run_id),
            "--repo",
            repo,
            "--json",
            "databaseId,headSha,headBranch,event,displayTitle,conclusion,createdAt,startedAt,updatedAt,jobs",
        ]
    )
    jobs_response = gh_read(
        args=[
            "api",
            f"repos/{repo}/actions/runs/{run_id}/jobs?per_page=100",
            "--paginate",
        ]
    )
    if run_response.returncode != 0 or jobs_response.returncode != 0:
        return None
    run = cast(dict[str, object], json.loads(run_response.stdout))
    pages = [
        cast(dict[str, object], json.loads(line))
        for line in jobs_response.stdout.splitlines()
        if line
    ]
    jobs = [job for page in pages for job in cast(list[dict[str, object]], page.get("jobs", []))]
    return run, {"jobs": jobs}


def _post(*, ingest_key: str, payload: dict[str, object]) -> tuple[int, int | str]:
    """POST the payload to the fixed Honeycomb endpoint and read its receipt."""
    connection = http.client.HTTPSConnection(_HONEYCOMB_HOST, timeout=_POST_TIMEOUT_SECONDS)
    try:
        connection.request(
            "POST",
            _HONEYCOMB_PATH,
            body=json.dumps(payload),
            headers={
                "x-honeycomb-team": ingest_key,
                "Content-Type": "application/json",
            },
        )
        response = connection.getresponse()
        document = cast(dict[str, object], json.loads(response.read().decode("utf-8")))
        partial_success = cast(dict[str, object], document.get("partialSuccess", {}))
        rejected = cast(int | str, partial_success.get("rejectedSpans", 0))
        return response.status, rejected
    finally:
        connection.close()


def main(*, argv: Sequence[str] | None = None) -> int:
    """Export a CI run's root and completed-job spans, returning a shell-friendly status."""
    arguments = _arguments(argv=argv)
    if not arguments.repo or not arguments.run_id or not arguments.ingest_key:
        return 2
    if bool(arguments.run_json) != bool(arguments.jobs_json):
        return 2
    documents = (
        (_read_json(path=arguments.run_json), _read_json(path=arguments.jobs_json))
        if arguments.run_json and arguments.jobs_json
        else _github_documents(repo=arguments.repo, run_id=arguments.run_id)
    )
    if documents is None:
        return 1
    run, jobs = documents
    status, rejected = _post(
        ingest_key=arguments.ingest_key,
        payload=_payload(repo=arguments.repo, run_id=arguments.run_id, run=run, jobs=jobs),
    )
    return 0 if status == _HTTP_OK and str(rejected) == "0" else 1


if __name__ == "__main__":
    raise SystemExit(main())
