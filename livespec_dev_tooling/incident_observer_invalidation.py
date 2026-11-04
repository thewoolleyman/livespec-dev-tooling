"""Revoke exact unbound CI admission while retaining authenticated merge recovery.

This is an independent cached-authority fence, not a new incident lifecycle.
An authenticated exact merged-run binding still fulfills the retained grant.
Its caller must be the protected canonical mode writer. Workflow OIDC, every
label writer and actual merge admission still need their normal integration.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, cast

from livespec_dev_tooling._incident_observer_store import (
    load_record,
    read_observer_arm,
    repository_lock,
    save_record,
)
from livespec_dev_tooling._incident_observer_types import ObserverArm
from livespec_dev_tooling.incident_controller_installation import ControllerInstallation
from livespec_dev_tooling.incident_observer_authority import CurrentAuthorityReader

__all__: list[str] = ["ObserverCiInvalidation"]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-wanebl
_FIELDS = frozenset(
    {
        "repository",
        "arm_id",
        "incident_item_id",
        "attempt_id",
        "generation",
        "owner",
        "phase",
        "incident_operation_id",
        "pr_number",
        "base_sha",
        "head_sha",
        "receipt_digest",
        "operation_id",
    }
)
_INVALID_HISTORY = "invalid stored CI invalidation history"
_INVALID_RECEIPT = "invalid stored CI invalidation receipt"


@dataclass(frozen=True, kw_only=True)
class ObserverCiInvalidation:
    """Revoke before effects; recover the same immutable operation after lost replies."""

    installation: ControllerInstallation

    def execute(self, *, payload: dict[str, Any]) -> dict[str, Any]:
        settings = self.installation
        if not _valid_request(payload=payload) or payload["repository"] != settings.repository:
            return _refused(reason="invalid exact CI invalidation request")
        request = payload.copy()
        with repository_lock(directory=settings.state, repository=settings.repository) as path:
            record = load_record(path=path)
            previous = _recovered(record=record, request=request)
            if previous is not None:
                return previous
            arm = _matching_arm(record=record, request=request)
        if arm is None:
            return _refused(reason="exact unbound CI arm unavailable")
        reader = CurrentAuthorityReader(
            command=settings.reader,
            repo=settings.repo,
            release=settings.reader_release,
            installed_reader_approved=lambda release, command: (release, command)
            == (settings.reader_release, settings.reader),
        )
        # Tenant/credential failure must never hold the first-failure effect lock.
        if not reader(arm):
            return _refused(reason="canonical CI invalidation authority stale or unavailable")
        return self._commit(request=request, arm=arm)

    def _commit(self, *, request: dict[str, Any], arm: ObserverArm) -> dict[str, Any]:
        settings = self.installation
        with repository_lock(directory=settings.state, repository=settings.repository) as path:
            record = load_record(path=path)
            previous = _recovered(record=record, request=request)
            if previous is not None:
                return previous
            if _matching_arm(record=record, request=request) != arm:
                return _refused(reason="CI arm changed before invalidation")
            result = _result(request=request)
            history = _history(record=record).copy()
            history[request["operation_id"]] = {"request": request, "result": result}
            record.update(
                ci_invalidations=history,
                observer_arm_invalidated={
                    "operation_id": request["operation_id"],
                    "receipt": result["receipt"],
                },
            )
            save_record(path=path, record=record)
        return result


def _matching_arm(*, record: dict[str, object], request: dict[str, Any]) -> ObserverArm | None:
    arm = read_observer_arm(record=record)
    if (
        arm is None
        or record.get("observer_arm_bound")
        or record.get("observer_arm_invalidated") is not None
    ):
        return None
    expected = {
        "repository": arm.repository,
        "arm_id": record.get("observer_arm_id"),
        "incident_item_id": arm.incident_item_id,
        "attempt_id": arm.attempt_id,
        "generation": arm.generation,
        "owner": arm.owner,
        "phase": arm.phase,
        "incident_operation_id": arm.operation_id,
        "pr_number": arm.pr_number,
        "base_sha": arm.base_sha,
        "head_sha": arm.head_sha,
        "receipt_digest": hashlib.sha256(arm.authority_receipt).hexdigest(),
    }
    return arm if all(request[key] == value for key, value in expected.items()) else None


def _valid_request(*, payload: dict[str, Any]) -> bool:
    return (
        frozenset(payload) == _FIELDS
        and all(
            type(payload[name]) is int and payload[name] > 0 for name in ("generation", "pr_number")
        )
        and all(
            isinstance(payload[name], str) and payload[name]
            for name in _FIELDS - {"generation", "pr_number"}
        )
        and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,255}", payload["operation_id"]) is not None
    )


def _result(*, request: dict[str, Any]) -> dict[str, Any]:
    digest = hashlib.sha256(
        b"incident-ci-invalidation-v1\0"
        + json.dumps(request, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {
        "schema": 1,
        "status": "invalidated",
        "receipt": digest,
        "authorizes_current_effects": False,
    }


def _history(*, record: dict[str, object]) -> dict[str, dict[str, Any]]:
    raw = record.get("ci_invalidations", {})
    if not isinstance(raw, dict):
        raise TypeError(_INVALID_HISTORY)
    history = cast("dict[str, object]", raw)
    for operation, value in history.items():
        if not isinstance(value, dict):
            raise TypeError(_INVALID_RECEIPT)
        entry = cast("dict[str, Any]", value)
        raw_request = entry.get("request")
        if set(entry) != {"request", "result"} or not isinstance(raw_request, dict):
            raise ValueError(_INVALID_RECEIPT)
        request = cast("dict[str, Any]", raw_request)
        if (
            not _valid_request(payload=request)
            or request["operation_id"] != operation
            or json.dumps(entry["result"], sort_keys=True)
            != json.dumps(_result(request=request), sort_keys=True)
        ):
            raise ValueError(_INVALID_RECEIPT)
    return cast("dict[str, dict[str, Any]]", history)


def _recovered(*, record: dict[str, object], request: dict[str, Any]) -> dict[str, Any] | None:
    entry = _history(record=record).get(request["operation_id"])
    if entry is None:
        return None
    if entry["request"] != request:
        return _refused(reason="CI invalidation operation conflicts with immutable request")
    return cast("dict[str, Any]", entry["result"])


def _refused(*, reason: str) -> dict[str, Any]:
    return {"schema": 1, "status": "refused", "reason": reason}
