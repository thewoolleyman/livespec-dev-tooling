"""Durable acknowledgement and recovery of one early leaf-failure callback.

The callback is split into two steps so a caller can answer GitHub's webhook
within its 10-second delivery timeout: ``record_job_callback`` authenticates and
durably records the one immutable pending action; ``recover_recorded_job_callback``
then runs the recovery principal for that already-recorded action.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import cast

from livespec_dev_tooling._incident_observer_store import (
    load_record,
    read_observer_arm,
    read_registration,
    registration_record,
    repository_lock,
    save_record,
)
from livespec_dev_tooling._incident_observer_types import (
    JobCallback,
    LeafCompletion,
    ObserverRegistration,
    ObserverResult,
    RecoveryIntent,
)
from livespec_dev_tooling.incident_observer_events import verify_leaf_completion

__all__: list[str] = [
    "record_job_callback",
    "recover_recorded_job_callback",
    "recovery_action_id",
]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-47ij37
_FAILURES = frozenset({"failure", "timed_out", "action_required", "startup_failure", "stale"})


def record_job_callback(
    *, directory: Path, delivery: JobCallback, webhook_secret: bytes
) -> tuple[ObserverResult, RecoveryIntent | None]:
    """Durably accept an authenticated leaf callback before recovery begins."""
    completion = verify_leaf_completion(
        body=delivery.body,
        signature=delivery.signature,
        event=delivery.event,
        delivery_id=delivery.delivery_id,
        secret=webhook_secret,
    )
    if completion is None:
        return (
            ObserverResult(
                status="refused", reason="unauthenticated or invalid early job callback"
            ),
            None,
        )
    with repository_lock(directory=directory, repository=completion.repository) as path:
        record = load_record(path=path)
        registration = read_registration(record=record)
        if registration is None or not _matches_leaf(
            registration=registration, completion=completion
        ):
            return (
                ObserverResult(
                    status="ignored",
                    reason="job is outside the registered incident master leaf universe",
                ),
                None,
            )
        action_id = recovery_action_id(registration=registration)
        actions = _actions(record=record)
        if action_id in actions:
            return (
                ObserverResult(
                    status=str(actions[action_id]["status"]),
                    reason="existing immutable action; no duplicate effect",
                    action_id=action_id,
                ),
                None,
            )
        intent = RecoveryIntent(
            action_id=action_id,
            registration=registration,
            completion=completion,
            observer_arm=read_observer_arm(record=record),
        )
        action: dict[str, object] = {
            "status": "pending",
            "registration": registration_record(registration=registration),
            "completion": asdict(completion),
            "receipt": None,
            "observer_arm": record.get("observer_arm"),
            "observer_arm_id": record.get("observer_arm_id"),
        }
        actions[action_id] = action
        record["actions"] = actions
        save_record(path=path, record=record)
    return (
        ObserverResult(
            status="pending",
            reason="first failing required leaf emitted recovery",
            action_id=action_id,
        ),
        intent,
    )


def recover_recorded_job_callback(
    *, directory: Path, intent: RecoveryIntent, recover: Callable[[RecoveryIntent], str | None]
) -> ObserverResult:
    """Run the principal for an already durable immutable callback action."""
    with repository_lock(directory=directory, repository=intent.registration.repository) as path:
        record = load_record(path=path)
        # Re-read the SAME independent fence immediately before the side effect,
        # under the lock shared by admission, recovery and ordinary reconciliation.
        if read_registration(record=record) != intent.registration:
            return ObserverResult(
                status="refused",
                reason="incident generation changed before recovery",
                action_id=intent.action_id,
            )
        action = _actions(record=record).get(intent.action_id)
        if action is None:
            return ObserverResult(status="refused", reason="unknown immutable recovery action")
        if action.get("status") != "pending":
            recorded_receipt = action.get("receipt")
            return ObserverResult(
                status=str(action["status"]),
                reason="existing immutable action; no duplicate effect",
                action_id=intent.action_id,
                receipt=recorded_receipt if isinstance(recorded_receipt, str) else None,
            )
        receipt = recover(intent)
        if receipt:
            action.update(status="completed", receipt=receipt)
            save_record(path=path, record=record)
        return ObserverResult(
            status="completed" if receipt else "pending",
            reason="first failing required leaf emitted recovery",
            action_id=intent.action_id,
            receipt=receipt,
        )


def _matches_leaf(*, registration: ObserverRegistration, completion: LeafCompletion) -> bool:
    return (
        completion.repository == registration.repository
        and completion.head_sha == registration.head_sha
        and completion.branch == registration.branch
        and completion.run_id == registration.run_id
        and completion.job_name in registration.required_jobs
        and completion.conclusion in _FAILURES
    )


def recovery_action_id(*, registration: ObserverRegistration) -> str:
    """The one immutable revert action of a registered landed attempt, whatever its cause."""
    identity = (
        f"{registration.repository}:{registration.operation_id}:{registration.generation}:recover"
    )
    return hashlib.sha256(identity.encode()).hexdigest()


def _actions(*, record: dict[str, object]) -> dict[str, dict[str, object]]:
    return cast("dict[str, dict[str, object]]", record.setdefault("actions", {}))
