"""Independent early-failure controller with durable repository action ownership."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import cast

from livespec_dev_tooling._incident_observer_store import (
    load_record,
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
    "admit_observer",
    "handle_job_callback",
    "reconcile_action_receipt",
    "route_ordinary_action",
]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-47ij37
_FAILURES = frozenset({"failure", "timed_out", "action_required", "startup_failure", "stale"})


def admit_observer(
    *,
    directory: Path,
    registration: ObserverRegistration,
    expected_generation: int | None,
    authorize_current: Callable[[ObserverRegistration], bool],
    released_controller: Callable[[str, str], bool],
) -> ObserverResult:
    """Persist the pre-merge observer receipt only after canonical authorization.

    ``authorize_current`` is the canonical current-reader adapter, not a JSON
    parser, label, flag, or historical-reader result. It must bind every identity
    and receipt byte. Build verification belongs to the known-good controller's
    independently provisioned release allowlist, never to candidate code.
    """
    refusal = _admission_refusal(
        registration=registration,
        authorize_current=authorize_current,
        released_controller=released_controller,
    )
    if refusal is not None:
        return ObserverResult(status="refused", reason=refusal)
    with repository_lock(directory=directory, repository=registration.repository) as path:
        record = load_record(path=path)
        previous = read_registration(record=record)
        if previous == registration:
            return ObserverResult(status="admitted", reason="same durable observer receipt")
        actual = None if previous is None else previous.generation
        if actual != expected_generation or (
            actual is not None and registration.generation <= actual
        ):
            return ObserverResult(
                status="refused", reason="observer generation compare-and-swap failed"
            )
        if any(action.get("status") == "pending" for action in _actions(record=record).values()):
            return ObserverResult(
                status="unresolved", reason="prior action requires exact receipt recovery"
            )
        record["registration"] = registration_record(registration=registration)
        save_record(path=path, record=record)
    return ObserverResult(
        status="admitted", reason="durable independent observer armed before merge"
    )


def handle_job_callback(
    *,
    directory: Path,
    delivery: JobCallback,
    webhook_secret: bytes,
    recover: Callable[[RecoveryIntent], str | None],
) -> ObserverResult:
    """Authenticate one early leaf delivery and act without waiting for its run.

    Recovery uses the normally provisioned principal and immutable action id.
    ``None`` means its outcome is unknown, so this controller never retries the
    side effect until exact receipt recovery has established what happened.
    """
    completion = verify_leaf_completion(
        body=delivery.body,
        signature=delivery.signature,
        event=delivery.event,
        delivery_id=delivery.delivery_id,
        secret=webhook_secret,
    )
    if completion is None:
        return ObserverResult(
            status="refused", reason="unauthenticated or invalid early job callback"
        )
    with repository_lock(directory=directory, repository=completion.repository) as path:
        record = load_record(path=path)
        registration = read_registration(record=record)
        if registration is None or not _matches_leaf(
            registration=registration, completion=completion
        ):
            return ObserverResult(
                status="ignored",
                reason="job is outside the registered incident master leaf universe",
            )
        action_id = _action_id(registration=registration)
        actions = _actions(record=record)
        if action_id in actions:
            return ObserverResult(
                status=str(actions[action_id]["status"]),
                reason="existing immutable action; no duplicate effect",
                action_id=action_id,
            )
        intent = RecoveryIntent(
            action_id=action_id, registration=registration, completion=completion
        )
        action: dict[str, object] = {
            "status": "pending",
            "registration": registration_record(registration=registration),
            "completion": asdict(completion),
            "receipt": None,
        }
        actions[action_id] = action
        record["actions"] = actions
        save_record(path=path, record=record)
        # Re-read the SAME independent fence immediately before the side effect,
        # under the lock shared by admission, recovery and ordinary reconciliation.
        if read_registration(record=load_record(path=path)) != registration:
            return ObserverResult(
                status="refused",
                reason="incident generation changed before recovery",
                action_id=action_id,
            )
        receipt = recover(intent)
        if receipt:
            action.update(status="completed", receipt=receipt)
            save_record(path=path, record=record)
        return ObserverResult(
            status="completed" if receipt else "pending",
            reason="first failing required leaf emitted recovery",
            action_id=action_id,
            receipt=receipt,
        )


def reconcile_action_receipt(
    *,
    directory: Path,
    repository: str,
    action_id: str,
    read_exact_receipt: Callable[[str], str | None],
    publish_receipt: Callable[[bytes, str, str], bool],
) -> ObserverResult:
    """Recover exact post-timeout effects and replay their receipts to the tenant.

    An unavailable publisher leaves controller state intact. Successful replay
    is recorded locally, so restarting never invents another lifecycle event.
    """
    with repository_lock(directory=directory, repository=repository) as path:
        record = load_record(path=path)
        action = _actions(record=record).get(action_id)
        if action is None:
            return ObserverResult(status="refused", reason="unknown exact action receipt")
        registration = read_registration(record=action)
        if registration is None:
            return ObserverResult(status="refused", reason="missing immutable action authority")
        receipt = action.get("receipt") or read_exact_receipt(action_id)
        if not isinstance(receipt, str) or not receipt:
            return ObserverResult(
                status="pending",
                reason="exact recovery receipt remains unavailable",
                action_id=action_id,
            )
        action.update(status="completed", receipt=receipt)
        if not action.get("reconciled") and publish_receipt(
            registration.authority_receipt, action_id, receipt
        ):
            action["reconciled"] = True
        save_record(path=path, record=record)
        return ObserverResult(
            status="reconciled" if action.get("reconciled") else "completed",
            reason="exact receipt retained for canonical reconciliation",
            action_id=action_id,
            receipt=receipt,
        )


def route_ordinary_action(
    *,
    directory: Path,
    repository: str,
    head_sha: str,
    run_id: int,
    perform: Callable[[], str],
) -> ObserverResult:
    """The normal reconciler's shared ownership adapter, before rerun/classify.

    Existing ordinary policy runs unchanged when no incident registration exists.
    A recorded incident is owned by the early controller, so the normal policy
    cannot race its revert or delay it behind reruns or fix-forward classification.
    """
    with repository_lock(directory=directory, repository=repository) as path:
        registration = read_registration(record=load_record(path=path))
        if (
            registration is not None
            and registration.head_sha == head_sha
            and registration.run_id == run_id
        ):
            return ObserverResult(
                status="incident-owned",
                reason="independent incident controller owns repository action",
            )
        return ObserverResult(
            status="ordinary", reason="ordinary reconciler policy retained", receipt=perform()
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


def _action_id(*, registration: ObserverRegistration) -> str:
    identity = (
        f"{registration.repository}:{registration.operation_id}:{registration.generation}:recover"
    )
    return hashlib.sha256(identity.encode()).hexdigest()


def _actions(*, record: dict[str, object]) -> dict[str, dict[str, object]]:
    return cast("dict[str, dict[str, object]]", record.setdefault("actions", {}))


def _admission_refusal(
    *,
    registration: ObserverRegistration,
    authorize_current: Callable[[ObserverRegistration], bool],
    released_controller: Callable[[str, str], bool],
) -> str | None:
    if not authorize_current(registration):
        return "canonical current authority unavailable or mismatched"
    if not registration.authority_receipt or not registration.required_jobs:
        return "missing immutable receipt or required leaf universe"
    if (
        registration.controller_revision == registration.candidate_revision
        or not released_controller(
            registration.controller_release,
            registration.controller_revision,
        )
    ):
        return "controller is not an independent known-good released build"
    return None
