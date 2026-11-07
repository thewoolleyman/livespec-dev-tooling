"""Revert a landed incident attempt the canonical chain reopened for a related regression.

`POST /recover` is the observer's authenticated control route for a regression
seen on another pull request or on master. The orchestrator's regression reopen
moves the same incident into a fenced `reverting` generation, and nothing else
tells the trusted controller to revert the landed attempt: a leaf callback acts
only on the registered master run. This route takes that reopened-chain
receipt, verifies it through the installed canonical current reader, and hands
the registered landed attempt to the SAME `recover` callback a failing master
leaf uses, so one trusted controller performs every revert.

The action id is the registration's (`recovery_action_id`), so a leaf failure
and a reopen of the same landed attempt share one immutable action and one
revert. A replayed receipt answers its retained action from protected state
before any tenant read, including after a restart.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from typing import Any, cast

from livespec_dev_tooling._incident_observer_store import (
    load_record,
    read_observer_arm,
    read_registration,
    registration_record,
    repository_lock,
    save_record,
)
from livespec_dev_tooling._incident_observer_types import (
    ObserverRegistration,
    RecoveryIntent,
    RegressionReopen,
)
from livespec_dev_tooling.incident_controller_installation import ControllerInstallation
from livespec_dev_tooling.incident_observer import recovery_action_id
from livespec_dev_tooling.incident_observer_authority import CurrentAuthorityReader

__all__: list[str] = ["ObserverRecovery"]

_TEXTS = ("repository", "incident_item_id", "attempt_id", "phase", "operation_id", "owner")
_FIELDS = frozenset({*_TEXTS, "generation", "authority_receipt"})
_REVERTING = "reverting"


@dataclass(frozen=True, kw_only=True)
class ObserverRecovery:
    """One revert per reopened landed attempt, through the leaf callback's recovery path."""

    installation: ControllerInstallation
    recover: Callable[[RecoveryIntent], str | None]

    def execute(self, *, payload: dict[str, Any]) -> dict[str, Any]:
        receipt = _receipt(payload=payload)
        if isinstance(receipt, str):
            return _refused(reason=receipt)
        regression, authority = receipt
        settings = self.installation
        with repository_lock(directory=settings.state, repository=settings.repository) as path:
            record = load_record(path=path)
            replayed = _replayed(record=record, regression=regression)
            if replayed is not None:
                return replayed
            landed = _landed(record=record, payload=payload)
        if isinstance(landed, str):
            return _refused(reason=landed)
        reader = CurrentAuthorityReader(
            command=settings.reader,
            repo=settings.repo,
            release=settings.reader_release,
            installed_reader_approved=lambda release, command: (release, command)
            == (settings.reader_release, settings.reader),
        )
        subject = replace(
            landed,
            attempt_id=regression.attempt_id,
            operation_id=regression.operation_id,
            generation=regression.generation,
            owner=regression.owner,
            phase=_REVERTING,
            authority_receipt=authority,
        )
        # Tenant/credential failure must never hold the first-failure effect lock.
        if not reader(subject):
            return _refused(reason="canonical reopened-chain receipt is stale or unavailable")
        return self._commit(registration=landed, regression=regression)

    def _commit(
        self, *, registration: ObserverRegistration, regression: RegressionReopen
    ) -> dict[str, Any]:
        settings = self.installation
        with repository_lock(directory=settings.state, repository=settings.repository) as path:
            record = load_record(path=path)
            replayed = _replayed(record=record, regression=regression)
            if replayed is not None:
                return replayed
            if read_registration(record=record) != registration or _armed(record=record):
                return _refused(reason="incident registration changed before recovery")
            action_id = recovery_action_id(registration=registration)
            actions = _actions(record=record)
            if action_id in actions:
                return _existing(action_id=action_id, action=actions[action_id])
            action: dict[str, object] = {
                "status": "pending",
                "registration": registration_record(registration=registration),
                "completion": None,
                "regression": asdict(regression),
                "receipt": None,
                "observer_arm": record.get("observer_arm"),
                "observer_arm_id": record.get("observer_arm_id"),
            }
            actions[action_id] = action
            save_record(path=path, record=record)
            receipt = self.recover(
                RecoveryIntent(
                    action_id=action_id,
                    registration=registration,
                    observer_arm=read_observer_arm(record=record),
                    regression=regression,
                )
            )
            if receipt:
                action.update(status="completed", receipt=receipt)
                save_record(path=path, record=record)
        return {
            "status": "completed" if receipt else "pending",
            "reason": "reopened incident attempt emitted recovery",
            "action_id": action_id,
            "receipt": receipt,
        }


def _receipt(*, payload: dict[str, Any]) -> tuple[RegressionReopen, bytes] | str:
    if (
        frozenset(payload) != _FIELDS
        or not all(isinstance(payload[name], str) and payload[name] for name in _TEXTS)
        or type(payload["generation"]) is not int
        or payload["generation"] <= 0
        or not isinstance(payload["authority_receipt"], str)
    ):
        return "invalid reopened-chain receipt"
    if payload["phase"] != _REVERTING:
        return "reopened incident attempt is not in phase reverting"
    try:
        authority = bytes.fromhex(payload["authority_receipt"])
    except ValueError:
        return "invalid reopened-chain receipt"
    if not authority:
        return "invalid reopened-chain receipt"
    regression = RegressionReopen(
        attempt_id=payload["attempt_id"],
        operation_id=payload["operation_id"],
        generation=payload["generation"],
        owner=payload["owner"],
        receipt_digest=hashlib.sha256(authority).hexdigest(),
    )
    return regression, authority


def _landed(*, record: dict[str, object], payload: dict[str, Any]) -> ObserverRegistration | str:
    registration = read_registration(record=record)
    if registration is None:
        return "no landed incident attempt is registered"
    if payload["incident_item_id"] != registration.incident_item_id:
        return "reopened-chain receipt names another incident"
    if payload["generation"] <= registration.generation:
        return "reopened-chain receipt generation is stale"
    if _armed(record=record):
        return "armed observer awaits post-merge binding"
    return registration


def _armed(*, record: dict[str, object]) -> bool:
    return bool(record.get("observer_arm_id")) and not record.get("observer_arm_bound")


def _replayed(*, record: dict[str, object], regression: RegressionReopen) -> dict[str, Any] | None:
    retained = asdict(regression)
    for action_id, action in _actions(record=record).items():
        if action.get("regression") == retained:
            return _existing(action_id=action_id, action=action)
    return None


def _existing(*, action_id: str, action: dict[str, object]) -> dict[str, Any]:
    return {
        "status": str(action["status"]),
        "reason": "existing immutable action; no duplicate effect",
        "action_id": action_id,
        "receipt": action.get("receipt"),
    }


def _actions(*, record: dict[str, object]) -> dict[str, dict[str, object]]:
    return cast("dict[str, dict[str, object]]", record.setdefault("actions", {}))


def _refused(*, reason: str) -> dict[str, Any]:
    return {"status": "refused", "reason": reason}
