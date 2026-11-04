"""Separate pre-merge observer readiness from authenticated post-merge CI binding."""

from __future__ import annotations

import hashlib
import json
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
    ObserverArm,
    ObserverArmQuery,
    ObserverRegistration,
    ObserverResult,
)

__all__: list[str] = ["arm_before_merge", "bind_after_merge", "observer_arm_admitted"]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-47ij37
# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-wanebl


def arm_before_merge(
    *,
    directory: Path,
    arm: ObserverArm,
    expected_arm_id: str | None,
    authorize_current: Callable[[ObserverArm], bool],
    released_controller: Callable[[str, str], bool],
) -> ObserverResult:
    """Record real independent readiness without inventing a future master run.

    The canonical current-reader adapter binds the original PR/base/head and full
    generation/owner identity. Its immutable receipt is retained, not interpreted
    as authority merely because it arrived as JSON or a label on a candidate PR.
    """
    if not authorize_current(arm):
        return ObserverResult(status="refused", reason="canonical pre-merge authority unavailable")
    if not arm.authority_receipt or not arm.required_jobs or arm.phase != "repair":
        return ObserverResult(status="refused", reason="incomplete pre-merge observer authority")
    if arm.controller_revision == arm.head_sha or not released_controller(
        arm.controller_release,
        arm.controller_revision,
    ):
        return ObserverResult(
            status="refused", reason="independent released controller unavailable"
        )
    snapshot: dict[str, object] = asdict(arm)
    snapshot["authority_receipt"] = arm.authority_receipt.hex()
    arm_id = hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()
    with repository_lock(directory=directory, repository=arm.repository) as path:
        record = load_record(path=path)
        if record.get("observer_arm_id") == arm_id:
            invalidated = record.get("observer_arm_invalidated") is not None
            return ObserverResult(
                status="refused" if invalidated else "armed",
                reason="pre-merge CI admission invalidated"
                if invalidated
                else "same durable pre-merge arm",
                receipt=None if invalidated else arm_id,
            )
        refusal = _arm_change_refusal(record=record, arm=arm, expected_arm_id=expected_arm_id)
        if refusal is not None:
            return ObserverResult(status="refused", reason=refusal)
        record.update(
            observer_arm_id=arm_id,
            observer_arm=snapshot,
            observer_arm_bound=False,
            observer_arm_invalidated=None,
            registration=None,
        )
        save_record(path=path, record=record)
    return ObserverResult(
        status="armed",
        reason="durable observer ready for this exact PR before merge",
        receipt=arm_id,
    )


def observer_arm_admitted(
    *,
    directory: Path,
    query: ObserverArmQuery,
) -> bool:
    """The merge entrance reads the independent controller's actual receipt.

    Calling this on a candidate-local store does not constitute production
    admission; the released controller owns this read and its protected store.
    """
    with repository_lock(directory=directory, repository=query.repository) as path:
        record = load_record(path=path)
        snapshot = record.get("observer_arm")
        if (
            record.get("observer_arm_id") != query.arm_id
            or record.get("observer_arm_bound")
            or record.get("observer_arm_invalidated") is not None
            or not isinstance(snapshot, dict)
        ):
            return False
        snapshot = cast("dict[str, object]", snapshot)
        receipt = snapshot.get("authority_receipt")
        if (
            not isinstance(receipt, str)
            or hashlib.sha256(bytes.fromhex(receipt)).hexdigest() != query.receipt_digest
        ):
            return False
        return all(
            snapshot.get(key) == value
            for key, value in {
                "repository": query.repository,
                "pr_number": query.pr_number,
                "base_sha": query.base_sha,
                "head_sha": query.head_sha,
            }.items()
        )


def bind_after_merge(
    *,
    directory: Path,
    arm: ObserverArm,
    registration: ObserverRegistration,
    verify_merged_run: Callable[[ObserverArm, ObserverRegistration], bool],
) -> ObserverResult:
    """Fulfill the retained pre-merge grant through authenticated forge reads.

    ``verify_merged_run`` checks the exact armed PR/base/head, complete landed
    change, normal push/master workflow and run/SHA association. The canonical
    pre-merge receipt stays unchanged; observed merge/run data are effect receipts,
    not an invented canonical phase or generation. No fresh tenant/wrapper call
    is required to fulfill the already admitted grant during an outage.
    """
    same_incident = (
        registration.repository == arm.repository
        and registration.incident_item_id == arm.incident_item_id
    )
    same_controller = (registration.controller_release, registration.controller_revision) == (
        arm.controller_release,
        arm.controller_revision,
    )
    same_authority = (
        registration.attempt_id,
        registration.operation_id,
        registration.generation,
        registration.owner,
        registration.phase,
        registration.authority_receipt,
    ) == (
        arm.attempt_id,
        arm.operation_id,
        arm.generation,
        arm.owner,
        arm.phase,
        arm.authority_receipt,
    )
    if not same_incident or not same_controller or not same_authority:
        return ObserverResult(
            status="refused", reason="post-merge binding changed incident or controller"
        )
    if (
        registration.candidate_revision != arm.head_sha
        or registration.required_jobs != arm.required_jobs
    ):
        return ObserverResult(
            status="refused", reason="post-merge binding changed armed candidate scope"
        )
    if not verify_merged_run(arm, registration):
        return ObserverResult(
            status="refused", reason="exact merged PR and master run are not authenticated"
        )
    snapshot: dict[str, object] = asdict(arm)
    snapshot["authority_receipt"] = arm.authority_receipt.hex()
    arm_id = hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()
    with repository_lock(directory=directory, repository=arm.repository) as path:
        record = load_record(path=path)
        if record.get("observer_arm_id") != arm_id:
            return ObserverResult(status="refused", reason="pre-merge observer arm changed")
        previous = read_registration(record=record)
        if previous is not None and previous != registration:
            return ObserverResult(
                status="refused", reason="observer arm is already bound to another master run"
            )
        record.update(
            registration=registration_record(registration=registration), observer_arm_bound=True
        )
        save_record(path=path, record=record)
    return ObserverResult(
        status="admitted", reason="retained arm bound to its authenticated master run"
    )


def _arm_change_refusal(
    *,
    record: dict[str, object],
    arm: ObserverArm,
    expected_arm_id: str | None,
) -> str | None:
    if record.get("observer_arm_id") != expected_arm_id:
        return "pre-merge observer arm compare-and-swap failed"
    previous = record.get("observer_arm")
    if isinstance(previous, dict) and arm.generation <= cast("int", previous["generation"]):
        return "pre-merge observer generation moved backwards"
    actions = cast("dict[str, dict[str, object]]", record.get("actions", {}))
    if any(action.get("status") == "pending" for action in actions.values()):
        return "prior recovery effect requires exact receipt before correction"
    return None
