"""Focused-evidence records are found by derived id and judged the way `/arm` judges them."""

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-4aksht
from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

import pytest

from livespec_dev_tooling.incident_focused_admission import (
    DISPOSITION_ROW,
    EVIDENCE_ROW,
    MAX_EVIDENCE_SLOTS,
    EvidenceReview,
    EvidenceSubject,
    disposition_matches,
    disposition_receipt,
    disposition_receipt_id,
    evidence_receipt_id,
    first_free_slot,
    review_record,
)

_TREE = "f" * 40
_SUBJECT = EvidenceSubject(
    repository="owner/repo",
    item="incident-1",
    attempt="repair-1",
    operation="operation-1",
    generation=4,
    head="c" * 40,
    tree=_TREE,
)


def _record(**changes: Any) -> dict[str, Any]:
    record: dict[str, Any] = {
        "mode": "expedited-repair",
        "scope": "focused-tests-and-touched-files",
        "tree_hash": _TREE,
        "identity": {
            "incident_item_id": "incident-1",
            "attempt_id": "repair-1",
            "phase": "repair",
            "repository": "owner/repo",
            "base_sha": "e" * 40,
            "head_sha": "c" * 40,
            "operation_id": "operation-1",
        },
        "paths": {"src/widget.py": "executable", "README.md": "non-executable"},
        "selection": {"tests": ["tests/test_widget.py"], "deferred_tests": {}},
        "manual": {
            "procedure": "call widget",
            "expected": "42",
            "observed": "42",
            "outcome": "passed",
        },
        "tests": {"returncode": 0, "timed_out": False},
        "coverage_command": {"returncode": 0, "timed_out": False},
        "coverage": {"src/widget.py": {"summary": {"percent_covered": 100}}},
        "risks": [],
        "outcome": "passed",
    }
    record.update(changes)
    return record


def _receipt(*, record: object, status: str = "passed", **changes: Any) -> dict[str, Any]:
    receipt: dict[str, Any] = {
        "receipt_id": "evidence",
        "hook": "pre-push",
        "tree": _TREE,
        "mode": "expedited-repair",
        "evidence_kind": "expedited-local-partial",
        "exit_status": 0,
        "results": [
            {
                "name": EVIDENCE_ROW,
                "status": status,
                "reason": "focused evidence",
                "returncode": 0,
                "duration_seconds": 1.0,
                "output": record if isinstance(record, str) else json.dumps(record),
            }
        ],
    }
    receipt.update(changes)
    return receipt


def _review(*, record: object, **changes: Any) -> EvidenceReview | None:
    return review_record(receipt=_receipt(record=record, **changes), subject=_SUBJECT)


def test_a_complete_passing_record_leaves_nothing_to_dispose() -> None:
    assert _review(record=_record()) == EvidenceReview(missing=(), failed=(), members=())


def test_evidence_ids_name_identity_head_tree_and_slot() -> None:
    first = evidence_receipt_id(subject=_SUBJECT, slot=0)
    assert first == evidence_receipt_id(subject=_SUBJECT, slot=0)
    assert first != evidence_receipt_id(subject=_SUBJECT, slot=1)
    assert first != evidence_receipt_id(subject=replace(_SUBJECT, tree="a" * 40), slot=0)
    assert first != evidence_receipt_id(subject=replace(_SUBJECT, generation=5), slot=0)
    assert disposition_receipt_id(evidence_receipt_id=first, member="m") != (
        disposition_receipt_id(evidence_receipt_id=first, member="n")
    )


def test_the_first_unrecorded_slot_is_chosen_and_a_full_tree_has_none() -> None:
    taken = {evidence_receipt_id(subject=_SUBJECT, slot=slot) for slot in range(2)}
    assert first_free_slot(subject=_SUBJECT, recorded=taken.__contains__) == (
        evidence_receipt_id(subject=_SUBJECT, slot=2)
    )
    assert first_free_slot(subject=_SUBJECT, recorded=lambda _: True) is None
    assert MAX_EVIDENCE_SLOTS == 8


@pytest.mark.parametrize(
    ("change", "value"),
    [
        ("tree", "a" * 40),
        ("mode", "emergency-revert"),
        ("evidence_kind", "normal"),
        ("results", []),
        ("results", [{"name": "other", "output": "{}"}]),
        ("results", [{"name": EVIDENCE_ROW, "output": 3}]),
        ("results", ["not a row"]),
    ],
)
def test_a_receipt_that_is_not_this_trees_evidence_is_not_judged(change: str, value: Any) -> None:
    assert _review(record=_record(), **{change: value}) is None


@pytest.mark.parametrize(
    "record",
    [
        "not json",
        "[1]",
        _record(mode="normal"),
        _record(scope="full"),
        _record(tree_hash="a" * 40),
        _record(outcome="unknown"),
        _record(identity={"head_sha": "d" * 40}),
        _record(identity="not a mapping"),
        _record(risks="not a list"),
        _record(risks=[3]),
    ],
)
def test_a_record_that_does_not_bind_this_subject_is_not_judged(record: object) -> None:
    assert _review(record=record if isinstance(record, str) else record) is None


@pytest.mark.parametrize(
    ("changes", "missing"),
    [
        ({"manual": None}, ("manual reproduction",)),
        ({"manual": {**_record()["manual"], "observed": "  "}}, ("manual reproduction",)),
        ({"manual": {**_record()["manual"], "outcome": "skipped"}}, ("manual reproduction",)),
        ({"tests": None}, ("focused test result",)),
        ({"tests": {"returncode": "0", "timed_out": False}}, ("focused test result",)),
        ({"tests": {"returncode": 0, "timed_out": "no"}}, ("focused test result",)),
        ({"coverage": None}, ("touched-file coverage result",)),
        ({"paths": None}, ("touched-file coverage result",)),
        ({"coverage_command": None}, ("touched-file coverage result",)),
        ({"coverage": {}}, ("touched-file coverage result: src/widget.py",)),
        (
            {"coverage": {"src/widget.py": {"summary": {"percent_covered": True}}}},
            ("touched-file coverage result: src/widget.py",),
        ),
    ],
)
def test_a_record_lacking_a_required_member_names_it(
    changes: dict[str, Any], missing: tuple[str, ...]
) -> None:
    review = _review(record=_record(**changes))
    assert review is not None
    assert review.missing == missing


@pytest.mark.parametrize(
    ("changes", "failed"),
    [
        (
            {"tests": {"returncode": 1, "timed_out": False}, "outcome": "failed"},
            ("focused test",),
        ),
        (
            {
                "manual": {**_record()["manual"], "outcome": "failed"},
                "risks": ["manual reproduction did not pass"],
                "outcome": "failed",
            },
            ("manual reproduction",),
        ),
        ({"outcome": "failed"}, ("focused evidence outcome",)),
        ({"tests": {"returncode": 1, "timed_out": True}, "outcome": "incomplete"}, ()),
    ],
)
def test_a_failed_member_is_named_as_failed(
    changes: dict[str, Any], failed: tuple[str, ...]
) -> None:
    review = _review(record=_record(**changes))
    assert review is not None
    assert review.failed == failed
    assert "manual reproduction did not pass" not in review.members


def test_every_deferred_or_incomplete_member_needs_a_disposition() -> None:
    record = _record(
        paths={"src/widget.py": "executable", "run.sh": "unsupported-executable"},
        coverage={"src/widget.py": {"summary": {"percent_covered": 87.5}}},
        selection={"tests": [], "deferred_tests": {"tests/test_slow.py": "slow"}},
        tests={"returncode": None, "timed_out": True},
        risks=["coverage incomplete: src/widget.py", "incident tree changed during collection"],
        outcome="incomplete",
    )
    review = _review(record=record, status="deferred-timeout")
    assert review is not None
    assert review.members == (
        "coverage incomplete: src/widget.py",
        "unsupported executable coverage: run.sh",
        "deferred test: tests/test_slow.py: slow",
        "focused test or coverage collection incomplete",
        "focused evidence collection reached the sixty-second budget",
        "incident tree changed during collection",
    )


def test_a_failed_coverage_report_and_an_unexplained_incomplete_outcome_need_disposition() -> None:
    review = _review(record=_record(coverage_command={"returncode": 2, "timed_out": False}))
    assert review is not None
    assert review.members == ("focused test or coverage collection incomplete",)
    review = _review(record=_record(outcome="incomplete"))
    assert review is not None
    assert review.members == ("focused evidence outcome incomplete",)


def _disposition(**changes: Any) -> dict[str, Any]:
    receipt = disposition_receipt(
        evidence_receipt_id="evidence",
        evidence_checksum="sha256:" + "1" * 64,
        member="coverage incomplete: src/widget.py",
        disposition="risk accepted for the incident",
        tree=_TREE,
    )
    receipt.update(changes)
    return receipt


def _matches(receipt: dict[str, Any]) -> bool:
    return disposition_matches(
        receipt=receipt,
        evidence_receipt_id="evidence",
        evidence_checksum="sha256:" + "1" * 64,
        member="coverage incomplete: src/widget.py",
        tree=_TREE,
    )


def test_a_disposition_binds_one_member_of_the_exact_record_bytes() -> None:
    receipt = _disposition()
    assert receipt["receipt_id"] == disposition_receipt_id(
        evidence_receipt_id="evidence", member="coverage incomplete: src/widget.py"
    )
    row = receipt["results"][0]
    assert (row["name"], row["status"], row["returncode"], row["duration_seconds"]) == (
        DISPOSITION_ROW,
        "deferred",
        None,
        0,
    )
    assert _matches(receipt)


def _with_output(**changes: Any) -> dict[str, Any]:
    receipt = _disposition()
    output = json.loads(receipt["results"][0]["output"])
    output.update(changes)
    receipt["results"] = [{**receipt["results"][0], "output": json.dumps(output)}]
    return receipt


@pytest.mark.parametrize(
    "receipt",
    [
        _disposition(receipt_id="other"),
        _disposition(tree="a" * 40),
        _disposition(results=[]),
        _disposition(results=[{"name": "other", "output": "{}"}]),
        _disposition(results=[{"name": DISPOSITION_ROW, "output": None}]),
        _disposition(results=[{"name": DISPOSITION_ROW, "output": "not json"}]),
        _with_output(evidence_receipt_id="other"),
        _with_output(evidence_checksum="sha256:" + "2" * 64),
        _with_output(member="other"),
        _with_output(disposition="   "),
        _with_output(disposition=None),
    ],
)
def test_a_disposition_of_anything_else_disposes_nothing(receipt: dict[str, Any]) -> None:
    assert not _matches(receipt)
