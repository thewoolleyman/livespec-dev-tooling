"""Name and judge the focused-evidence records an expedited arm must find.

Both sides of a record share these names. The operator's evidence and
disposition entrances write receipts under them through the canonical
authority's `record-local-gates`; the observer's `/arm` reads them back through
`read-local-gates`, which answers by receipt id only. The ids are therefore
derived, never chosen by a caller. An evidence record's id names the incident
identity, the exact head and its tree, and a slot, so the observer finds EVERY
record for that head tree without being told which one to read. A disposition's
id names the evidence record and the one member it disposes.

`review_record` reads one record the way `/arm` judges it (SPECIFICATION
`contracts.md`, the expedited incident execution contract: "Incomplete focused
evidence MUST remain recorded risk with an operator disposition; a failing assertion
requires repair"): which required members it lacks, which members failed, and
which deferred or incomplete members need an operator disposition.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any, cast

__all__: list[str] = [
    "DISPOSITION_ROW",
    "EVIDENCE_ROW",
    "MAX_EVIDENCE_SLOTS",
    "EvidenceReview",
    "EvidenceSubject",
    "disposition_matches",
    "disposition_receipt",
    "disposition_receipt_id",
    "evidence_receipt_id",
    "first_free_slot",
    "review_record",
]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-4aksht
EVIDENCE_ROW = "incident-focused-evidence"
DISPOSITION_ROW = "incident-focused-evidence-disposition"
# Records one head tree may carry under one generation; a further run needs a new head.
MAX_EVIDENCE_SLOTS = 8
_FULL_COVERAGE = 100
_MANUAL_FAILED_RISK = "manual reproduction did not pass"
_MANUAL_FIELDS = ("procedure", "expected", "observed")
_OUTCOMES = frozenset(("passed", "incomplete", "failed"))


@dataclass(frozen=True, kw_only=True)
class EvidenceSubject:
    """The exact incident identity, head and head tree one record must measure."""

    repository: str
    item: str
    attempt: str
    operation: str
    generation: int
    head: str
    tree: str


@dataclass(frozen=True, kw_only=True)
class EvidenceReview:
    """What one record lacks, what failed in it, and what it leaves to disposition."""

    missing: tuple[str, ...]
    failed: tuple[str, ...]
    members: tuple[str, ...]


def _digest(*, value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def evidence_receipt_id(*, subject: EvidenceSubject, slot: int) -> str:
    """The receipt id of one evidence slot for exactly this identity, head and tree."""
    return _digest(value=[EVIDENCE_ROW, asdict(subject), slot])


def disposition_receipt_id(*, evidence_receipt_id: str, member: str) -> str:
    """The receipt id of the one operator disposition of one member of one record."""
    return _digest(value=[DISPOSITION_ROW, evidence_receipt_id, member])


def first_free_slot(*, subject: EvidenceSubject, recorded: Callable[[str], bool]) -> str | None:
    """The first unrecorded slot's receipt id, or None when every slot is taken."""
    for slot in range(MAX_EVIDENCE_SLOTS):
        receipt_id = evidence_receipt_id(subject=subject, slot=slot)
        if not recorded(receipt_id):
            return receipt_id
    return None


def _mapping(*, value: object) -> dict[str, Any] | None:
    return cast("dict[str, Any]", value) if isinstance(value, dict) else None


def _single_row(*, receipt: dict[str, Any]) -> dict[str, Any] | None:
    rows = receipt.get("results")
    items = cast("list[object]", rows) if isinstance(rows, list) else []
    return _mapping(value=items[0]) if len(items) == 1 else None


def _record(*, receipt: dict[str, Any], subject: EvidenceSubject) -> dict[str, Any] | None:
    row = _single_row(receipt=receipt)
    if (
        row is None
        or row.get("name") != EVIDENCE_ROW
        or not isinstance(row.get("output"), str)
        or receipt.get("tree") != subject.tree
        or receipt.get("mode") != "expedited-repair"
        or receipt.get("evidence_kind") != "expedited-local-partial"
    ):
        return None
    try:
        record = _mapping(value=json.loads(row["output"]))
    except ValueError:
        return None
    identity = _mapping(value=(record or {}).get("identity")) or {}
    expected = {
        "repository": subject.repository,
        "incident_item_id": subject.item,
        "attempt_id": subject.attempt,
        "operation_id": subject.operation,
        "head_sha": subject.head,
    }
    if (
        record is None
        or record.get("mode") != "expedited-repair"
        or record.get("scope") != "focused-tests-and-touched-files"
        or record.get("tree_hash") != subject.tree
        or str(record.get("outcome")) not in _OUTCOMES
        or any(identity.get(key) != value for key, value in expected.items())
    ):
        return None
    return {**record, "row_status": row.get("status")}


def _run(*, value: object) -> dict[str, Any] | None:
    run = _mapping(value=value)
    if (
        run is None
        or not isinstance(run.get("timed_out"), bool)
        or not (run.get("returncode") is None or type(run.get("returncode")) is int)
    ):
        return None
    return run


def _percent(*, row: object) -> float | None:
    value = (_mapping(value=(_mapping(value=row) or {}).get("summary")) or {}).get(
        "percent_covered"
    )
    return float(cast("float", value)) if type(value) in {int, float} else None


def _missing(*, record: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    manual = _mapping(value=record.get("manual")) or {}
    if manual.get("outcome") not in {"passed", "failed"} or not all(
        isinstance(manual.get(name), str) and manual[name].strip() for name in _MANUAL_FIELDS
    ):
        missing.append("manual reproduction")
    if _run(value=record.get("tests")) is None:
        missing.append("focused test result")
    paths = _mapping(value=record.get("paths"))
    coverage = _mapping(value=record.get("coverage"))
    if paths is None or coverage is None or _run(value=record.get("coverage_command")) is None:
        missing.append("touched-file coverage result")
        return missing
    missing.extend(
        f"touched-file coverage result: {name}"
        for name, disposition in sorted(paths.items())
        if disposition == "executable" and _percent(row=coverage.get(name)) is None
    )
    return missing


def _failed(*, record: dict[str, Any]) -> list[str]:
    tests = _run(value=record.get("tests")) or {"returncode": None, "timed_out": False}
    manual = _mapping(value=record.get("manual")) or {}
    failed = [
        *(["focused test"] if tests["returncode"] and not tests["timed_out"] else []),
        *(["manual reproduction"] if manual.get("outcome") == "failed" else []),
    ]
    if not failed and record["outcome"] == "failed":
        failed.append("focused evidence outcome")
    return failed


def _members(*, record: dict[str, Any]) -> list[str] | None:
    raw = record.get("risks")
    risks = cast("list[object]", raw) if isinstance(raw, list) else None
    if risks is None or not all(isinstance(risk, str) for risk in risks):
        return None
    paths = _mapping(value=record.get("paths")) or {}
    coverage = _mapping(value=record.get("coverage")) or {}
    deferred = _mapping(value=(_mapping(value=record.get("selection")) or {}).get("deferred_tests"))
    tests = _run(value=record.get("tests")) or {}
    report = _run(value=record.get("coverage_command")) or {}
    members = [
        *(
            f"coverage incomplete: {name}"
            for name, row in sorted(coverage.items())
            if (_percent(row=row) or 0) < _FULL_COVERAGE
        ),
        *(
            f"unsupported executable coverage: {name}"
            for name, disposition in sorted(paths.items())
            if disposition == "unsupported-executable"
        ),
        *(f"deferred test: {name}: {reason}" for name, reason in (deferred or {}).items()),
        *(
            ["focused test or coverage collection incomplete"]
            if tests.get("timed_out") or report.get("timed_out") or report.get("returncode")
            else []
        ),
        *(
            ["focused evidence collection reached the sixty-second budget"]
            if record["row_status"] == "deferred-timeout"
            else []
        ),
        *(risk for risk in cast("list[str]", risks) if risk != _MANUAL_FAILED_RISK),
    ]
    if not members and record["outcome"] == "incomplete":
        members.append("focused evidence outcome incomplete")
    return list(dict.fromkeys(members))


def review_record(*, receipt: dict[str, Any], subject: EvidenceSubject) -> EvidenceReview | None:
    """Judge one evidence receipt; None when it is not a record of exactly this subject."""
    record = _record(receipt=receipt, subject=subject)
    members = None if record is None else _members(record=record)
    if record is None or members is None:
        return None
    return EvidenceReview(
        missing=tuple(_missing(record=record)),
        failed=tuple(_failed(record=record)),
        members=tuple(members),
    )


def disposition_receipt(
    *, evidence_receipt_id: str, evidence_checksum: str, member: str, disposition: str, tree: str
) -> dict[str, Any]:
    """One operator risk disposition, bound to the exact record bytes it accepts."""
    output = {
        "schema": 1,
        "evidence_receipt_id": evidence_receipt_id,
        "evidence_checksum": evidence_checksum,
        "member": member,
        "disposition": disposition,
    }
    return {
        "receipt_id": disposition_receipt_id(
            evidence_receipt_id=evidence_receipt_id, member=member
        ),
        "hook": "pre-push",
        "tree": tree,
        "mode": "expedited-repair",
        "evidence_kind": "expedited-local-partial",
        "exit_status": 0,
        "results": [
            {
                "name": DISPOSITION_ROW,
                "status": "deferred",
                "reason": "operator risk disposition: " + member,
                "returncode": None,
                "duration_seconds": 0,
                "output": json.dumps(output, sort_keys=True, separators=(",", ":")),
            }
        ],
    }


def disposition_matches(
    *,
    receipt: dict[str, Any],
    evidence_receipt_id: str,
    evidence_checksum: str,
    member: str,
    tree: str,
) -> bool:
    """True only for a non-empty disposition of this member of these exact record bytes."""
    row = _single_row(receipt=receipt)
    if row is None or row.get("name") != DISPOSITION_ROW or not isinstance(row.get("output"), str):
        return False
    try:
        output = _mapping(value=json.loads(row["output"])) or {}
    except ValueError:
        return False
    text = output.get("disposition")
    return (
        receipt.get("receipt_id")
        == disposition_receipt_id(evidence_receipt_id=evidence_receipt_id, member=member)
        and output.get("evidence_receipt_id") == evidence_receipt_id
        and output.get("evidence_checksum") == evidence_checksum
        and output.get("member") == member
        and isinstance(text, str)
        and bool(text.strip())
        and receipt.get("tree") == tree
    )
