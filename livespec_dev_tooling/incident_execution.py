"""Resolve trusted incident execution mode before any gate chooses work.

Incident flags are deliberately not a gate-local switch.  A caller resolves an
immutable operation identity once, then passes the resulting context across its
hook, dispatcher, CI, and recovery boundaries.  This keeps a normal child from
re-reading a leaked ambient flag and silently acquiring weaker policy.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import cast

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.pipeline import is_successful  # noqa: E402  — vendor-path-aware import.
from returns.result import Failure, Result, Success  # noqa: E402  — vendor-path-aware import.

from livespec_dev_tooling._incident_execution_types import (  # noqa: E402
    ExecutionContext,
    ExecutionMode,
    IncidentConfigurationRefusal,
    IncidentResolution,
    Invocation,
    OperationIdentity,
)

__all__: list[str] = [
    "EXPEDITED_INCIDENT_RESPONSE",
    "EXPEDITED_INCIDENT_RESPONSE_REVERT",
    "ExecutionContext",
    "ExecutionMode",
    "IncidentConfigurationRefusal",
    "IncidentResolution",
    "Invocation",
    "OperationIdentity",
    "parse_incident_truth_value",
    "resolve_execution_context",
    "validate_execution_context",
]

EXPEDITED_INCIDENT_RESPONSE = "EXPEDITED_INCIDENT_RESPONSE"
EXPEDITED_INCIDENT_RESPONSE_REVERT = "EXPEDITED_INCIDENT_RESPONSE_REVERT"

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"", "0", "false", "no", "off"})
_TRUE = True
_FALSE = False
_FIRST_PRINTABLE = 32
_DELETE_CONTROL = 127
# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-sh3vz3
_OBJECT_ID = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
_REPOSITORY = re.compile(r"[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+\Z")


def parse_incident_truth_value(
    *, name: str, value: str | None
) -> Result[bool, IncidentConfigurationRefusal]:
    """Parse one documented incident flag without treating typos as false.

    Missing and explicit false values are normal.  Any other spelling is a
    named configuration refusal, so an operator cannot accidentally choose a
    normal gate after intending an incident operation.
    """
    normalized = "" if value is None else value.strip().casefold()
    if normalized in _TRUE_VALUES:
        return Success(_TRUE)
    if normalized in _FALSE_VALUES:
        return Success(_FALSE)
    return Failure(
        IncidentConfigurationRefusal(
            code="invalid-incident-flag",
            detail=(
                f"{name} must be one of 1, true, yes, on, 0, false, no, off, or unset; "
                f"received {value!r}"
            ),
        )
    )


def _identity_refusal(*, identity: OperationIdentity | None) -> IncidentConfigurationRefusal | None:
    """Name the missing identity component, rather than accepting a partial receipt."""
    if identity is None:
        return IncidentConfigurationRefusal(
            code="missing-incident-identity",
            detail="an expedited incident operation requires its immutable operation identity",
        )
    if not isinstance(cast(object, identity), OperationIdentity):
        return IncidentConfigurationRefusal(
            code="invalid-incident-identity",
            detail="identity must be an OperationIdentity",
        )
    for field_name, value in (
        ("incident_item_id", identity.incident_item_id),
        ("attempt_id", identity.attempt_id),
        ("phase", identity.phase),
        ("repository", identity.repository),
        ("base_sha", identity.base_sha),
        ("head_sha", identity.head_sha),
        ("operation_id", identity.operation_id),
    ):
        if (
            not isinstance(cast(object, value), str)
            or not value
            or value != value.strip()
            or any(
                ord(character) < _FIRST_PRINTABLE or ord(character) == _DELETE_CONTROL
                for character in value
            )
        ):
            return IncidentConfigurationRefusal(
                code="invalid-incident-identity",
                detail=f"incident identity {field_name} must be nonempty, trimmed and control-free",
            )
    if (
        not _OBJECT_ID.fullmatch(identity.base_sha)
        or not _OBJECT_ID.fullmatch(identity.head_sha)
        or not _REPOSITORY.fullmatch(identity.repository)
        or identity.repository.split("/")[1] in {".", ".."}
    ):
        return IncidentConfigurationRefusal(
            code="invalid-incident-identity",
            detail="identity requires owner/repository and full Git object IDs",
        )
    return None


def _revert_refusal(*, identity: OperationIdentity) -> IncidentConfigurationRefusal | None:
    """Require an emergency operation to name the merge it is allowed to undo."""
    if identity.recorded_incident_merge_sha is None:
        return IncidentConfigurationRefusal(
            code="missing-recorded-incident-merge",
            detail="an emergency revert requires the recorded incident merge SHA it reverses",
        )
    if not isinstance(
        cast(object, identity.recorded_incident_merge_sha), str
    ) or not _OBJECT_ID.fullmatch(identity.recorded_incident_merge_sha):
        return IncidentConfigurationRefusal(
            code="invalid-recorded-incident-merge",
            detail="an emergency revert requires a full recorded incident merge object ID",
        )
    return None


def _success(*, context: ExecutionContext) -> IncidentResolution:
    """Construct a successful resolution boundary value."""
    return IncidentResolution(result=Success(context))


def _failure(*, refusal: IncidentConfigurationRefusal) -> IncidentResolution:
    """Construct a named configuration-refusal boundary value."""
    return IncidentResolution(result=Failure(refusal))


def _incident_mode(*, environ: Mapping[str, str]) -> Result[str, IncidentConfigurationRefusal]:
    """Parse both ambient flags once, with the revert flag taking precedence."""
    repair = parse_incident_truth_value(
        name=EXPEDITED_INCIDENT_RESPONSE,
        value=environ.get(EXPEDITED_INCIDENT_RESPONSE),
    )
    if not is_successful(repair):
        return Failure(repair.failure())
    revert = parse_incident_truth_value(
        name=EXPEDITED_INCIDENT_RESPONSE_REVERT,
        value=environ.get(EXPEDITED_INCIDENT_RESPONSE_REVERT),
    )
    if not is_successful(revert):
        return Failure(revert.failure())
    return Success(
        ExecutionMode.EMERGENCY_REVERT
        if revert.unwrap()
        else ExecutionMode.EXPEDITED_REPAIR
        if repair.unwrap()
        else ExecutionMode.NORMAL
    )


def resolve_execution_context(
    *,
    environ: Mapping[str, str],
    invocation: str,
    identity: OperationIdentity | None,
) -> IncidentResolution:
    """Resolve the trusted operation context before a caller selects any gate.

    Normal master and normal factory follow-up are trusted normal origins. They
    intentionally never parse inherited incident flags: even a malformed value
    must be inert there.  Other origins parse both flags, with emergency revert
    taking precedence over expedited repair.
    """
    if invocation not in {
        Invocation.ORDINARY,
        Invocation.NORMAL_MASTER,
        Invocation.NORMAL_FACTORY_FOLLOW_UP,
    }:
        return _failure(
            refusal=IncidentConfigurationRefusal(
                code="invalid-incident-invocation",
                detail="unknown trusted invocation",
            )
        )
    if invocation in {Invocation.NORMAL_MASTER, Invocation.NORMAL_FACTORY_FOLLOW_UP}:
        return _success(
            context=ExecutionContext(
                mode=ExecutionMode.NORMAL,
                invocation=invocation,
                identity=None,
            ),
        )
    selected_mode = _incident_mode(environ=environ)
    if not is_successful(selected_mode):
        return _failure(refusal=selected_mode.failure())
    mode = selected_mode.unwrap()
    if mode == ExecutionMode.NORMAL:
        return _success(context=ExecutionContext(mode=mode, invocation=invocation, identity=None))
    return _incident_context(mode=mode, invocation=invocation, identity=identity)


def _incident_context(
    *, mode: str, invocation: str, identity: OperationIdentity | None
) -> IncidentResolution:
    """Validate caller-authenticated identity syntax and selected operation phase."""
    refusal = _identity_refusal(identity=identity)
    if refusal is not None:
        return _failure(refusal=refusal)
    validated_identity = cast(OperationIdentity, identity)
    expected_phases = (
        {"reverting", "emergency-revert"}
        if mode == ExecutionMode.EMERGENCY_REVERT
        else {"repair", "expedited-repair"}
    )
    if validated_identity.phase not in expected_phases:
        return _failure(
            refusal=IncidentConfigurationRefusal(
                code="invalid-incident-identity",
                detail="incident phase does not match the selected mode",
            )
        )
    if (
        mode == ExecutionMode.EMERGENCY_REVERT
        or validated_identity.recorded_incident_merge_sha is not None
    ):
        revert_refusal = _revert_refusal(identity=validated_identity)
        if revert_refusal is not None:
            return _failure(refusal=revert_refusal)
    return _success(context=ExecutionContext(mode=mode, invocation=invocation, identity=identity))


def validate_execution_context(*, context: ExecutionContext) -> IncidentResolution:
    """Revalidate a caller-constructed context; this does not authenticate its receipt."""
    flags = {
        ExecutionMode.NORMAL: {},
        ExecutionMode.EXPEDITED_REPAIR: {EXPEDITED_INCIDENT_RESPONSE: "1"},
        ExecutionMode.EMERGENCY_REVERT: {EXPEDITED_INCIDENT_RESPONSE_REVERT: "1"},
    }
    if context.mode not in flags:
        return _failure(
            refusal=IncidentConfigurationRefusal(
                code="invalid-incident-context",
                detail="unknown execution mode",
            )
        )
    resolved = resolve_execution_context(
        environ=flags[context.mode],
        invocation=context.invocation,
        identity=context.identity,
    )
    if resolved.is_successful and resolved.unwrap() != context:
        return _failure(
            refusal=IncidentConfigurationRefusal(
                code="invalid-incident-context",
                detail="mode, invocation and identity are inconsistent",
            )
        )
    return resolved
