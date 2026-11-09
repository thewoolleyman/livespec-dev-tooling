"""Durable acknowledgement and recovery of one early leaf-failure callback.

The callback is split into two steps so a caller can answer GitHub's webhook
within its 10-second delivery timeout: ``record_job_callback`` authenticates and
durably records the one immutable pending action; ``recover_recorded_job_callback``
then runs the recovery principal for that already-recorded action.

The principal MUST run with the observer repository fence held: the installed
principal refuses ``publish`` and ``conflict`` without a borrowed observer fence,
and a refusal is never retried, so a principal run outside the fence would leave
the action pending forever behind a clean acknowledgement. The recovery step
therefore acquires the fence itself and holds it across the principal and the
action's settlement. The acknowledgement waits for the fence only a bounded time and
otherwise answers from the durable record without it.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import cast

from livespec_dev_tooling._incident_observer_store import (
    RepositoryFenceBusyError,
    load_record,
    read_observer_arm,
    read_registration,
    record_path,
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
_EMITTED = "first failing required leaf emitted recovery"
_NO_DUPLICATE = "existing immutable action; no duplicate effect"
_RAISED = "recovery principal raised before returning a receipt; outcome unknown"
_NO_RECEIPT = "recovery principal returned no receipt; outcome unknown"


def record_job_callback(
    *,
    directory: Path,
    delivery: JobCallback,
    webhook_secret: bytes,
    fence_wait_seconds: float | None = None,
) -> tuple[ObserverResult, RecoveryIntent | None]:
    """Durably accept an authenticated leaf callback before recovery begins.

    ``fence_wait_seconds`` bounds the wait for the repository fence. When another
    holder, typically a running principal, keeps it past the bound, the answer is read
    from the atomically replaced durable record without the fence: an action already
    recorded for this incident is answered as such, and only a failure with no recorded
    action is reported ``unavailable`` so the delivery can be redelivered.
    """
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
    repository = completion.repository
    try:
        with repository_lock(
            directory=directory, repository=repository, wait_seconds=fence_wait_seconds
        ) as path:
            record = load_record(path=path)
            decided = _decide(record=record, completion=completion)
            if isinstance(decided, ObserverResult):
                return decided, None
            actions = _actions(record=record)
            actions[decided.action_id] = {
                "status": "pending",
                "registration": registration_record(registration=decided.registration),
                "completion": asdict(completion),
                "receipt": None,
                "observer_arm": record.get("observer_arm"),
                "observer_arm_id": record.get("observer_arm_id"),
            }
            record["actions"] = actions
            save_record(path=path, record=record)
    except RepositoryFenceBusyError:
        decided = _decide(
            record=load_record(path=record_path(directory=directory, repository=repository)),
            completion=completion,
        )
        if isinstance(decided, ObserverResult):
            return decided, None
        return (
            ObserverResult(
                status="unavailable",
                reason="observer repository fence is busy; redeliver this callback",
                action_id=decided.action_id,
            ),
            None,
        )
    return ObserverResult(status="pending", reason=_EMITTED, action_id=decided.action_id), decided


def recover_recorded_job_callback(
    *, directory: Path, intent: RecoveryIntent, recover: Callable[[RecoveryIntent], str | None]
) -> ObserverResult:
    """Run the principal for an already durable immutable callback action.

    The repository fence is held across the pre-effect fence re-read, the principal
    and the action's settlement, as the installed principal requires. A redelivery
    meanwhile is answered from the already durable pending action by the bounded
    acknowledgement, so it never queues behind the principal.

    A principal that raises or returns no receipt leaves the action ``pending``, the
    state exact receipt recovery resolves, and marks it durably with a
    ``recovery_failure`` reason. The side effect is never retried here.
    """
    repository = intent.registration.repository
    with repository_lock(directory=directory, repository=repository) as path:
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
                reason=_NO_DUPLICATE,
                action_id=intent.action_id,
                receipt=recorded_receipt if isinstance(recorded_receipt, str) else None,
            )
        returned = False
        try:
            receipt = recover(intent)
            returned = True
        finally:
            if not returned:
                _settle(path=path, action_id=intent.action_id, recovery_failure=_RAISED)
        if receipt:
            _settle(path=path, action_id=intent.action_id, status="completed", receipt=receipt)
        else:
            _settle(
                path=path,
                action_id=intent.action_id,
                recovery_failure=_NO_RECEIPT,
            )
    return ObserverResult(
        status="completed" if receipt else "pending",
        reason=_EMITTED,
        action_id=intent.action_id,
        receipt=receipt,
    )


def _decide(
    *, record: dict[str, object], completion: LeafCompletion
) -> ObserverResult | RecoveryIntent:
    """The answer for a delivery that needs no write, else the intent to record."""
    registration = read_registration(record=record)
    if registration is None or not _matches_leaf(registration=registration, completion=completion):
        return ObserverResult(
            status="ignored",
            reason="job is outside the registered incident master leaf universe",
        )
    action_id = recovery_action_id(registration=registration)
    existing = _actions(record=record).get(action_id)
    if existing is not None:
        return ObserverResult(
            status=str(existing["status"]), reason=_NO_DUPLICATE, action_id=action_id
        )
    return RecoveryIntent(
        action_id=action_id,
        registration=registration,
        completion=completion,
        observer_arm=read_observer_arm(record=record),
    )


def _settle(*, path: Path, action_id: str, **fields: object) -> None:
    """Durably update one action under the fence the caller already holds."""
    record = load_record(path=path)
    _actions(record=record)[action_id].update(fields)
    save_record(path=path, record=record)


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
