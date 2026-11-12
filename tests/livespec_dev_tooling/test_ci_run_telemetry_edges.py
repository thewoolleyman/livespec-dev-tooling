"""Edge contracts for the shared CI run telemetry exporter."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from types import ModuleType

import pytest

from livespec_dev_tooling.budgeted_gh import GhRead

__all__: list[str] = []

_MODULE = "livespec_dev_tooling.ci_run_telemetry"
_MODULE_PATH = Path(__file__).resolve().parents[2] / "livespec_dev_tooling" / "ci_run_telemetry.py"
_REPOSITORY = "thewoolleyman/livespec-dev-tooling"
_RUN_ID = 42


def _exporter() -> ModuleType:
    """Import only after a genuine assertion that the new module exists."""
    assert _MODULE_PATH.is_file()
    return importlib.import_module(_MODULE)


def test_the_cli_rejects_incomplete_inputs_and_reads_paginated_jobs(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Missing inputs fail closed while the GitHub client flattens jobs pages."""
    exporter = _exporter()
    monkeypatch.delenv("REPO", raising=False)
    monkeypatch.delenv("RUN_ID", raising=False)
    monkeypatch.delenv("HONEYCOMB_GITHUB_CI_INGEST_KEY_LIVESPEC", raising=False)
    assert exporter.main(argv=[]) == 2
    assert (
        exporter.main(
            argv=[
                "--repo",
                _REPOSITORY,
                "--run-id",
                str(_RUN_ID),
                "--ingest-key",
                "test-key",
                "--run-json",
                str(tmp_path / "run.json"),
            ]
        )
        == 2
    )

    def _failed_read(*, args: list[str], **kwargs: object) -> GhRead:
        _ = args, kwargs
        return GhRead(returncode=1, stdout="", stderr="not authorised")

    monkeypatch.setattr(exporter, "gh_read", _failed_read)
    assert (
        exporter.main(
            argv=["--repo", _REPOSITORY, "--run-id", str(_RUN_ID), "--ingest-key", "test-key"]
        )
        == 1
    )

    responses = iter(
        [
            GhRead(
                returncode=0,
                stdout=json.dumps(
                    {
                        "createdAt": "2026-11-12T03:00:00",
                        "updatedAt": "2026-11-12T03:03:00",
                        "jobs": [
                            {
                                "databaseId": 101,
                                "name": "check",
                                "startedAt": "2026-11-12T03:01:00",
                                "completedAt": "2026-11-12T03:02:00",
                            },
                            {
                                "databaseId": 102,
                                "name": "no-created-at",
                                "startedAt": "2026-11-12T03:01:00",
                                "completedAt": "2026-11-12T03:02:00",
                            },
                        ],
                    }
                ),
                stderr="",
            ),
            GhRead(
                returncode=0,
                stdout=json.dumps({"jobs": [{"id": 101, "created_at": "2026-11-12T03:02:00"}]}),
                stderr="",
            ),
        ]
    )

    class _Response:
        status = 200

        def read(self) -> bytes:
            return b'{"partialSuccess":{"rejectedSpans":"1"}}'

    class _Connection:
        def __init__(self, *, host: str, timeout: float) -> None:
            assert host == "api.honeycomb.io"
            assert timeout == 30.0

        def request(self, method: str, url: str, body: str, headers: dict[str, str]) -> None:
            assert method == "POST"
            assert url == "/v1/traces"
            assert body
            assert headers["x-honeycomb-team"] == "test-key"

        def getresponse(self) -> _Response:
            return _Response()

        def close(self) -> None:
            return None

    def _connection(host: str, timeout: float) -> _Connection:
        return _Connection(host=host, timeout=timeout)

    def _read_response(*, args: list[str], **kwargs: object) -> GhRead:
        _ = args, kwargs
        return next(responses)

    monkeypatch.setattr(exporter, "gh_read", _read_response)
    monkeypatch.setattr("http.client.HTTPSConnection", _connection)
    assert (
        exporter.main(
            argv=["--repo", _REPOSITORY, "--run-id", str(_RUN_ID), "--ingest-key", "test-key"]
        )
        == 1
    )
