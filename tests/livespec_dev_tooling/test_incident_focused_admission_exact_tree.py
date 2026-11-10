"""A record that did not measure the exact head tree is never admitted, disposed or not.

The collector records `incident tree changed during collection` when the tree it
measured is no longer the head tree. Such a record is not evidence of this tree,
so it fails at `/arm` whatever disposition is recorded, and the disposition
entrance refuses to dispose it. A record naming another head is not judged.
"""

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-4aksht
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

from livespec_dev_tooling import incident_focused_disposition_entry as entry
from livespec_dev_tooling._incident_observer_types import ObserverArm
from livespec_dev_tooling.incident_focused_admission import (
    EVIDENCE_ROW,
    EvidenceSubject,
    disposition_receipt,
    evidence_receipt_id,
    review_record,
)
from livespec_dev_tooling.incident_hook_entry import QUERY_ENV
from livespec_dev_tooling.incident_hook_process import canonical
from livespec_dev_tooling.incident_observer_evidence import FocusedEvidenceGate

_HEAD = "c" * 40
_TREE = "f" * 40
_CHECKSUM = "sha256:" + "1" * 64
_CHANGED = "incident tree changed during collection"
_SUBJECT = EvidenceSubject(
    repository="owner/repo",
    item="incident-1",
    attempt="repair-1",
    operation="operation-1",
    generation=2,
    head=_HEAD,
    tree=_TREE,
)
_EVIDENCE = evidence_receipt_id(subject=_SUBJECT, slot=0)
_ARM = ObserverArm(
    repository="owner/repo",
    incident_item_id="incident-1",
    attempt_id="repair-1",
    operation_id="operation-1",
    generation=2,
    owner="operator:alice",
    phase="repair",
    pr_number=55,
    base_sha="e" * 40,
    head_sha=_HEAD,
    required_jobs=("coverage",),
    controller_release="v1.169.0",
    controller_revision="b" * 40,
    authority_receipt=b"{}",
)
_QUERY = {
    "repository": "owner/repo",
    "item": "incident-1",
    "attempt": "repair-1",
    "phase": "repair",
    "operation": "operation-1",
    "generation": 2,
    "owner": "operator:alice",
}


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
        "risks": [_CHANGED],
        "outcome": "incomplete",
    }
    record.update(changes)
    return record


def _evidence(*, record: dict[str, Any]) -> dict[str, Any]:
    return {
        "receipt_id": _EVIDENCE,
        "hook": "pre-push",
        "tree": _TREE,
        "mode": "expedited-repair",
        "evidence_kind": "expedited-local-partial",
        "exit_status": 1,
        "results": [{"name": EVIDENCE_ROW, "status": "failed", "output": json.dumps(record)}],
    }


def _lookup(receipt: dict[str, Any] | None, receipt_id: str) -> dict[str, Any]:
    return {
        "status": "absent" if receipt is None else "recorded",
        "receipt_id": receipt_id,
        "receipt": receipt,
        "checksum": None if receipt is None else _CHECKSUM,
    }


def test_a_changed_tree_is_a_failed_member_and_never_a_disposable_one() -> None:
    review = review_record(receipt=_evidence(record=_record()), subject=_SUBJECT)
    facts = [
        review is not None,
        review is not None and review.failed == (_CHANGED,),
        review is not None and _CHANGED not in review.members,
    ]
    assert all(facts), facts


def test_a_record_naming_another_head_is_not_judged() -> None:
    record = _record(risks=[], outcome="passed")
    record["identity"] = {**record["identity"], "head_sha": "d" * 40}
    assert review_record(receipt=_evidence(record=record), subject=_SUBJECT) is None


def test_arm_refuses_a_changed_tree_record_even_with_a_disposition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    disposition = disposition_receipt(
        evidence_receipt_id=_EVIDENCE,
        evidence_checksum=_CHECKSUM,
        member=_CHANGED,
        disposition="accepted",
        tree=_TREE,
    )
    receipts = {_EVIDENCE: _evidence(record=_record()), disposition["receipt_id"]: disposition}
    replies = [
        json.dumps(
            {
                "schema": 1,
                "status": "verified",
                "authorizes_current_effects": False,
                "normal_factory_proof": False,
                "result": _lookup(receipts.get(receipt_id), receipt_id),
            }
        )
        for receipt_id in (
            _EVIDENCE,
            evidence_receipt_id(subject=_SUBJECT, slot=1),
            disposition["receipt_id"],
        )
    ]
    run = Mock(side_effect=[subprocess.CompletedProcess([], 0, reply, "") for reply in replies])
    monkeypatch.setattr(subprocess, "run", run)
    forge = Mock(return_value={"sha": _HEAD, "tree": {"sha": _TREE}})
    refusal = FocusedEvidenceGate(
        command=("/installed/reader",),
        repo=Path("/protected/repo"),
        release="v0.304.0",
        installed_reader_approved=Mock(return_value=True),
        read=forge,
    )(_ARM)
    assert str(refusal).startswith(f"incident-focused-evidence-failed: {_CHANGED}"), refusal


def test_the_disposition_entrance_refuses_to_dispose_a_changed_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stale = {
        "EXPEDITED_INCIDENT_RESPONSE_REVERT",
        *(k for k in os.environ if k.startswith(("EXPEDITED_", "LIVESPEC_INCIDENT_"))),
    }
    for key in stale:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("EXPEDITED_INCIDENT_RESPONSE", "1")
    monkeypatch.setenv(QUERY_ENV, canonical(value=_QUERY))
    reading = {
        "attempt": {
            "repository": "owner/repo",
            "item_id": "incident-1",
            "attempt_id": "repair-1",
            "phase": "repair",
            "operation_id": "operation-1",
            "generation": 2,
            "owner": "operator:alice",
            "base": "e" * 40,
            "head": _HEAD,
            "pr_number": 55,
            "landed_commits": [],
        },
        "committed_token_id": "closed-1",
        "current_token_id": "open-2",
        "is_current": True,
    }
    authority = Mock(side_effect=[reading, _lookup(_evidence(record=_record()), _EVIDENCE)])
    monkeypatch.setattr(entry, "invoke_authority", authority)
    argv = ["--evidence-receipt", _EVIDENCE, "--member", _CHANGED, "--disposition", "accepted"]
    status = entry.main(argv=argv)
    facts = [
        status == 78,
        "a failing assertion requires repair" in capsys.readouterr().err,
        authority.call_count == 2,
    ]
    assert all(facts), facts
