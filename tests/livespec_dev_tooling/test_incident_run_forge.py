"""The collector reads complete original-attempt pages and source, never reruns."""

import base64
import hashlib
from typing import Any

import pytest

from livespec_dev_tooling._incident_run_types import EvidenceRefusal, RunSnapshot
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


def provider(*, responses: list[object], **options: Any) -> tuple[ForgeRunReader, list[str]]:
    calls: list[str] = []

    def read(path: str) -> object:
        calls.append(path)
        return responses.pop(0)

    return ForgeRunReader(read=read, **options), calls


def test_reads_original_attempt_and_workflow_revision_with_complete_pagination() -> None:
    reader, calls = provider(
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
    assert calls[0].endswith("/runs/42/attempts/1")
    assert calls[1].endswith("?ref=" + "a" * 40)
    assert all("/attempts/1/jobs?" in path for path in calls[2:])


@pytest.mark.parametrize("options", [{"budget_seconds": 0}, {"max_pages": 0}])
def test_invalid_budget_refuses(options: dict[str, Any]) -> None:
    assert isinstance(provider(responses=[], **options)[0](original()), EvidenceRefusal)


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
def test_metadata_identity_cannot_shift(changes: dict[str, Any]) -> None:
    reader, _ = provider(responses=[metadata(**changes)])
    assert isinstance(reader(original()), EvidenceRefusal)


@pytest.mark.parametrize(
    "responses",
    [
        [None],
        [metadata(), None],
        [metadata(), []],
        [metadata(), {"encoding": "base64", "content": "!!!!"}],
        [metadata(), source()],
    ],
)
def test_unavailable_or_mismatched_source_refuses(responses: list[object]) -> None:
    reader, _ = provider(responses=responses)
    assert isinstance(reader(original(graph_digest="wrong")), EvidenceRefusal)


@pytest.mark.parametrize(
    ("pages", "options"),
    [
        ([None], {}),
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
def test_incomplete_or_bad_pagination_refuses(pages: list[object], options: dict[str, Any]) -> None:
    reader, _ = provider(responses=[metadata(), source(), *pages], **options)
    assert isinstance(reader(original(graph_digest=DIGEST)), EvidenceRefusal)


def test_provider_budget_is_monotonic_without_sleep_or_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reader, calls = provider(responses=[])
    clock = iter([0, 46])
    monkeypatch.setattr(
        "livespec_dev_tooling.incident_run_forge.time.monotonic", lambda: next(clock)
    )
    assert isinstance(reader(original()), EvidenceRefusal)
    assert calls == []


def test_zero_job_run_is_a_complete_empty_observation() -> None:
    reader, _ = provider(responses=[metadata(), source(), {"total_count": 0, "jobs": []}])
    result = reader(original(graph_digest=DIGEST))
    assert isinstance(result, RunSnapshot) and result.jobs == ()
