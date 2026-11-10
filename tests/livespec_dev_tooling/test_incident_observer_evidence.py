"""The observer refuses an arm until its exact head tree carries complete, disposed evidence."""

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-4aksht
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from livespec_dev_tooling._incident_observer_types import ObserverArm
from livespec_dev_tooling.incident_focused_admission import (
    EVIDENCE_ROW,
    EvidenceSubject,
    disposition_receipt,
    evidence_receipt_id,
)
from livespec_dev_tooling.incident_observer_evidence import FocusedEvidenceGate

_HEAD = "c" * 40
_TREE = "f" * 40
_CHECKSUM = "sha256:" + "1" * 64
_ARM = ObserverArm(
    repository="owner/repo",
    incident_item_id="incident-1",
    attempt_id="repair-1",
    operation_id="operation-1",
    generation=4,
    owner="owner",
    phase="repair",
    pr_number=55,
    base_sha="e" * 40,
    head_sha=_HEAD,
    required_jobs=("coverage",),
    controller_release="v1.169.0",
    controller_revision="b" * 40,
    authority_receipt=b"{}",
)
_SUBJECT = EvidenceSubject(
    repository="owner/repo",
    item="incident-1",
    attempt="repair-1",
    operation="operation-1",
    generation=4,
    head=_HEAD,
    tree=_TREE,
)
_MEMBER = "coverage incomplete: src/widget.py"


def _record(**changes: Any) -> dict[str, Any]:
    record: dict[str, Any] = {
        "mode": "expedited-repair",
        "scope": "focused-tests-and-touched-files",
        "tree_hash": _TREE,
        "identity": {
            "incident_item_id": "incident-1",
            "attempt_id": "repair-1",
            "repository": "owner/repo",
            "head_sha": _HEAD,
            "operation_id": "operation-1",
        },
        "paths": {"src/widget.py": "executable"},
        "selection": {"tests": [], "deferred_tests": {}},
        "manual": {"procedure": "p", "expected": "e", "observed": "e", "outcome": "passed"},
        "tests": {"returncode": 0, "timed_out": False},
        "coverage_command": {"returncode": 0, "timed_out": False},
        "coverage": {"src/widget.py": {"summary": {"percent_covered": 100}}},
        "risks": [],
        "outcome": "passed",
    }
    record.update(changes)
    return record


_INCOMPLETE = _record(
    coverage={"src/widget.py": {"summary": {"percent_covered": 50}}},
    risks=[_MEMBER],
    outcome="incomplete",
)


def _evidence(*, slot: int, record: dict[str, Any]) -> dict[str, Any]:
    return {
        "receipt_id": evidence_receipt_id(subject=_SUBJECT, slot=slot),
        "hook": "pre-push",
        "tree": _TREE,
        "mode": "expedited-repair",
        "evidence_kind": "expedited-local-partial",
        "exit_status": 0,
        "results": [{"name": EVIDENCE_ROW, "status": "passed", "output": json.dumps(record)}],
    }


def _dispose(*, slot: int, member: str = _MEMBER) -> dict[str, Any]:
    return disposition_receipt(
        evidence_receipt_id=evidence_receipt_id(subject=_SUBJECT, slot=slot),
        evidence_checksum=_CHECKSUM,
        member=member,
        disposition="risk accepted for the incident",
        tree=_TREE,
    )


@dataclass
class _Authority:
    receipts: dict[str, dict[str, Any]] = field(default_factory=dict)
    calls: list[list[str]] = field(default_factory=list)
    answer: dict[str, Any] | None = None
    returncode: int = 0

    def add(self, receipt: dict[str, Any]) -> None:
        self.receipts[receipt["receipt_id"]] = receipt

    def __call__(self, argv: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        self.calls.append(argv)
        receipt_id = argv[argv.index("--receipt-id") + 1]
        receipt = self.receipts.get(receipt_id)
        result = self.answer or {
            "status": "absent" if receipt is None else "recorded",
            "receipt_id": receipt_id,
            "committed_token_id": "committed",
            "current_token_id": "current",
            "checksum": None if receipt is None else _CHECKSUM,
            "receipt": receipt,
        }
        if self.returncode:
            result = {"code": "incident-receipt-unavailable", "detail": "ledger outage"}
        reply = {
            "schema": 1,
            "status": "refused" if self.returncode else "verified",
            "authorizes_current_effects": False,
            "normal_factory_proof": False,
            "result": result,
        }
        return subprocess.CompletedProcess(argv, self.returncode, json.dumps(reply), "")


def _forge(path: str) -> object:
    return {f"repos/owner/repo/git/commits/{_HEAD}": {"sha": _HEAD, "tree": {"sha": _TREE}}}.get(
        path
    )


@pytest.fixture
def authority(monkeypatch: pytest.MonkeyPatch) -> _Authority:
    fake = _Authority()
    monkeypatch.setattr(subprocess, "run", fake)
    return fake


def _gate(*, read: Any = _forge, approved: bool = True) -> FocusedEvidenceGate:
    return FocusedEvidenceGate(
        command=("/installed/reader",),
        repo=Path("/protected/repo"),
        release="v0.304.0",
        installed_reader_approved=lambda release, command: approved
        and (release, command) == ("v0.304.0", ("/installed/reader",)),
        read=read,
    )


def test_no_record_for_the_head_tree_refuses_absent_naming_the_tree(
    authority: _Authority,
) -> None:
    refusal = _gate()(_ARM)
    assert refusal is not None
    assert refusal.startswith("incident-focused-evidence-absent:")
    assert _TREE in refusal
    assert len(authority.calls) == 1
    argv = authority.calls[0]
    assert argv[:2] == ["/installed/reader", "read-local-gates"]
    flags = dict(zip(argv[2::2], argv[3::2], strict=True))
    assert flags == {
        "--repo": "/protected/repo",
        "--repository": "owner/repo",
        "--item": "incident-1",
        "--attempt": "repair-1",
        "--phase": "repair",
        "--operation": "operation-1",
        "--generation": "4",
        "--owner": "owner",
        "--receipt-id": evidence_receipt_id(subject=_SUBJECT, slot=0),
    }


def test_a_complete_record_admits(authority: _Authority) -> None:
    authority.add(_evidence(slot=0, record=_record()))
    assert _gate()(_ARM) is None
    assert len(authority.calls) == 2


@pytest.mark.parametrize(
    ("changes", "member"),
    [
        ({"manual": None}, "manual reproduction"),
        ({"coverage": None}, "touched-file coverage result"),
    ],
)
def test_a_record_lacking_a_required_member_refuses_naming_it(
    authority: _Authority, changes: dict[str, Any], member: str
) -> None:
    authority.add(_evidence(slot=0, record=_record(**changes)))
    refusal = _gate()(_ARM)
    assert refusal is not None
    assert refusal.startswith("incident-focused-evidence-member-missing:")
    assert member in refusal


def test_an_undisposed_incomplete_member_refuses_until_its_disposition_is_recorded(
    authority: _Authority,
) -> None:
    authority.add(_evidence(slot=0, record=_INCOMPLETE))
    refusal = _gate()(_ARM)
    assert refusal is not None
    assert refusal.startswith("incident-focused-evidence-undisposed:")
    assert _MEMBER in refusal
    authority.add(_dispose(slot=0))
    assert _gate()(_ARM) is None


@pytest.mark.parametrize(
    "changes",
    [
        {"tests": {"returncode": 1, "timed_out": False}, "outcome": "failed"},
        {
            "manual": {"procedure": "p", "expected": "e", "observed": "x", "outcome": "failed"},
            "outcome": "failed",
        },
    ],
)
def test_a_failed_member_refuses_whatever_disposition_it_carries(
    authority: _Authority, changes: dict[str, Any]
) -> None:
    authority.add(_evidence(slot=0, record=_record(**changes, risks=[_MEMBER])))
    authority.add(_dispose(slot=0))
    authority.add(_dispose(slot=0, member="focused test"))
    authority.add(_dispose(slot=0, member="manual reproduction"))
    refusal = _gate()(_ARM)
    assert refusal is not None
    assert refusal.startswith("incident-focused-evidence-failed:")


def test_a_failed_earlier_record_on_the_same_tree_still_refuses(authority: _Authority) -> None:
    failing = _record(tests={"returncode": 1, "timed_out": False}, outcome="failed")
    authority.add(_evidence(slot=0, record=failing))
    authority.add(_evidence(slot=1, record=_record()))
    refusal = _gate()(_ARM)
    assert refusal is not None
    assert refusal.startswith("incident-focused-evidence-failed: focused test")


def test_the_latest_record_governs_completeness(authority: _Authority) -> None:
    authority.add(_evidence(slot=0, record=_INCOMPLETE))
    authority.add(_evidence(slot=1, record=_record()))
    assert _gate()(_ARM) is None


def test_every_slot_is_read_when_all_are_recorded(authority: _Authority) -> None:
    for slot in range(8):
        authority.add(_evidence(slot=slot, record=_record()))
    assert _gate()(_ARM) is None
    assert len(authority.calls) == 8


@pytest.mark.parametrize(
    "commit",
    [
        None,
        {"sha": "d" * 40, "tree": {"sha": _TREE}},
        {"sha": _HEAD, "tree": "not a mapping"},
        {"sha": _HEAD, "tree": {"sha": "not-a-sha"}},
    ],
)
def test_an_unreadable_head_tree_refuses_unavailable(authority: _Authority, commit: object) -> None:
    def read(_path: str) -> object:
        return commit

    refusal = _gate(read=read)(_ARM)
    assert refusal is not None
    assert refusal.startswith("incident-focused-evidence-unavailable:")
    assert authority.calls == []


def test_an_unapproved_reader_refuses_without_reading(authority: _Authority) -> None:
    refusal = _gate(approved=False)(_ARM)
    assert refusal is not None
    assert refusal.startswith("incident-focused-evidence-unavailable:")
    assert authority.calls == []


def test_an_authority_refusal_refuses_unavailable(authority: _Authority) -> None:
    authority.returncode = 78
    refusal = _gate()(_ARM)
    assert refusal is not None
    assert refusal.startswith("incident-focused-evidence-unavailable:")
    assert "incident-receipt-unavailable" in refusal


@pytest.mark.parametrize(
    "answer",
    [
        {"status": "absent", "receipt_id": "other", "receipt": None, "checksum": None},
        {"status": "absent", "receipt_id": "SLOT", "receipt": {}, "checksum": None},
        {"status": "unknown", "receipt_id": "SLOT", "receipt": None, "checksum": None},
        {"status": "recorded", "receipt_id": "SLOT", "receipt": None, "checksum": _CHECKSUM},
        {"status": "recorded", "receipt_id": "SLOT", "receipt": {"receipt_id": "x"}},
        {"status": "recorded", "receipt_id": "SLOT", "receipt": {"receipt_id": "SLOT"}},
        {
            "status": "recorded",
            "receipt_id": "SLOT",
            "receipt": {"receipt_id": "SLOT"},
            "checksum": "md5:1",
        },
    ],
)
def test_a_malformed_lookup_refuses_unavailable(
    authority: _Authority, answer: dict[str, Any]
) -> None:
    slot = evidence_receipt_id(subject=_SUBJECT, slot=0)
    authority.answer = json.loads(json.dumps(answer).replace("SLOT", slot))
    refusal = _gate()(_ARM)
    assert refusal is not None
    assert refusal.startswith("incident-focused-evidence-unavailable:")


def test_a_record_that_does_not_bind_the_tree_refuses_unavailable(authority: _Authority) -> None:
    authority.add(_evidence(slot=0, record=_record(tree_hash="a" * 40)))
    refusal = _gate()(_ARM)
    assert refusal is not None
    assert refusal.startswith("incident-focused-evidence-unavailable:")


def test_a_disposition_bound_to_other_bytes_refuses_unavailable(authority: _Authority) -> None:
    authority.add(_evidence(slot=0, record=_INCOMPLETE))
    stale = _dispose(slot=0)
    stale["tree"] = "a" * 40
    authority.add(stale)
    refusal = _gate()(_ARM)
    assert refusal is not None
    assert refusal.startswith("incident-focused-evidence-unavailable:")
