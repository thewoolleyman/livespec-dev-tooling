"""Evidence survives canonical outages without becoming a local attempt store."""

import fcntl
import hashlib
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from livespec_dev_tooling._incident_observer_store import load_record, repository_lock, save_record
from livespec_dev_tooling._incident_run_types import EvidenceRefusal, RunEvidence
from livespec_dev_tooling.incident_run_collector import CanonicalRunAdapter, OriginalRunCollector
from tests.livespec_dev_tooling.test_incident_run_evidence import (
    evidence,
    original,
    proposal,
    snapshot,
)


def fail(*_args: object) -> Any:
    raise OSError("canonical unavailable")


def collector(*, directory: Path, **changes: Any) -> OriginalRunCollector:
    adapter = CanonicalRunAdapter(
        authorize=lambda _original: True,
        record=lambda _evidence, _digest: "evidence-receipt",
        correct=lambda _proposal, _digest: "attempt-transition-receipt",
    )
    return OriginalRunCollector(
        directory=directory,
        read=lambda _original: snapshot(),
        canonical=replace(adapter, **changes),
    )


def test_retains_original_evidence_and_foreign_observer_fields_without_network_under_lock(
    tmp_path: Path,
) -> None:
    with repository_lock(directory=tmp_path, repository="owner/repo") as path:
        save_record(path=path, record={"foreign_observer_intent": "retained"})
    owner = collector(directory=tmp_path)
    collected = owner.collect(original=original(), continuation_id="original-tree-proof-42")
    assert isinstance(collected, RunEvidence)
    # A replacement observation of the SAME original run remains available.
    assert owner.collect(original=original(), continuation_id="original-tree-proof-42") == collected
    with repository_lock(directory=tmp_path, repository="owner/repo") as path:
        stored = load_record(path=path)
    assert stored["foreign_observer_intent"] == "retained"
    assert len(stored["original_run_evidence"]) == 1
    assert "phase" not in stored and "attempts" not in stored
    assert (
        owner.propose_correction(evidence=collected, proposal=proposal(collected=collected))
        == "attempt-transition-receipt"
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"authorize": lambda _original: False},
        {"authorize": fail},
        {"record": fail},
        {"record": lambda _evidence, _digest: ""},
        {"record": lambda _evidence, _digest: True},
    ],
)
def test_canonical_unavailability_refuses_without_losing_owned_debt(
    tmp_path: Path, changes: dict[str, Any]
) -> None:
    owner = collector(directory=tmp_path, **changes)
    assert isinstance(
        owner.collect(original=original(), continuation_id="owned-proof"), EvidenceRefusal
    )
    if "record" in changes:
        stored = json.loads(next(tmp_path.glob("*.json")).read_text())
        assert stored["original_run_evidence"]


def test_provider_unavailable_refusal_and_bad_graph_leave_no_claim(tmp_path: Path) -> None:
    owner = collector(directory=tmp_path)
    for read in [
        fail,
        lambda _original: EvidenceRefusal(code="offline", detail="provider"),
        lambda _original: snapshot(complete_listing=False),
    ]:
        assert isinstance(
            replace(owner, read=read).collect(original=original(), continuation_id="owned"),
            EvidenceRefusal,
        )
    assert list(tmp_path.iterdir()) == []


def test_storage_errors_and_corrupt_receipts_refuse(tmp_path: Path) -> None:
    owner = collector(directory=tmp_path)
    with repository_lock(directory=tmp_path, repository="owner/repo") as path:
        save_record(path=path, record={"original_run_evidence": []})
    assert isinstance(owner.collect(original=original(), continuation_id="owned"), EvidenceRefusal)
    blocked = tmp_path / "file"
    blocked.write_text("not a directory")
    assert isinstance(
        replace(owner, directory=blocked).collect(original=original(), continuation_id="owned"),
        EvidenceRefusal,
    )


@pytest.mark.parametrize(
    "correct", [fail, lambda _proposal, _digest: "", lambda _proposal, _digest: None]
)
def test_canonical_correction_failure_never_creates_local_attempt(
    tmp_path: Path, correct: Any
) -> None:
    owner = collector(directory=tmp_path, correct=correct)
    collected = evidence()
    assert isinstance(
        owner.propose_correction(evidence=collected, proposal=proposal(collected=collected)),
        EvidenceRefusal,
    )
    assert list(tmp_path.iterdir()) == []


def test_invalid_proposal_does_not_reach_canonical_writer(tmp_path: Path) -> None:
    owner = collector(directory=tmp_path, correct=lambda *_args: pytest.fail("must not publish"))
    collected = evidence()
    assert isinstance(
        owner.propose_correction(
            evidence=collected, proposal=proposal(collected=collected, next_attempt_id="attempt-1")
        ),
        EvidenceRefusal,
    )


def test_corrupt_existing_immutable_evidence_cannot_be_overwritten(tmp_path: Path) -> None:
    owner = collector(directory=tmp_path)
    assert isinstance(owner.collect(original=original(), continuation_id="owned"), RunEvidence)
    with repository_lock(directory=tmp_path, repository="owner/repo") as path:
        record = load_record(path=path)
        observations = record["original_run_evidence"]
        assert isinstance(observations, dict)
        key = next(iter(observations))
        observations[key] = {"corrupted": True}
        save_record(path=path, record=record)
    result = owner.collect(original=original(), continuation_id="owned")
    assert isinstance(result, EvidenceRefusal)
    assert "persistence" in result.detail


def test_provider_and_canonical_rpc_never_own_the_recovery_lock(tmp_path: Path) -> None:
    lock_path = tmp_path / (hashlib.sha256(b"owner/repo").hexdigest() + ".lock")

    def assert_unlocked() -> None:
        with lock_path.open("a+b") as stream:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    def read(_original: object) -> Any:
        assert_unlocked()
        return snapshot()

    def record(_evidence: object, _digest: str) -> str:
        assert_unlocked()
        return "canonical-evidence"

    owner = replace(collector(directory=tmp_path, record=record), read=read)
    assert isinstance(owner.collect(original=original(), continuation_id="owned"), RunEvidence)
