"""Strict consistency packets for independently authenticated incident CI reads."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, cast

from livespec_dev_tooling._incident_observer_store import read_observer_arm
from livespec_dev_tooling.incident_ci_policy import CiAuthority, CiOutcome
from livespec_dev_tooling.incident_execution import ExecutionContext, Invocation, OperationIdentity
from livespec_dev_tooling.incident_strict_json import IncidentJsonRefusalError, strict_json

__all__: list[str] = ["decode_authority", "decode_outcome", "query_for"]
# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-egy3ri
_SHA = re.compile(r"[0-9a-f]{40}")
_DIGEST = re.compile(r"[0-9a-f]{64}")
_OUTCOMES = {"passed", "failed", "cancelled", "skipped", "timed_out"}


def decode_authority(*, payload: str) -> CiAuthority | None:
    """Decode consistency only; current and admitted endpoints supply authority."""
    try:
        value = strict_json(text=payload, limit=16384)
        data = cast("dict[str, Any]", value) if isinstance(value, dict) else {}
        if (
            set(data) != {"schema", "arm", "observer_arm_id"}
            or type(data["schema"]) is not int
            or data["schema"] != 1
            or not isinstance(data["arm"], dict)
        ):
            return None
        arm_id = hashlib.sha256(json.dumps(data["arm"], sort_keys=True).encode()).hexdigest()
        if data["observer_arm_id"] != arm_id:
            return None
        arm = read_observer_arm(record={"observer_arm": data["arm"], "observer_arm_id": arm_id})
        if arm is None:
            return None
        return CiAuthority(
            context=ExecutionContext(
                mode="expedited-repair",
                invocation=Invocation.ORDINARY,
                identity=OperationIdentity(
                    incident_item_id=arm.incident_item_id,
                    attempt_id=arm.attempt_id,
                    phase=arm.phase,
                    repository=arm.repository,
                    base_sha=arm.base_sha,
                    head_sha=arm.head_sha,
                    operation_id=arm.operation_id,
                ),
            ),
            generation=arm.generation,
            owner=arm.owner,
            pr_number=arm.pr_number,
            receipt_digest=hashlib.sha256(arm.authority_receipt).hexdigest(),
            observer_arm_id=arm_id,
        )
    except (ValueError, IncidentJsonRefusalError, TypeError, KeyError, RecursionError):
        return None


def query_for(*, authority: CiAuthority) -> dict[str, Any]:
    """Project the controller's six-field read query from decoded canonical context."""
    identity = authority.context.identity
    if identity is None:
        message = "incident authority has no identity"
        raise ValueError(message)
    return dict(
        repository=identity.repository,
        arm_id=authority.observer_arm_id,
        pr_number=authority.pr_number,
        base_sha=identity.base_sha,
        head_sha=identity.head_sha,
        receipt_digest=authority.receipt_digest,
    )


def decode_outcome(*, value: object) -> CiOutcome:
    """Reject unknown outcomes and malformed identities before aggregation."""
    data = cast("dict[str, Any]", value) if isinstance(value, dict) else {}
    if (
        set(data) != {"name", "head_sha", "scope", "outcome"}
        or not all(isinstance(v, str) for v in data.values())
        or re.fullmatch(r"check-[a-z0-9-]+", data["name"]) is None
        or _SHA.fullmatch(data["head_sha"]) is None
        or _DIGEST.fullmatch(data["scope"]) is None
        or data["outcome"] not in _OUTCOMES
    ):
        message = "invalid incident CI outcome"
        raise ValueError(message)
    return CiOutcome(**data)
