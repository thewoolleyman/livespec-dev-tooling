"""Complete incident inverse execution inside the independent observer fence."""

from __future__ import annotations

import hashlib
import subprocess
import sys
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import cast

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.io import IOFailure, IOResult, IOSuccess  # noqa: E402 — vendor-path-aware import.
from returns.pipeline import is_successful  # noqa: E402
from returns.unsafe import unsafe_perform_io  # noqa: E402

from livespec_dev_tooling._incident_inverse_git import (  # noqa: E402
    build_inverse,
    scope_matches_git,
)
from livespec_dev_tooling._incident_inverse_types import (  # noqa: E402
    InverseConflictRequest,
    InverseForge,
    InversePlan,
    InversePublishRequest,
    InverseRefusal,
    LandedIncident,
    RecoveryOutcome,
)
from livespec_dev_tooling._incident_observer_types import RecoveryIntent  # noqa: E402

__all__: list[str] = [
    "InverseForge",
    "InversePlan",
    "InverseRefusal",
    "LandedIncident",
    "RecoveryOutcome",
    "observer_inverse_callback",
    "plan_incident_inverse",
    "recover_incident_inverse",
]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-lgfo3v
_CAS_ATTEMPTS = 3


def plan_incident_inverse(
    *, repo_root: Path, scope: LandedIncident, expected_head: str
) -> IOResult[InversePlan, InverseRefusal]:
    """Build the complete reverse patch against current master without checkout."""
    try:
        valid = scope_matches_git(root=repo_root, scope=scope, expected_head=expected_head)
    except (OSError, subprocess.SubprocessError, UnicodeError) as error:
        return IOFailure(InverseRefusal(code="invalid-incident-scope", detail=str(error)))
    if not valid:
        return IOFailure(
            InverseRefusal(
                code="invalid-incident-scope",
                detail="complete landed chain, trees and patch must match authenticated scope",
            )
        )
    try:
        return IOSuccess(build_inverse(root=repo_root, scope=scope, expected_head=expected_head))
    except subprocess.CalledProcessError as error:
        return IOFailure(
            InverseRefusal(
                code=(
                    "rollback-conflict"
                    if error.returncode == 1 and "apply" in error.cmd
                    else "inverse-unavailable"
                ),
                detail=(error.stderr or b"Git inverse construction failed").decode(
                    errors="replace"
                ),
            )
        )
    except (OSError, subprocess.SubprocessError, UnicodeError) as error:
        return IOFailure(InverseRefusal(code="inverse-unavailable", detail=str(error)))


def recover_incident_inverse(
    *,
    repo_root: Path,
    intent: RecoveryIntent,
    forge: InverseForge,
    resume_unresolved: bool = False,
) -> IOResult[RecoveryOutcome, InverseRefusal]:
    """Resolve prior effects then execute under the caller-held observer lock.

    The adapter is an independently provisioned scoped recovery principal, not
    the tenant, credential wrapper, ambient incident flag or CI-gated PR route.
    Observer persists the immutable intent before calling this function. A lost
    or unknown publication response is NEVER retried here. Only an explicit
    no-effect head-moved CAS result permits recomputation with the SAME action.

    ``resume_unresolved`` is the one exception, and only an operator's explicit
    `/reconcile` request sets it. It skips the refusal an unresolved lookup raises,
    so the same action reaches the principal's `publish`, which settles the open
    attempt from forge facts and re-sends its one recorded commit. Exactly-one is
    the principal's ledger's rule, so a caller cannot mint a second revert this way.
    """
    try:
        prior = None if resume_unresolved else forge.read_exact_receipt(intent=intent)
        if prior:
            return IOSuccess(
                RecoveryOutcome(
                    status="recovered", reason="exact prior action effect", receipt=prior
                )
            )
        scope = forge.landed_incident(intent=intent)
        if scope is None:
            return IOFailure(
                InverseRefusal(
                    code="inverse-scope-unavailable",
                    detail="authenticated complete landed PR scope unavailable",
                )
            )
        if not _authorized(intent=intent, scope=scope, forge=forge):
            return IOFailure(
                InverseRefusal(
                    code="inverse-authority-refused",
                    detail="retained observer grant and scoped recovery principal required",
                )
            )
        return _execute(repo_root=repo_root, intent=intent, scope=scope, forge=forge)
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        return IOFailure(InverseRefusal(code="inverse-unavailable", detail=str(error)))


def _authorized(*, intent: RecoveryIntent, scope: LandedIncident, forge: InverseForge) -> bool:
    registration = intent.registration
    return (
        scope.repository == registration.repository
        and scope.merge_sha == registration.head_sha
        and scope.authority_sha256 == hashlib.sha256(registration.authority_receipt).hexdigest()
        and bool(intent.action_id and registration.owner and registration.authority_receipt)
        and _matches_arm(intent=intent, scope=scope)
        and forge.authorize_inverse(intent=intent, scope=scope)
    )


def _matches_arm(*, intent: RecoveryIntent, scope: LandedIncident) -> bool:
    arm: object = asdict(intent).get("observer_arm")
    if arm is None:
        # Legacy post-merge registrations still require the separate principal authorization.
        return True
    if not isinstance(arm, dict):
        return False
    data = cast("dict[str, object]", arm)
    registration = asdict(intent.registration)
    return (
        all(
            data.get(key) == registration[key]
            for key in (
                "repository",
                "incident_item_id",
                "attempt_id",
                "operation_id",
                "generation",
                "owner",
                "phase",
                "authority_receipt",
                "controller_release",
                "controller_revision",
            )
        )
        and data.get("pr_number") == scope.pr_number
        and data.get("base_sha") == scope.original_base_sha
        and data.get("head_sha") == scope.original_head_sha
    )


def _execute(
    *, repo_root: Path, intent: RecoveryIntent, scope: LandedIncident, forge: InverseForge
) -> IOResult[RecoveryOutcome, InverseRefusal]:
    for _attempt in range(_CAS_ATTEMPTS):
        head = forge.read_master_head(
            repository=scope.repository, branch=intent.registration.branch
        )
        planned = plan_incident_inverse(repo_root=repo_root, scope=scope, expected_head=head)
        if not is_successful(planned):
            refusal = unsafe_perform_io(planned.failure())
            if refusal.code != "rollback-conflict":
                return IOFailure(refusal)
            return _conflict(
                intent=intent, scope=scope, head=head, reason=refusal.detail, forge=forge
            )
        plan = unsafe_perform_io(planned.unwrap())
        result = forge.publish_inverse(
            request=InversePublishRequest(
                intent=intent,
                plan=plan,
                message=(
                    f"Revert complete incident PR #{scope.pr_number}\n\n"
                    f"Incident-Action: {intent.action_id}\n"
                    f"Incident-Owner: {intent.registration.owner}\n"
                ),
            )
        )
        if result.status == "head-moved":
            continue
        receipt = forge.read_exact_receipt(intent=intent)
        if receipt:
            return IOSuccess(
                RecoveryOutcome(
                    status="reverted",
                    reason="exact action effect receipt confirmed",
                    receipt=receipt,
                )
            )
        return IOSuccess(
            RecoveryOutcome(
                status="pending",
                reason="publication outcome requires exact effect receipt; no retry",
            )
        )
    return IOSuccess(
        RecoveryOutcome(
            status="pending", reason="bounded CAS movement; same immutable action remains owned"
        )
    )


def _conflict(
    *, intent: RecoveryIntent, scope: LandedIncident, head: str, reason: str, forge: InverseForge
) -> IOResult[RecoveryOutcome, InverseRefusal]:
    receipt = forge.record_conflict(
        request=InverseConflictRequest(
            intent=intent,
            scope=scope,
            expected_head=head,
            reason=reason,
            receipt=f"rollback-conflict:{intent.action_id}:owner:{intent.registration.owner}:head:{head}",
        )
    )
    return IOSuccess(
        RecoveryOutcome(
            status="rollback-conflict" if receipt else "pending",
            reason="overlapping later work requires identified owner resolution",
            receipt=receipt,
        )
    )


def observer_inverse_callback(
    *, repo_root: Path, forge: InverseForge, resume_unresolved: bool = False
) -> Callable[[RecoveryIntent], str | None]:
    """Adapt to receipt-or-pending without reacquiring the observer's OS lock."""

    def callback(*, intent: RecoveryIntent) -> str | None:
        result = recover_incident_inverse(
            repo_root=repo_root, intent=intent, forge=forge, resume_unresolved=resume_unresolved
        )
        return unsafe_perform_io(result.unwrap()).receipt if is_successful(result) else None

    return lambda intent: callback(intent=intent)
