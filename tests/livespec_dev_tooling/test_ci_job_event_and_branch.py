"""CI job spans retain the run fields used for event-duration analysis."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from livespec_dev_tooling import ci_run_telemetry

__all__: list[str] = []


def _attributes(*, span: dict[str, Any]) -> dict[str, str]:
    """Flatten an OTLP span's attribute representation for schema assertions."""
    return {
        attribute["key"]: next(iter(attribute["value"].values()))
        for attribute in span["attributes"]
    }


def test_a_fixture_job_span_carries_its_runs_event_and_branch(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Job-duration queries can split a recorded merge-group job by its run metadata."""
    run = {
        "createdAt": "2026-11-17T10:59:00Z",
        "startedAt": "2026-11-17T11:00:00Z",
        "updatedAt": "2026-11-17T11:01:00Z",
        "headBranch": "gh-readonly-queue/master/pr-123-abcdef",
        "event": "merge_group",
        "jobs": [
            {
                "databaseId": 101,
                "name": "check-python",
                "conclusion": "success",
                "startedAt": "2026-11-17T11:00:00Z",
                "completedAt": "2026-11-17T11:01:00Z",
            }
        ],
    }
    run_path = tmp_path / "run.json"
    jobs_path = tmp_path / "jobs.json"
    _ = run_path.write_text(json.dumps(run), encoding="utf-8")
    _ = jobs_path.write_text(json.dumps({"jobs": []}), encoding="utf-8")
    posted: list[dict[str, Any]] = []

    class _Response:
        status = 200

        def read(self) -> bytes:
            return b'{"partialSuccess":{"rejectedSpans":"0"}}'

    class _Connection:
        def __init__(self, *, host: str, timeout: float) -> None:
            assert host == "api.honeycomb.io"
            assert timeout == 30.0

        def request(self, method: str, url: str, body: str, headers: dict[str, str]) -> None:
            assert method == "POST"
            assert url == "/v1/traces"
            assert headers["x-honeycomb-team"] == "test-key"
            posted.append(json.loads(body))

        def getresponse(self) -> _Response:
            return _Response()

        def close(self) -> None:
            return None

    def _connection(host: str, timeout: float) -> _Connection:
        return _Connection(host=host, timeout=timeout)

    monkeypatch.setattr("http.client.HTTPSConnection", _connection)
    assert (
        ci_run_telemetry.main(
            argv=[
                "--repo",
                "livespec-ai/livespec-dev-tooling",
                "--run-id",
                "42",
                "--run-json",
                str(run_path),
                "--jobs-json",
                str(jobs_path),
                "--ingest-key",
                "test-key",
            ]
        )
        == 0
    )

    payload = posted[0]
    span = payload["resourceSpans"][0]["scopeSpans"][0]["spans"][1]
    assert _attributes(span=span) == {
        "repo": "livespec-ai/livespec-dev-tooling",
        "ci.run_id": "42",
        "ci.job.name": "check-python",
        "ci.job.conclusion": "success",
        "ci.job.queue_ms": "0",
        "git.branch": "gh-readonly-queue/master/pr-123-abcdef",
        "ci.event": "merge_group",
    }
