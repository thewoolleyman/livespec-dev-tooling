"""The collector reads complete original-attempt pages and source, never reruns."""

import base64
import hashlib
import json
import subprocess
from typing import Any

import pytest

from livespec_dev_tooling._incident_run_types import EvidenceRefusal, RunSnapshot
from livespec_dev_tooling.budgeted_gh import GhRead
from livespec_dev_tooling.incident_run_forge import ForgeRunReader
from tests.livespec_dev_tooling.test_incident_run_evidence import original

SOURCE = b"jobs:\n  test:\n    runs-on: ubuntu-latest\n"
DIGEST = hashlib.sha256(SOURCE).hexdigest()


def metadata(**changes: Any) -> dict[str, object]:
    return {
        "id": 42,
        "run_attempt": 1,
        "head_sha": "a" * 40,
        "status": "completed",
        "repository": {"full_name": "owner/repo"},
        "path": ".github/workflows/ci.yml",
        **changes,
    }


def raw_job(**changes: Any) -> dict[str, object]:
    return {
        "id": 10,
        "name": "test",
        "status": "completed",
        "conclusion": "failure",
        "html_url": "https://forge.invalid/job/10",
        **changes,
    }


def source() -> dict[str, object]:
    return {"encoding": "base64", "content": base64.b64encode(SOURCE).decode()}


def provider(
    *, monkeypatch: pytest.MonkeyPatch, responses: list[object], **options: Any
) -> tuple[ForgeRunReader, list[list[str]]]:
    calls: list[list[str]] = []

    def run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert kwargs["check"] is True
        assert 0 < kwargs["timeout"] <= 10
        assert not any(word in argv for word in ("POST", "cancel", "rerun", "DELETE"))
        calls.append(argv)
        value = responses.pop(0)
        if isinstance(value, BaseException):
            raise value
        return subprocess.CompletedProcess(argv, 0, stdout=json.dumps(value))

    monkeypatch.setattr("livespec_dev_tooling.incident_run_forge.subprocess.run", run)
    return ForgeRunReader(command=("controlled-forge-provider",), **options), calls


def test_reads_original_attempt_and_workflow_revision_with_complete_pagination(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reader, calls = provider(
        monkeypatch=monkeypatch,
        responses=[
            metadata(),
            source(),
            {"total_count": 2, "jobs": [raw_job()]},
            {"total_count": 2, "jobs": [raw_job(id=11, name="coverage", conclusion="skipped")]},
        ],
    )
    result = reader(original(graph_digest=DIGEST))
    assert isinstance(result, RunSnapshot)
    assert result.complete_listing and len(result.jobs) == 2
    assert calls[0][-1].endswith("/runs/42/attempts/1")
    assert calls[1][-1].endswith("?ref=" + "a" * 40)
    assert all("/attempts/1/jobs?" in argv[-1] for argv in calls[2:])


@pytest.mark.parametrize("options", [{"command": ()}, {"budget_seconds": 0}, {"max_pages": 0}])
def test_invalid_budget_refuses(options: dict[str, Any]) -> None:
    assert isinstance(ForgeRunReader(**options)(original()), EvidenceRefusal)


@pytest.mark.parametrize(
    "changes",
    [
        {"id": 43},
        {"run_attempt": 2},
        {"head_sha": "other"},
        {"repository": {}},
        {"path": "another.yml"},
        {"status": None},
    ],
)
def test_metadata_identity_cannot_shift(
    monkeypatch: pytest.MonkeyPatch, changes: dict[str, Any]
) -> None:
    reader, _ = provider(monkeypatch=monkeypatch, responses=[metadata(**changes)])
    assert isinstance(reader(original()), EvidenceRefusal)


@pytest.mark.parametrize(
    "responses",
    [
        [OSError("offline")],
        [metadata(), OSError("offline")],
        [metadata(), []],
        [metadata(), {"encoding": "base64", "content": "!!!!"}],
        [metadata(), source()],
    ],
)
def test_unavailable_or_mismatched_source_refuses(
    monkeypatch: pytest.MonkeyPatch, responses: list[object]
) -> None:
    reader, _ = provider(monkeypatch=monkeypatch, responses=responses)
    assert isinstance(reader(original(graph_digest="wrong")), EvidenceRefusal)


@pytest.mark.parametrize(
    ("pages", "options"),
    [
        ([OSError("offline")], {}),
        ([{}], {}),
        ([{"total_count": -1, "jobs": []}], {}),
        ([{"total_count": 1, "jobs": None}], {}),
        ([{"total_count": 2, "jobs": [raw_job()]}, {"total_count": 3, "jobs": []}], {}),
        ([{"total_count": 1, "jobs": []}], {}),
        ([{"total_count": 0, "jobs": [raw_job()]}], {}),
        ([{"total_count": 2, "jobs": [raw_job()]}], {"max_pages": 1}),
        ([{"total_count": 1, "jobs": [raw_job(id=False)]}], {}),
        ([{"total_count": 1, "jobs": [raw_job(conclusion=1)]}], {}),
        ([{"total_count": 1, "jobs": [raw_job(name="")]}], {}),
    ],
)
def test_incomplete_or_bad_pagination_refuses(
    monkeypatch: pytest.MonkeyPatch, pages: list[object], options: dict[str, Any]
) -> None:
    reader, _ = provider(
        monkeypatch=monkeypatch, responses=[metadata(), source(), *pages], **options
    )
    assert isinstance(reader(original(graph_digest=DIGEST)), EvidenceRefusal)


def test_provider_budget_is_monotonic_without_sleep_or_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reader, calls = provider(monkeypatch=monkeypatch, responses=[])
    clock = iter([0, 46])
    monkeypatch.setattr(
        "livespec_dev_tooling.incident_run_forge.time.monotonic", lambda: next(clock)
    )
    assert isinstance(reader(original()), EvidenceRefusal)
    assert calls == []


def test_oversized_response_is_not_silently_truncated(monkeypatch: pytest.MonkeyPatch) -> None:
    reader, _ = provider(monkeypatch=monkeypatch, responses=["x" * 4_000_001])
    assert isinstance(reader(original()), EvidenceRefusal)


def test_zero_job_run_is_a_complete_empty_observation(monkeypatch: pytest.MonkeyPatch) -> None:
    reader, _ = provider(
        monkeypatch=monkeypatch, responses=[metadata(), source(), {"total_count": 0, "jobs": []}]
    )
    result = reader(original(graph_digest=DIGEST))
    assert isinstance(result, RunSnapshot) and result.jobs == ()


@pytest.mark.parametrize("failed", [False, True])
def test_default_transport_uses_budgeted_reads_and_refuses_failed_requests(
    monkeypatch: pytest.MonkeyPatch, *, failed: bool
) -> None:
    responses = [metadata(), source(), {"total_count": 0, "jobs": []}]
    calls: list[list[str]] = []

    def read(*, args: list[str], timeout: float) -> GhRead:
        calls.append(args)
        assert args[0] == "api" and 0 < timeout <= 10
        return GhRead(
            returncode=1 if failed else 0,
            stdout=json.dumps(responses.pop(0)),
            stderr="denied" if failed else "",
        )

    monkeypatch.setattr("livespec_dev_tooling.incident_run_forge.gh_read", read)
    result = ForgeRunReader()(original(graph_digest=DIGEST))
    assert isinstance(result, EvidenceRefusal if failed else RunSnapshot)
    assert len(calls) == (1 if failed else 3)
