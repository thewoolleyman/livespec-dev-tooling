"""The coverage-reuse record contract stays available to CI telemetry."""

from __future__ import annotations

import importlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

from livespec_dev_tooling.budgeted_gh import GhRead

__all__: list[str] = []

_MODULE = "livespec_dev_tooling.ci_coverage_reuse"
_REPO_ROOT = Path(__file__).resolve().parents[2]
_MODULE_PATH = _REPO_ROOT / "livespec_dev_tooling" / "ci_coverage_reuse.py"
_EXPORT_SCRIPT = _REPO_ROOT / ".github" / "scripts" / "export-ci-telemetry.sh"
_REPOSITORY = "thewoolleyman/livespec-dev-tooling"
_RECORD = {
    "repository": _REPOSITORY,
    "run_id": "42",
    "job_id": "check-coverage",
    "duration_ms": 1234,
    "outcome": "reused",
}
_RECORD_LINE = f"LIVESPEC_COVERAGE_REUSE_OUTCOME {json.dumps(_RECORD)}"
_FAKE_PYTHON = """#!/usr/bin/env bash
printf '%s\\n' "$*" > "$FAKE_DIR/argv"
printf '%s\\n' "$PYTHONPATH" > "$FAKE_DIR/pythonpath"
exit "$FAKE_STATUS"
"""


def _run_export(*, tmp_path: Path, status: int) -> tuple[int, str, str, str]:
    """Run the shell launcher against a fake python3 that records its call."""
    fake_dir = tmp_path / "fake"
    fake_bin = fake_dir / "bin"
    fake_bin.mkdir(parents=True)
    (fake_bin / "python3").write_text(_FAKE_PYTHON, encoding="utf-8")
    (fake_bin / "python3").chmod(0o755)
    completed = subprocess.run(
        ["bash", str(_EXPORT_SCRIPT)],
        check=False,
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env={
            **os.environ,
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "PYTHONPATH": "",
            "FAKE_DIR": str(fake_dir),
            "FAKE_STATUS": str(status),
            "REPO": _REPOSITORY,
            "RUN_ID": "42",
            "GH_TOKEN": "unused",
            "HONEYCOMB_GITHUB_CI_INGEST_KEY_LIVESPEC": "unused",
        },
    )
    return (
        completed.returncode,
        completed.stderr,
        (fake_dir / "argv").read_text(encoding="utf-8").strip(),
        (fake_dir / "pythonpath").read_text(encoding="utf-8").strip(),
    )


def test_the_reuse_contract_module_exports_the_coverage_consumer_identifier() -> None:
    """The cohesive contract module is importable after its genuine Red file assertion."""
    assert _MODULE_PATH.is_file()

    module = importlib.import_module(_MODULE)

    assert module.COVERAGE_CONSUMER_JOB_ID == "check-coverage"


def test_a_github_timestamp_prefixed_log_line_is_read_as_the_outcome() -> None:
    """GitHub prefixes every job-log line with a timestamp; the record is still found."""
    module = importlib.import_module(_MODULE)
    log = f"2026-11-12T03:02:29.1234567Z other\n2026-11-12T03:02:30.7654321Z {_RECORD_LINE}\n"

    outcome = module.coverage_reuse_outcome(
        repo=_REPOSITORY, run_id=42, job_name="check-coverage", log=log
    )

    assert outcome == _RECORD


def test_the_workflows_exporter_script_runs_the_python_exporter_from_this_checkout(
    *, tmp_path: Path
) -> None:
    """export-telemetry runs the script, so the script must run the module that reads the record."""
    status, _stderr, argv, pythonpath = _run_export(tmp_path=tmp_path, status=0)

    assert status == 0
    assert argv == "-m livespec_dev_tooling.ci_run_telemetry"
    assert pythonpath == str(_REPO_ROOT)


def test_the_workflows_exporter_script_fails_when_the_python_exporter_fails(
    *, tmp_path: Path
) -> None:
    """The closed-loop self-verification still reddens the job when the export is not accepted."""
    status, stderr, _argv, _pythonpath = _run_export(tmp_path=tmp_path, status=1)

    assert status == 1
    assert "::error::CI telemetry export to Honeycomb FAILED" in stderr


def test_a_consumer_job_that_never_ran_is_exported_without_reuse_attributes(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A skipped consumer has no log and no record, and must not stop the red run's export."""
    exporter = importlib.import_module("livespec_dev_tooling.ci_run_telemetry")
    run = {
        "databaseId": 42,
        "headSha": "a" * 40,
        "headBranch": "master",
        "event": "push",
        "displayTitle": "producer failed",
        "conclusion": "failure",
        "createdAt": "2026-11-12T03:00:00Z",
        "startedAt": "2026-11-12T03:01:00Z",
        "updatedAt": "2026-11-12T03:03:00Z",
        "jobs": [
            {
                "databaseId": 104,
                "name": "check-coverage",
                "conclusion": "skipped",
                "startedAt": "2026-11-12T03:01:10Z",
                "completedAt": "2026-11-12T03:01:10Z",
            }
        ],
    }
    reads: list[list[str]] = []

    def _read(*, args: list[str], **kwargs: object) -> GhRead:
        _ = kwargs
        reads.append(args)
        if args[:2] == ["run", "view"]:
            return GhRead(returncode=0, stdout=json.dumps(run), stderr="")
        return GhRead(returncode=0, stdout='{"jobs": []}\n', stderr="")

    posted: list[dict[str, Any]] = []

    class _Response:
        status = 200

        def read(self) -> bytes:
            return b'{"partialSuccess":{"rejectedSpans":"0"}}'

    class _Connection:
        def request(self, method: str, url: str, body: str, headers: dict[str, str]) -> None:
            _ = method, url, headers
            posted.append(json.loads(body))

        def getresponse(self) -> _Response:
            return _Response()

        def close(self) -> None:
            return None

    def _connection(host: str, timeout: float) -> _Connection:
        _ = host, timeout
        return _Connection()

    monkeypatch.setattr(exporter, "gh_read", _read)
    monkeypatch.setattr("http.client.HTTPSConnection", _connection)

    status = exporter.main(
        argv=["--repo", _REPOSITORY, "--run-id", "42", "--ingest-key", "test-key"]
    )

    assert status == 0
    assert not any(args[-1].endswith("/logs") for args in reads)
    spans = posted[0]["resourceSpans"][0]["scopeSpans"][0]["spans"]
    (span,) = [span for span in spans if span["name"] == "ci.job.check-coverage"]
    assert not any(a["key"].startswith("ci.coverage_reuse.") for a in span["attributes"])
