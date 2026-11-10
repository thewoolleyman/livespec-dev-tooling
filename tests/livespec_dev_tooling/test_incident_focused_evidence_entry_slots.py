"""The evidence entrance appends each record to the next derived slot of its head tree.

The observer's `/arm` reads every slot of the head tree through
`read-local-gates`, so the writer never lets the operator choose which record
is judged: it takes the first free slot for the exact identity, head and tree.
"""

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-4aksht
from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from livespec_dev_tooling import incident_focused_evidence_entry as module
from livespec_dev_tooling.incident_focused_admission import EvidenceSubject, evidence_receipt_id
from livespec_dev_tooling.incident_hook_entry import QUERY_ENV
from livespec_dev_tooling.incident_hook_process import canonical

_HEAD = "c" * 40
_TREE = "f" * 40
_CHECKSUM = "sha256:" + "b" * 64
_QUERY = {
    "repository": "owner/repo",
    "item": "incident-1",
    "attempt": "attempt-1",
    "phase": "repair",
    "operation": "operation-1",
    "generation": 2,
    "owner": "operator:alice",
}
_SUBJECT = EvidenceSubject(
    repository="owner/repo",
    item="incident-1",
    attempt="attempt-1",
    operation="operation-1",
    generation=2,
    head=_HEAD,
    tree=_TREE,
)
_MANUAL = ["--procedure", "p", "--expected", "e", "--observed", "e", "--verdict", "passed"]
_ATTEMPT: dict[str, Any] = {
    "repository": "owner/repo",
    "item_id": "incident-1",
    "attempt_id": "attempt-1",
    "phase": "repair",
    "operation_id": "operation-1",
    "generation": 2,
    "owner": "operator:alice",
    "base": "e" * 40,
    "head": _HEAD,
    "pr_number": 55,
    "landed_commits": [],
}
_READING: dict[str, Any] = {
    "attempt": _ATTEMPT,
    "committed_token_id": "closed-1",
    "current_token_id": "open-2",
    "is_current": True,
}


class _Authority:
    def __init__(self) -> None:
        self.receipts: dict[str, dict[str, Any]] = {}
        self.actions: list[str] = []
        self.lookup: dict[str, Any] | None = None

    def __call__(self, **kwargs: Any) -> dict[str, Any]:
        action = kwargs["action"]
        self.actions.append(action)
        tokens = {"committed_token_id": "closed-1", "current_token_id": "open-2"}
        if action == "record-local-gates":
            receipt = json.loads(kwargs["receipt"])
            self.receipts[receipt["receipt_id"]] = receipt
            return {"receipt_id": receipt["receipt_id"], "checksum": _CHECKSUM, **tokens}
        if action == "read-local-gates":
            if self.lookup is not None:
                return self.lookup
            receipt = self.receipts.get(kwargs["receipt_id"])
            return {
                "status": "absent" if receipt is None else "recorded",
                "receipt_id": kwargs["receipt_id"],
                "receipt": receipt,
                "checksum": None if receipt is None else _CHECKSUM,
                **tokens,
            }
        return _READING


def _tree(**_: object) -> str:
    return _TREE


def _config(**_: object) -> SimpleNamespace:
    return SimpleNamespace(tests_tree_prefix="t/")


def _prefixes(**_: object) -> tuple[str, ...]:
    return ("src/",)


def _collected(**_: object) -> dict[str, Any]:
    return {"mode": "expedited-repair", "risks": [], "outcome": "passed"}


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
    monkeypatch.setattr(module, "exact_tree", _tree)
    monkeypatch.setattr(module, "load_config", _config)
    monkeypatch.setattr(module, "derive_source_prefixes", _prefixes)
    monkeypatch.setattr(module, "collect_focused_evidence", _collected)
    return fake


def test_each_run_takes_the_next_free_slot_of_the_head_tree(
    authority: _Authority, capsys: pytest.CaptureFixture[str]
) -> None:
    assert module.main(argv=_MANUAL) == 0
    first = json.loads(capsys.readouterr().out)["publication"]["receipt_id"]
    assert first == evidence_receipt_id(subject=_SUBJECT, slot=0)
    assert authority.actions == [
        "read-current",
        "read-local-gates",
        "record-local-gates",
        "read-local-gates",
        "read-history",
    ]
    assert module.main(argv=_MANUAL) == 0
    second = json.loads(capsys.readouterr().out)["publication"]["receipt_id"]
    assert second == evidence_receipt_id(subject=_SUBJECT, slot=1)
    assert set(authority.receipts) == {first, second}


def test_a_tree_whose_slots_are_all_recorded_refuses_and_publishes_nothing(
    authority: _Authority, capsys: pytest.CaptureFixture[str]
) -> None:
    for slot in range(8):
        receipt_id = evidence_receipt_id(subject=_SUBJECT, slot=slot)
        authority.receipts[receipt_id] = {"receipt_id": receipt_id}
    assert module.main(argv=_MANUAL) == 78
    assert "commit a new head" in capsys.readouterr().err
    assert "record-local-gates" not in authority.actions


@pytest.mark.parametrize(
    "lookup",
    [
        {"status": "absent", "receipt_id": "another"},
        {"status": "unavailable", "receipt_id": evidence_receipt_id(subject=_SUBJECT, slot=0)},
    ],
)
def test_a_slot_lookup_that_does_not_bind_the_slot_refuses(
    authority: _Authority, capsys: pytest.CaptureFixture[str], lookup: dict[str, Any]
) -> None:
    authority.lookup = lookup
    assert module.main(argv=_MANUAL) == 78
    assert "slot lookup does not bind this tree" in capsys.readouterr().err
    assert "record-local-gates" not in authority.actions
