"""The shared CI run exporter preserves the OTLP schema of the former shell exporter."""

from __future__ import annotations

import importlib
import json
from copy import deepcopy
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from livespec_dev_tooling.budgeted_gh import GhRead

__all__: list[str] = []


_MODULE = "livespec_dev_tooling.ci_run_telemetry"
_MODULE_PATH = Path(__file__).resolve().parents[2] / "livespec_dev_tooling" / "ci_run_telemetry.py"
_RUN_ID = 42
_REPOSITORY = "thewoolleyman/livespec-dev-tooling"
_RUN = {
    "databaseId": _RUN_ID,
    "headSha": "a" * 40,
    "headBranch": "master",
    "event": "push",
    "displayTitle": "publish telemetry",
    "conclusion": "success",
    "createdAt": "2026-11-12T03:00:00Z",
    "startedAt": "2026-11-12T03:01:00Z",
    "updatedAt": "2026-11-12T03:03:00Z",
    "jobs": [
        {
            "databaseId": 101,
            "name": "check-python",
            "conclusion": "success",
            "startedAt": "2026-11-12T03:01:05Z",
            "completedAt": "2026-11-12T03:02:00Z",
        },
        {
            "databaseId": 102,
            "name": "check-metadata",
            "conclusion": "failure",
            "startedAt": "2026-11-12T03:01:10Z",
            "completedAt": "2026-11-12T03:02:30Z",
        },
        {
            "databaseId": 103,
            "name": "not-completed",
            "conclusion": "",
            "startedAt": "2026-11-12T03:01:10Z",
            "completedAt": None,
        },
    ],
}
_JOBS = {
    "jobs": [
        {"id": 101, "created_at": "2026-11-12T03:00:05Z"},
        {"id": 102, "created_at": "2026-11-12T03:00:10Z"},
    ]
}
_COVERAGE_REUSE_OUTCOME = {
    "repository": _REPOSITORY,
    "run_id": "42",
    "job_id": "check-coverage",
    "duration_ms": 1234,
    "outcome": "reused",
}


def _exporter() -> ModuleType:
    """Import the module only after the genuine Red assertion about its absence."""
    assert _MODULE_PATH.is_file()
    return importlib.import_module(_MODULE)


def _span_attributes(*, span: dict[str, Any]) -> dict[str, str]:
    """Flatten OTLP attributes for the exact schema comparison below."""
    return {
        attribute["key"]: next(iter(attribute["value"].values()))
        for attribute in span["attributes"]
    }


def test_the_budgeted_log_read_exports_the_consumer_reuse_outcome(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The export reads the script's structured log line for the coverage consumer."""
    exporter = _exporter()
    run = deepcopy(_RUN)
    run["jobs"] = [
        {
            "databaseId": 104,
            "name": "check-coverage",
            "conclusion": "success",
            "startedAt": "2026-11-12T03:01:10Z",
            "completedAt": "2026-11-12T03:02:30Z",
        }
    ]
    responses = iter(
        [
            GhRead(returncode=0, stdout=json.dumps(run), stderr=""),
            GhRead(
                returncode=0,
                stdout=json.dumps({"jobs": [{"id": 104, "created_at": "2026-11-12T03:00:10Z"}]}),
                stderr="",
            ),
            GhRead(
                returncode=0,
                stdout=f"before\nLIVESPEC_COVERAGE_REUSE_OUTCOME {json.dumps(_COVERAGE_REUSE_OUTCOME)}\nafter\n",
                stderr="",
            ),
        ]
    )

    def _read(*, args: list[str], **kwargs: object) -> GhRead:
        _ = args, kwargs
        return next(responses)

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

    monkeypatch.setattr(exporter, "gh_read", _read)
    monkeypatch.setattr("http.client.HTTPSConnection", _connection)
    assert (
        exporter.main(argv=["--repo", _REPOSITORY, "--run-id", "42", "--ingest-key", "test-key"])
        == 0
    )

    spans = posted[0]["resourceSpans"][0]["scopeSpans"][0]["spans"]
    coverage_span = next(span for span in spans if span["name"] == "ci.job.check-coverage")
    assert _span_attributes(span=coverage_span) == {
        "repo": _REPOSITORY,
        "ci.run_id": "42",
        "ci.job.id": "104",
        "ci.job.name": "check-coverage",
        "ci.job.conclusion": "success",
        "ci.job.queue_ms": "60000",
        "ci.coverage_reuse.repository": _REPOSITORY,
        "ci.coverage_reuse.run_id": "42",
        "ci.coverage_reuse.job_id": "check-coverage",
        "ci.coverage_reuse.duration_ms": "1234",
        "ci.coverage_reuse.outcome": "reused",
    }


@pytest.mark.parametrize(
    "log_response",
    [
        GhRead(returncode=0, stdout="LIVESPEC_COVERAGE_REUSE_OUTCOME {not-json}\n", stderr=""),
        GhRead(returncode=0, stdout="no coverage outcome\n", stderr=""),
        GhRead(returncode=0, stdout="LIVESPEC_COVERAGE_REUSE_OUTCOME true\n", stderr=""),
        GhRead(
            returncode=0,
            stdout='LIVESPEC_COVERAGE_REUSE_OUTCOME {"unexpected":"shape"}\n',
            stderr="",
        ),
        GhRead(
            returncode=0,
            stdout=(
                "LIVESPEC_COVERAGE_REUSE_OUTCOME "
                '{"repository":"thewoolleyman/livespec-dev-tooling","run_id":"42",'
                '"job_id":"check-coverage","duration_ms":-1,"outcome":"reused"}\n'
            ),
            stderr="",
        ),
        GhRead(returncode=1, stdout="", stderr="logs unavailable"),
    ],
)
def test_the_export_refuses_an_unreadable_or_invalid_coverage_reuse_record(
    *, monkeypatch: pytest.MonkeyPatch, log_response: GhRead
) -> None:
    """A coverage consumer cannot silently lose its one required detector record."""
    exporter = _exporter()
    run = deepcopy(_RUN)
    run["jobs"] = [
        {
            "databaseId": 104,
            "name": "check-coverage",
            "conclusion": "success",
            "startedAt": "2026-11-12T03:01:10Z",
            "completedAt": "2026-11-12T03:02:30Z",
        }
    ]
    responses = iter(
        [
            GhRead(returncode=0, stdout=json.dumps(run), stderr=""),
            GhRead(
                returncode=0,
                stdout=json.dumps({"jobs": [{"id": 104, "created_at": "2026-11-12T03:00:10Z"}]}),
                stderr="",
            ),
            log_response,
        ]
    )

    def _read(*, args: list[str], **kwargs: object) -> GhRead:
        _ = args, kwargs
        return next(responses)

    monkeypatch.setattr(exporter, "gh_read", _read)

    assert (
        exporter.main(argv=["--repo", _REPOSITORY, "--run-id", "42", "--ingest-key", "test-key"])
        == 1
    )


def test_recorded_github_documents_emit_the_shell_exporters_run_and_job_spans(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Recorded GitHub data emits the former exporter's spans with identical fields."""
    exporter = _exporter()
    run_path = tmp_path / "run.json"
    jobs_path = tmp_path / "jobs.json"
    _ = run_path.write_text(json.dumps(_RUN), encoding="utf-8")
    _ = jobs_path.write_text(json.dumps(_JOBS), encoding="utf-8")
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
            assert headers == {
                "x-honeycomb-team": "test-key",
                "Content-Type": "application/json",
            }
            posted.append(json.loads(body))

        def getresponse(self) -> _Response:
            return _Response()

        def close(self) -> None:
            return None

    def _connection(host: str, timeout: float) -> _Connection:
        return _Connection(host=host, timeout=timeout)

    monkeypatch.setattr("http.client.HTTPSConnection", _connection)

    assert (
        exporter.main(
            argv=[
                "--repo",
                _REPOSITORY,
                "--run-id",
                str(_RUN_ID),
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

    spans = posted[0]["resourceSpans"][0]["scopeSpans"][0]["spans"]
    assert [span["name"] for span in spans] == [
        "ci.run",
        "ci.job.check-python",
        "ci.job.check-metadata",
    ]
    assert _span_attributes(span=spans[0]) == {
        "repo": _REPOSITORY,
        "ci.run_id": "42",
        "ci.conclusion": "success",
        "ci.title": "publish telemetry",
        "git.commit.sha": "a" * 40,
        "git.branch": "master",
        "ci.event": "push",
    }
    assert [_span_attributes(span=span) for span in spans[1:]] == [
        {
            "repo": _REPOSITORY,
            "ci.run_id": "42",
            "ci.job.name": "check-python",
            "ci.job.conclusion": "success",
            "ci.job.queue_ms": "60000",
        },
        {
            "repo": _REPOSITORY,
            "ci.run_id": "42",
            "ci.job.name": "check-metadata",
            "ci.job.conclusion": "failure",
            "ci.job.queue_ms": "60000",
        },
    ]
    assert spans[0]["status"] == {"code": 1}
    assert [span["status"] for span in spans[1:]] == [{"code": 1}, {"code": 2}]
