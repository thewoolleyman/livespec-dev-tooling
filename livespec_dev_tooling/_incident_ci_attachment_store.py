"""Strictly validated non-authorizing CI job attachment subtree of the controller record."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, cast

__all__: list[str] = [
    "BINDING_INTS",
    "BINDING_TEXTS",
    "OBSERVATION_STATUSES",
    "TERMINAL_STATUSES",
    "attachment_receipt",
    "attachment_slot",
    "attachment_tree",
    "binding_digest",
    "observation_receipt",
    "observation_reply",
    "raw_fact",
    "valid_collection_id",
]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-si6uu7
_SLOT = b"livespec-incident-ci-attachment-slot-v1\0"
_BINDING = b"livespec-incident-ci-attachment-binding-v1\0"
_OBSERVATION = b"livespec-incident-ci-job-observation-v1\0"
_HEX = re.compile(r"[0-9a-f]{64}")
_COLLECTION = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}")
_RAW = re.compile(r"[a-z_]{1,32}")
_INVALID = "invalid stored CI job attachment subtree"
BINDING_INTS = frozenset(
    {
        "repository_id",
        "repository_owner_id",
        "generation",
        "pr_number",
        "run_id",
        "run_attempt",
        "job_id",
        "check_run_id",
        "check_suite_id",
    }
)
BINDING_TEXTS = frozenset(
    {
        "repository",
        "incident_item_id",
        "attempt_id",
        "operation_id",
        "owner",
        "phase",
        "arm_id",
        "receipt_digest",
        "base_sha",
        "head_sha",
        "merge_sha",
        "ref",
        "base_ref",
        "head_ref",
        "caller_workflow_ref",
        "caller_workflow_sha",
        "reusable_workflow_ref",
        "reusable_workflow_sha",
        "policy_sha256",
        "controller_release",
        "controller_revision",
    }
)
TERMINAL_STATUSES = frozenset({"successful", "failed", "skipped", "cancelled"})
OBSERVATION_STATUSES = TERMINAL_STATUSES | {"pending", "unavailable", "conflict"}
_FACTS = frozenset({"job_status", "job_conclusion", "check_status", "check_conclusion"})
_FALSE = {
    "authorizes_current_effects": False,
    "ci_admission": False,
    "authorizes_merge": False,
    "normal_factory_proof": False,
}


def _digest(*, domain: bytes, value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(domain + raw).hexdigest()


def attachment_slot(*, repository_id: int, run_id: int, run_attempt: int, check_run_id: int) -> str:
    """One stable slot per signed check of one exact run attempt."""
    return _digest(domain=_SLOT, value=[repository_id, run_id, run_attempt, check_run_id])


def binding_digest(*, binding: dict[str, Any]) -> str:
    """Domain-separated digest of the complete immutable binding."""
    return _digest(domain=_BINDING, value=binding)


def attachment_receipt(*, binding: dict[str, Any]) -> dict[str, Any]:
    """The deterministic non-authorizing reply, recomputed from the stored binding."""
    slot = attachment_slot(
        repository_id=binding["repository_id"],
        run_id=binding["run_id"],
        run_attempt=binding["run_attempt"],
        check_run_id=binding["check_run_id"],
    )
    return {
        "schema": 1,
        "status": "attached",
        "attachment_id": slot,
        "binding_digest": binding_digest(binding=binding),
        "binding": dict(binding),
        **_FALSE,
    }


def observation_receipt(*, attachment_id: str, digest: str, observation: dict[str, Any]) -> str:
    """Bind one observation to its exact attachment, collection and sequence."""
    body = {k: v for k, v in observation.items() if k != "receipt"}
    return _digest(domain=_OBSERVATION, value=[attachment_id, digest, body])


def observation_reply(*, attachment_id: str, observation: dict[str, Any]) -> dict[str, Any]:
    """A committed observation replayed exactly; it grants no capability."""
    return {
        "schema": 1,
        "status": "observed",
        "attachment_id": attachment_id,
        "collection_id": observation["collection_id"],
        "observation": dict(observation),
        **_FALSE,
    }


def attachment_tree(*, record: dict[str, object]) -> dict[str, Any]:
    """Return a validated copy; malformed state refuses instead of becoming empty."""
    raw = record.get("ci_job_attachments")
    if raw is None:
        return {"schema": 1, "attachments": {}, "collections": {}}
    tree = _mapping(value=raw)
    if set(tree) != {"schema", "attachments", "collections"} or tree["schema"] != 1:
        raise ValueError(_INVALID)
    if type(tree["schema"]) is not int:
        raise TypeError(_INVALID)
    attachments = {
        slot: _entry(slot=slot, value=value)
        for slot, value in _mapping(value=tree["attachments"]).items()
    }
    collections = _mapping(value=tree["collections"])
    for collection_id, value in collections.items():
        _collection(collection_id=collection_id, value=value, attachments=attachments)
    seen = [row["collection_id"] for v in attachments.values() for row in v["observations"]]
    if len(seen) != len(set(seen)) or set(seen) != set(collections):
        raise ValueError(_INVALID)
    return {
        "schema": 1,
        "attachments": attachments,
        "collections": {k: dict(_mapping(value=v)) for k, v in collections.items()},
    }


def valid_collection_id(*, value: object) -> bool:
    """Caller-chosen idempotency identity for one exact collection request."""
    return isinstance(value, str) and _COLLECTION.fullmatch(value) is not None


def raw_fact(*, value: object) -> bool:
    """A bounded provider status token, or absent."""
    return value is None or (isinstance(value, str) and _RAW.fullmatch(value) is not None)


def _mapping(*, value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError(_INVALID)
    return dict(cast("dict[str, Any]", value))


def _entry(*, slot: str, value: object) -> dict[str, Any]:
    entry = _mapping(value=value)
    if set(entry) != {"binding", "binding_digest", "receipt", "attached_at", "observations"}:
        raise ValueError(_INVALID)
    binding = _binding(value=entry["binding"])
    receipt = attachment_receipt(binding=binding)
    if (
        receipt["attachment_id"] != slot
        or entry["binding_digest"] != receipt["binding_digest"]
        or entry["receipt"] != receipt
        or type(entry["attached_at"]) is not int
        or not isinstance(entry["observations"], list)
    ):
        raise ValueError(_INVALID)
    rows = cast("list[object]", entry["observations"])
    observations = [
        _observation(slot=slot, digest=receipt["binding_digest"], index=index, value=row)
        for index, row in enumerate(rows)
    ]
    return entry | {"binding": binding, "receipt": receipt, "observations": observations}


def _binding(*, value: object) -> dict[str, Any]:
    binding = _mapping(value=value)
    if (
        frozenset(binding) != BINDING_INTS | BINDING_TEXTS
        or not all(type(binding[k]) is int and binding[k] >= 0 for k in BINDING_INTS)
        or not all(isinstance(binding[k], str) for k in BINDING_TEXTS)
        or not all(_HEX.fullmatch(binding[k]) for k in ("arm_id", "receipt_digest"))
    ):
        raise ValueError(_INVALID)
    return binding


def _observation(*, slot: str, digest: str, index: int, value: object) -> dict[str, Any]:
    row = _mapping(value=value)
    facts = _mapping(value=row.get("facts"))
    if (
        set(row) != {"sequence", "collection_id", "observed_at", "status", "facts", "receipt"}
        or type(row["sequence"]) is not int
        or row["sequence"] != index + 1
        or not valid_collection_id(value=row["collection_id"])
        or type(row["observed_at"]) is not int
        or row["status"] not in OBSERVATION_STATUSES
        or set(facts) != {*_FACTS, "snapshot_status", "reason"}
        or facts["snapshot_status"] not in OBSERVATION_STATUSES
        or not isinstance(facts["reason"], str)
        or not all(raw_fact(value=facts[k]) for k in _FACTS)
        or row["receipt"] != observation_receipt(attachment_id=slot, digest=digest, observation=row)
    ):
        raise ValueError(_INVALID)
    return row | {"facts": facts}


def _collection(*, collection_id: str, value: object, attachments: dict[str, Any]) -> None:
    row = _mapping(value=value)
    entry = attachments.get(row.get("attachment_id", ""))
    sequence = row.get("sequence")
    if (
        set(row) != {"attachment_id", "sequence"}
        or entry is None
        or type(sequence) is not int
        or not 0 < sequence <= len(entry["observations"])
        or entry["observations"][sequence - 1]["collection_id"] != collection_id
    ):
        raise ValueError(_INVALID)
