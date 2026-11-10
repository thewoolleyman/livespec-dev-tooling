"""Independent early-failure controller with durable repository action ownership."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import cast

from livespec_dev_tooling._incident_observer_ack import (
    record_job_callback,
    recover_recorded_job_callback,
)
from livespec_dev_tooling._incident_observer_store import (
    RepositoryFenceBusyError,
    load_record,
    read_registration,
    registration_record,
    repository_lock,
    save_record,
)
from livespec_dev_tooling._incident_observer_types import (
    JobCallback,
    ObserverRegistration,
    ObserverResult,
    RecoveryIntent,
)

__all__: list[str] = [
    "admit_observer",
    "handle_job_callback",
    "reconcile_action_receipt",
    "route_ordinary_action",
    "route_reconciler_window",
]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-ariayn
# How long the reconciler's ownership question waits for the repository fence.
# A holder that keeps it longer is the observer acting (a recovery principal
# runs with the fence held), so the bounded answer is incident-owned rather
# than a wait that outlasts the reconciler's own step timeout.
RECONCILER_FENCE_WAIT_SECONDS = 10.0


def admit_observer(
    *,
    directory: Path,
    registration: ObserverRegistration,
    expected_generation: int | None,
    authorize_current: Callable[[ObserverRegistration], bool],
    released_controller: Callable[[str, str], bool],
) -> ObserverResult:
    """Persist a standalone master binding after canonical authorization.

    ``authorize_current`` is the canonical current-reader adapter, not a JSON
    parser, label, flag, or historical-reader result. It must bind every identity
    and receipt byte. Build verification belongs to the known-good controller's
    independently provisioned release allowlist, never to candidate code.
    A future merge must instead use the pre-merge arm protocol: a real master
    SHA/run does not exist before that merge, and this low-level operation is
    not evidence of pre-merge readiness.
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
        if record.get("observer_arm_id"):
            return ObserverResult(
                status="refused", reason="armed observer requires authenticated post-merge binding"
            )
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
    return ObserverResult(status="admitted", reason="durable independent master observer bound")


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
    result, intent = record_job_callback(
        directory=directory,
        delivery=delivery,
        webhook_secret=webhook_secret,
    )
    if intent is None:
        return result
    return recover_recorded_job_callback(directory=directory, intent=intent, recover=recover)


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
    This is the exact-run form; the master-health reconciler asks
    ``route_reconciler_window`` because one of its passes can touch any commit of
    the red episode, not one run.
    """
    with repository_lock(directory=directory, repository=repository) as path:
        return _incident_owner(
            record=load_record(path=path),
            owns=lambda registration: (registration.head_sha, registration.run_id)
            == (head_sha, run_id),
        ) or _ordinary(perform=perform)


def route_reconciler_window(
    *,
    directory: Path,
    repository: str,
    window_shas: frozenset[str],
    perform: Callable[[], str],
    wait_seconds: float = RECONCILER_FENCE_WAIT_SECONDS,
) -> ObserverResult:
    """The master-health reconciler's ownership answer for one whole pass.

    A reconciler pass does not act on one run. It reruns the newest failing run,
    reverts the culprit at the bottom of the red episode, and releases or closes
    a revert, so ownership is keyed on every commit the pass can touch: the
    caller's ``window_shas``. A registered incident commit anywhere in that set,
    an unbound pre-merge arm, or a recovery action whose outcome is still unknown
    makes the pass incident-owned. Otherwise ``perform`` runs under the same
    repository fence and its receipt is returned.

    A fence still held after ``wait_seconds`` is the observer acting, so the
    answer is incident-owned and nothing waits on it.
    """
    try:
        with repository_lock(
            directory=directory, repository=repository, wait_seconds=wait_seconds
        ) as path:
            return _incident_owner(
                record=load_record(path=path),
                owns=lambda registration: registration.head_sha in window_shas,
            ) or _ordinary(perform=perform)
    except RepositoryFenceBusyError:
        return ObserverResult(
            status="incident-owned",
            reason="repository action fence is held by the incident observer",
        )


def _ordinary(*, perform: Callable[[], str]) -> ObserverResult:
    return ObserverResult(
        status="ordinary", reason="ordinary reconciler policy retained", receipt=perform()
    )


def _incident_owner(
    *, record: dict[str, object], owns: Callable[[ObserverRegistration], bool]
) -> ObserverResult | None:
    """The incident-owned answer for this record, or None when ordinary policy may act."""
    if record.get("observer_arm_id") and not record.get("observer_arm_bound"):
        return ObserverResult(
            status="incident-owned", reason="pre-merge observer owns repository action"
        )
    if any(action.get("status") == "pending" for action in _actions(record=record).values()):
        return ObserverResult(
            status="incident-owned",
            reason="an incident recovery action with an unknown outcome owns repository action",
        )
    registration = read_registration(record=record)
    if registration is not None and owns(registration):
        return ObserverResult(
            status="incident-owned",
            reason="independent incident controller owns repository action",
        )
    return None


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
