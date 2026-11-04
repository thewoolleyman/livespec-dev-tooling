"""Exact canonical packets and retained-action authentication for recovery."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from typing import Any, cast

from livespec_dev_tooling._incident_inverse_types import (
    InverseConflictRequest,
    InversePlan,
    InversePublishRequest,
)
from livespec_dev_tooling._incident_observer_store import read_observer_arm, read_registration
from livespec_dev_tooling._incident_observer_types import (
    LeafCompletion,
    ObserverRegistration,
    RecoveryIntent,
)
from livespec_dev_tooling._incident_recovery_journal_types import RetainedAction
from livespec_dev_tooling._incident_recovery_journal_values import JournalValues

__all__: list[str] = ["JournalCodec"]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-dln3ac
_FAILURES = frozenset({"failure", "timed_out", "action_required", "startup_failure", "stale"})


def _registration(*, raw: Any) -> Any:
    data = JournalValues.object(value=raw).copy()
    receipt = JournalValues.bytes(value=data.get("authority_receipt"))
    data["authority_receipt"] = receipt.hex()
    registration = cast("ObserverRegistration", read_registration(record={"registration": data}))
    identity = asdict(registration)
    if not (
        all(JournalValues.positive(value=identity[key]) for key in ("generation", "run_id"))
        and all(
            JournalValues.sha(value=identity[key])
            for key in ("head_sha", "controller_revision", "candidate_revision")
        )
        and receipt
        and registration.required_jobs
        and all(JournalValues.text(value=job) for job in registration.required_jobs)
        and len(set(registration.required_jobs)) == len(registration.required_jobs)
        and all(
            JournalValues.text(value=value) for value in identity.values() if isinstance(value, str)
        )
        and registration.branch == "master"
    ):
        message = "invalid recovery registration"
        raise ValueError(message)
    return registration


def _arm(*, raw: Any) -> Any:
    if raw is None:
        return None
    data = JournalValues.object(value=raw).copy()
    data["authority_receipt"] = JournalValues.bytes(value=data.get("authority_receipt")).hex()
    arm_id = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
    return read_observer_arm(record={"observer_arm": data, "observer_arm_id": arm_id})


def _completion(*, raw: Any) -> LeafCompletion:
    data = JournalValues.object(value=raw)
    fields = {
        "delivery_id",
        "repository",
        "head_sha",
        "branch",
        "run_id",
        "job_id",
        "job_name",
        "conclusion",
    }
    if not (
        set(data) == fields
        and all(JournalValues.positive(value=data[key]) for key in ("run_id", "job_id"))
        and all(JournalValues.text(value=data[key]) for key in fields - {"run_id", "job_id"})
        and JournalValues.sha(value=data["head_sha"])
        and data["conclusion"] in _FAILURES
    ):
        message = "invalid recovery completion"
        raise ValueError(message)
    return LeafCompletion(**data)


def _matching_arm(*, intent: RecoveryIntent) -> bool:
    arm, registration = intent.observer_arm, intent.registration
    if arm is None:
        return True
    fields = (
        "repository",
        "incident_item_id",
        "attempt_id",
        "operation_id",
        "generation",
        "owner",
        "phase",
        "required_jobs",
        "controller_release",
        "controller_revision",
        "authority_receipt",
    )
    return (
        all(getattr(arm, name) == getattr(registration, name) for name in fields)
        and JournalValues.positive(value=arm.pr_number)
        and JournalValues.sha(value=arm.base_sha)
        and JournalValues.sha(value=arm.head_sha)
        and arm.head_sha == registration.candidate_revision
    )


def _publish_request(*, data: dict[str, Any], intent: RecoveryIntent) -> InversePublishRequest:
    plan = JournalValues.object(value=data.get("plan"))
    if set(data) != {"intent", "plan", "message"} or set(plan) != {
        "scope",
        "expected_head",
        "tree_sha",
        "inverse_patch",
    }:
        message = "invalid exact recovery reservation"
        raise ValueError(message)
    scope = JournalValues.scope(raw=plan["scope"])
    if not (
        JournalValues.scope_matches(scope=scope, intent=intent)
        and JournalValues.sha(value=plan["expected_head"])
        and JournalValues.sha(value=plan["tree_sha"])
        and JournalValues.text(value=data["message"])
    ):
        message = "unbound recovery reservation"
        raise ValueError(message)
    return InversePublishRequest(
        intent=intent,
        plan=InversePlan(
            scope=scope,
            expected_head=plan["expected_head"],
            tree_sha=plan["tree_sha"],
            inverse_patch=JournalValues.bytes(value=plan["inverse_patch"]),
        ),
        message=data["message"],
    )


class JournalCodec:
    """Canonical existing process protocol, without introducing journal authority."""

    @staticmethod
    def decode(*, raw: bytes, limit: int) -> Any:
        return JournalValues.decode(raw=raw, limit=limit)

    @staticmethod
    def canonical(*, value: Any) -> bytes:
        return JournalValues.canonical(value=value)

    @staticmethod
    def wire(*, value: Any) -> dict[str, Any]:
        return JournalValues.wire(value=value)

    @staticmethod
    def intent(*, raw: Any) -> RecoveryIntent:
        data = JournalValues.object(value=raw)
        if set(data) != {
            "action_id",
            "registration",
            "completion",
            "observer_arm",
        } or not JournalValues.digest(value=data.get("action_id")):
            message = "invalid recovery intent"
            raise ValueError(message)
        registration = _registration(raw=data["registration"])
        intent = RecoveryIntent(
            action_id=data["action_id"],
            registration=registration,
            completion=_completion(raw=data["completion"]),
            observer_arm=_arm(raw=data["observer_arm"]),
        )
        completion = intent.completion
        action_key = (
            f"{registration.repository}:"
            f"{registration.operation_id}:{registration.generation}:recover"
        )
        if not (
            intent.action_id == hashlib.sha256(action_key.encode()).hexdigest()
            and (completion.repository, completion.head_sha, completion.branch, completion.run_id)
            == (
                registration.repository,
                registration.head_sha,
                registration.branch,
                registration.run_id,
            )
            and completion.job_name in registration.required_jobs
            and _matching_arm(intent=intent)
        ):
            message = "recovery intent does not match retained grant"
            raise ValueError(message)
        return intent

    @staticmethod
    def retained(*, record: dict[str, Any], intent: RecoveryIntent) -> RetainedAction | None:
        actions = JournalValues.object(value=record.get("actions"))
        action = JournalValues.object(value=actions.get(intent.action_id))
        if not action:
            return None
        registration = read_registration(record=action)
        arm = read_observer_arm(record=action)
        if registration is None:
            message = "retained action registration missing"
            raise ValueError(message)
        restored = RecoveryIntent(
            action_id=intent.action_id,
            registration=registration,
            completion=_completion(raw=action.get("completion")),
            observer_arm=arm,
        )
        raw = JournalCodec.wire(value=asdict(restored))
        _ = JournalCodec.intent(raw=raw)
        if JournalCodec.canonical(value=raw) != JournalCodec.canonical(value=asdict(intent)):
            return None
        status, receipt = action.get("status"), action.get("receipt")
        if (
            status not in {"pending", "completed"}
            or (status == "pending" and receipt is not None)
            or (status == "completed" and not JournalValues.text(value=receipt))
        ):
            message = "invalid retained action disposition"
            raise ValueError(message)
        return RetainedAction(intent=raw, status=status, receipt=receipt)

    @staticmethod
    def request(*, operation: str, raw: Any) -> InversePublishRequest | InverseConflictRequest:
        data = JournalValues.object(value=raw)
        intent = JournalCodec.intent(raw=data.get("intent"))
        if operation == "reserve":
            return _publish_request(data=data, intent=intent)
        if set(data) != {"intent", "scope", "expected_head", "reason", "receipt"}:
            message = "invalid owned conflict request"
            raise ValueError(message)
        scope = JournalValues.scope(raw=data["scope"])
        expected = (
            f"rollback-conflict:{intent.action_id}:owner:{intent.registration.owner}:"
            f"head:{data['expected_head']}"
        )
        if not (
            JournalValues.scope_matches(scope=scope, intent=intent)
            and JournalValues.sha(value=data["expected_head"])
            and JournalValues.text(value=data["reason"])
            and data["receipt"] == expected
        ):
            message = "unbound owned conflict request"
            raise ValueError(message)
        return InverseConflictRequest(
            intent=intent,
            scope=scope,
            expected_head=data["expected_head"],
            reason=data["reason"],
            receipt=expected,
        )
