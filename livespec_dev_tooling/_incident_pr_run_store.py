"""Strictly validated expedited pull-request run subtree of the controller record.

Each run attempt of the incident CI job on an armed head owns one slot. A slot holds
the records owed to the incident item, in arrival order, each bound to its key and
content by a domain-separated digest, and whether the item already carries it.
Malformed state refuses instead of becoming empty.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, cast

__all__: list[str] = [
    "KEY_INTS",
    "KEY_TEXTS",
    "add_record",
    "mark_written",
    "pending_records",
    "record_digest",
    "run_slot",
    "run_tree",
]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-bqnzcm.4
_DIGEST = b"livespec-incident-pr-run-record-v1\0"
_HEX = re.compile(r"[0-9a-f]{64}")
_INVALID = "invalid stored expedited pull-request run subtree"
_KINDS = frozenset({"unpublished"})
KEY_INTS = frozenset({"generation", "pr_number", "run_id", "run_attempt"})
KEY_TEXTS = frozenset(
    {"repository", "incident_item_id", "attempt_id", "arm_id", "base_sha", "head_sha"}
)
_ENTRY = frozenset({"kind", "key", "content", "digest", "written"})


def run_slot(*, run_id: int, run_attempt: int) -> str:
    """One slot per run attempt of the incident CI job."""
    return f"{run_id}:{run_attempt}"


def record_digest(*, kind: str, key: dict[str, Any], content: dict[str, Any]) -> str:
    """Domain-separated digest of one record's kind, key and content."""
    raw = json.dumps([kind, key, content], sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(_DIGEST + raw).hexdigest()


def run_tree(*, record: dict[str, object]) -> dict[str, Any]:
    """Return a validated copy of the subtree; absent state is an empty tree."""
    raw = record.get("pr_run_records")
    if raw is None:
        return {"schema": 1, "runs": {}}
    tree = _mapping(value=raw)
    if set(tree) != {"schema", "runs"} or type(tree["schema"]) is not int or tree["schema"] != 1:
        raise ValueError(_INVALID)
    runs = {
        slot: [_entry(value=row) for row in _rows(value=rows)]
        for slot, rows in _mapping(value=tree["runs"]).items()
    }
    return {"schema": 1, "runs": runs}


def add_record(
    *, record: dict[str, object], kind: str, key: dict[str, Any], content: dict[str, Any]
) -> bool:
    """Append one record to its run's slot; False when that exact record is already held."""
    tree = run_tree(record=record)
    slot = run_slot(run_id=key["run_id"], run_attempt=key["run_attempt"])
    rows: list[dict[str, Any]] = tree["runs"].setdefault(slot, [])
    digest = record_digest(kind=kind, key=key, content=content)
    if any(row["digest"] == digest for row in rows):
        return False
    rows.append({"kind": kind, "key": key, "content": content, "digest": digest, "written": False})
    record["pr_run_records"] = tree
    return True


def pending_records(*, record: dict[str, object]) -> tuple[dict[str, Any], ...]:
    """Every held record the incident item does not yet carry, in slot and arrival order."""
    runs: dict[str, list[dict[str, Any]]] = run_tree(record=record)["runs"]
    return tuple(row for slot in sorted(runs) for row in runs[slot] if not row["written"])


def mark_written(*, record: dict[str, object], digest: str) -> bool:
    """Mark the record with `digest` as carried by the item; False when none matches."""
    tree = run_tree(record=record)
    for rows in tree["runs"].values():
        for row in rows:
            if row["digest"] == digest:
                row["written"] = True
                record["pr_run_records"] = tree
                return True
    return False


def _mapping(*, value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError(_INVALID)
    return dict(cast("dict[str, Any]", value))


def _rows(*, value: object) -> list[object]:
    if not isinstance(value, list):
        raise TypeError(_INVALID)
    return list(cast("list[object]", value))


def _entry(*, value: object) -> dict[str, Any]:
    entry = _mapping(value=value)
    if (
        frozenset(entry) != _ENTRY
        or entry["kind"] not in _KINDS
        or type(entry["written"]) is not bool
    ):
        raise ValueError(_INVALID)
    key = _mapping(value=entry["key"])
    content = _mapping(value=entry["content"])
    if (
        frozenset(key) != KEY_INTS | KEY_TEXTS
        or not all(type(key[k]) is int and key[k] >= 0 for k in KEY_INTS)
        or not all(isinstance(key[k], str) for k in KEY_TEXTS)
        or not _HEX.fullmatch(key["arm_id"])
        or not _unpublished(content=content)
        or entry["digest"] != record_digest(kind=entry["kind"], key=key, content=content)
    ):
        raise ValueError(_INVALID)
    return entry | {"key": key, "content": content}


def _unpublished(*, content: dict[str, Any]) -> bool:
    return (
        set(content) == {"conclusion", "refusal"}
        and isinstance(content["conclusion"], str)
        and (content["refusal"] is None or isinstance(content["refusal"], str))
    )
