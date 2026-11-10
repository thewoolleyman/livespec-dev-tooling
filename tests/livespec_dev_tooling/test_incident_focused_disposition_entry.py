"""An operator disposes an incomplete member of focused evidence, never a failed one."""

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-4aksht
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from livespec_dev_tooling import incident_focused_disposition_entry as module
from livespec_dev_tooling.incident_focused_admission import (
    EVIDENCE_ROW,
    EvidenceSubject,
    disposition_receipt_id,
    evidence_receipt_id,
)
from livespec_dev_tooling.incident_hook_entry import QUERY_ENV
from livespec_dev_tooling.incident_hook_process import canonical

_HEAD = "c" * 40
_TREE = "f" * 40
_CHECKSUM = "sha256:" + "1" * 64
_MEMBER = "coverage incomplete: src/widget.py"
_QUERY = {
    "repository": "owner/repo",
    "item": "incident-1",
    "attempt": "attempt-1",
    "phase": "repair",
    "operation": "operation-1",
    "generation": 3,
    "owner": "operator:alice",
}
_SUBJECT = EvidenceSubject(
    repository="owner/repo",
    item="incident-1",
    attempt="attempt-1",
    operation="operation-1",
    generation=3,
    head=_HEAD,
    tree=_TREE,
)
_EVIDENCE = evidence_receipt_id(subject=_SUBJECT, slot=1)


def _record(**changes: Any) -> dict[str, Any]:
    record: dict[str, Any] = {
        "mode": "expedited-repair",
        "scope": "focused-tests-and-touched-files",
        "tree_hash": _TREE,
        "identity": {
            "incident_item_id": "incident-1",
            "attempt_id": "attempt-1",
            "repository": "owner/repo",
            "head_sha": _HEAD,
            "operation_id": "operation-1",
        },
        "paths": {"src/widget.py": "executable"},
        "selection": {"tests": [], "deferred_tests": {}},
        "manual": {"procedure": "p", "expected": "e", "observed": "e", "outcome": "passed"},
        "tests": {"returncode": 0, "timed_out": False},
        "coverage_command": {"returncode": 0, "timed_out": False},
        "coverage": {"src/widget.py": {"summary": {"percent_covered": 50}}},
        "risks": [_MEMBER],
        "outcome": "incomplete",
    }
    record.update(changes)
    return record


def _evidence(*, record: dict[str, Any], receipt_id: str = _EVIDENCE) -> dict[str, Any]:
    return {
        "receipt_id": receipt_id,
        "hook": "pre-push",
        "tree": _TREE,
        "mode": "expedited-repair",
        "evidence_kind": "expedited-local-partial",
        "exit_status": 1,
        "results": [{"name": EVIDENCE_ROW, "status": "failed", "output": json.dumps(record)}],
    }


class _Authority:
    def __init__(self) -> None:
        self.receipts: dict[str, dict[str, Any]] = {}
        self.actions: list[str] = []
        self.spoil = ""

    def __call__(self, **kwargs: Any) -> dict[str, Any]:
        assert kwargs["query"] == _QUERY
        action = kwargs["action"]
        self.actions.append(action)
        if action == "record-local-gates":
            receipt = json.loads(kwargs["receipt"])
            if self.spoil == "tree":
                receipt["tree"] = "a" * 40
            if self.spoil == "text":
                output = json.loads(receipt["results"][0]["output"])
                output["disposition"] = "a different text"
                receipt["results"][0]["output"] = json.dumps(output)
            self.receipts[receipt["receipt_id"]] = receipt
            return {"receipt_id": receipt["receipt_id"], "checksum": _CHECKSUM}
        if action == "read-local-gates":
            receipt = self.receipts.get(kwargs["receipt_id"])
            return {
                "status": "absent" if receipt is None else "recorded",
                "receipt_id": kwargs["receipt_id"],
                "receipt": receipt,
                "checksum": None if receipt is None else _CHECKSUM,
            }
        return {
            "attempt": {
                "repository": "owner/repo",
                "item_id": "incident-1",
                "attempt_id": "attempt-1",
                "phase": "repair",
                "operation_id": "operation-1",
                "generation": 3,
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


@pytest.fixture
def authority(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _Authority:
    # The set is never empty, so the scrub runs on a host whose environment carries none.
    stale = {
        "EXPEDITED_INCIDENT_RESPONSE_REVERT",
        *(k for k in os.environ if k.startswith(("EXPEDITED_", "LIVESPEC_INCIDENT_"))),
    }
    for key in stale:
        monkeypatch.delenv(key, raising=False)
    fake = _Authority()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("EXPEDITED_INCIDENT_RESPONSE", "1")
    monkeypatch.setenv(QUERY_ENV, canonical(value=_QUERY))
    monkeypatch.setattr(module, "invoke_authority", fake)
    return fake


def _main(*members: str, disposition: str = "risk accepted for the incident") -> int:
    argv = ["--evidence-receipt", _EVIDENCE, "--disposition", disposition]
    for member in members:
        argv.extend(["--member", member])
    return module.main(argv=argv)


def test_an_incomplete_member_is_disposed_and_read_back(
    authority: _Authority, capsys: pytest.CaptureFixture[str]
) -> None:
    authority.receipts[_EVIDENCE] = _evidence(record=_record())
    assert _main(_MEMBER, _MEMBER) == 0
    printed = json.loads(capsys.readouterr().out)
    disposition_id = disposition_receipt_id(evidence_receipt_id=_EVIDENCE, member=_MEMBER)
    assert printed == {
        "schema": 1,
        "evidence_receipt_id": _EVIDENCE,
        "tree": _TREE,
        "dispositions": [{"member": _MEMBER, "receipt_id": disposition_id, "checksum": _CHECKSUM}],
        "normal_factory_proof": False,
    }
    output = json.loads(authority.receipts[disposition_id]["results"][0]["output"])
    assert (output["evidence_checksum"], output["disposition"]) == (
        _CHECKSUM,
        "risk accepted for the incident",
    )
    assert authority.actions == [
        "read-current",
        "read-local-gates",
        "record-local-gates",
        "read-local-gates",
    ]


def test_a_failed_member_is_never_disposed(
    authority: _Authority, capsys: pytest.CaptureFixture[str]
) -> None:
    record = _record(tests={"returncode": 1, "timed_out": False}, outcome="failed")
    authority.receipts[_EVIDENCE] = _evidence(record=record)
    assert _main("focused test") == 78
    assert "a failing assertion requires repair" in capsys.readouterr().err
    assert "record-local-gates" not in authority.actions


def test_an_unknown_member_is_refused_naming_the_records_members(
    authority: _Authority, capsys: pytest.CaptureFixture[str]
) -> None:
    authority.receipts[_EVIDENCE] = _evidence(record=_record())
    assert _main("something else") == 78
    assert _MEMBER in capsys.readouterr().err
    assert "record-local-gates" not in authority.actions


@pytest.mark.parametrize(
    ("receipt", "reason"),
    [
        (None, "no recorded receipt"),
        (_evidence(record=_record(), receipt_id="other"), "no recorded receipt"),
        (_evidence(record=_record(tree_hash="a" * 40)), "is not a focused-evidence record"),
    ],
)
def test_evidence_that_does_not_read_back_as_this_trees_record_is_refused(
    authority: _Authority,
    capsys: pytest.CaptureFixture[str],
    receipt: dict[str, Any] | None,
    reason: str,
) -> None:
    if receipt is not None:
        authority.receipts[_EVIDENCE] = receipt
    assert _main(_MEMBER) == 78
    assert reason in capsys.readouterr().err
    assert "record-local-gates" not in authority.actions


def test_a_receipt_that_is_not_an_evidence_slot_of_the_current_head_is_refused(
    authority: _Authority, capsys: pytest.CaptureFixture[str]
) -> None:
    other = evidence_receipt_id(subject=_SUBJECT, slot=8)
    authority.receipts[other] = _evidence(record=_record(), receipt_id=other)
    status = module.main(
        argv=["--evidence-receipt", other, "--disposition", "accepted", "--member", _MEMBER]
    )
    assert status == 78
    assert "is not focused evidence of the current head" in capsys.readouterr().err


@pytest.mark.parametrize("spoil", ["tree", "text"])
def test_a_disposition_that_does_not_read_back_exactly_is_refused(
    authority: _Authority, capsys: pytest.CaptureFixture[str], spoil: str
) -> None:
    authority.receipts[_EVIDENCE] = _evidence(record=_record())
    authority.spoil = spoil
    assert _main(_MEMBER) == 78
    assert "does not read back exactly" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("environment", "reason"),
    [
        ({"EXPEDITED_INCIDENT_RESPONSE": None}, "resolved expedited incident context required"),
        ({"EXPEDITED_INCIDENT_RESPONSE": "maybe"}, "malformed incident flag"),
        ({QUERY_ENV: None}, "exact canonical incident authority query required"),
    ],
)
def test_outside_a_resolved_incident_context_nothing_is_read(
    authority: _Authority,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    environment: dict[str, str | None],
    reason: str,
) -> None:
    for name, value in environment.items():
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)
    assert _main(_MEMBER) == 78
    assert reason in capsys.readouterr().err
    assert authority.actions == []


def test_an_empty_disposition_is_refused(
    authority: _Authority, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _main(_MEMBER, disposition="   ") == 78
    assert "disposition text is empty" in capsys.readouterr().err
    assert authority.actions == []


def test_usage_errors_refuse_and_help_does_not(capsys: pytest.CaptureFixture[str]) -> None:
    assert module.main(argv=["--member", _MEMBER]) == 78
    assert module.main(argv=["--help"]) == 0
    assert "usage" in capsys.readouterr().out
