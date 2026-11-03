"""Resolve trusted incident execution mode before any gate chooses work.

Incident flags are deliberately not a gate-local switch.  A caller resolves an
immutable operation identity once, then passes the resulting context across its
hook, dispatcher, CI, and recovery boundaries.  This keeps a normal child from
re-reading a leaked ambient flag and silently acquiring weaker policy.
"""

from __future__ import annotations

import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.pipeline import is_successful  # noqa: E402  — vendor-path-aware import.
from returns.result import Failure, Result, Success  # noqa: E402  — vendor-path-aware import.

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
]

EXPEDITED_INCIDENT_RESPONSE = "EXPEDITED_INCIDENT_RESPONSE"
EXPEDITED_INCIDENT_RESPONSE_REVERT = "EXPEDITED_INCIDENT_RESPONSE_REVERT"

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"", "0", "false", "no", "off"})
_TRUE = True
_FALSE = False


class ExecutionMode:
    """The only execution modes an incident-aware caller may select."""

    NORMAL = "normal"
    EXPEDITED_REPAIR = "expedited-repair"
    EMERGENCY_REVERT = "emergency-revert"


class Invocation:
    """Trusted origin context, which takes precedence over ambient variables."""

    ORDINARY = "ordinary"
    NORMAL_MASTER = "normal-master"
    NORMAL_FACTORY_FOLLOW_UP = "normal-factory-follow-up"


@dataclass(frozen=True, kw_only=True)
class OperationIdentity:
    """The immutable identity bound to one incident operation."""

    incident_item_id: str
    attempt_id: str
    phase: str
    repository: str
    base_sha: str
    head_sha: str
    operation_id: str
    recorded_incident_merge_sha: str | None = None


@dataclass(frozen=True, kw_only=True)
class ExecutionContext:
    """One resolved mode and its identity, ready for gate selection."""

    mode: str
    invocation: str
    identity: OperationIdentity | None


@dataclass(frozen=True, kw_only=True)
class IncidentConfigurationRefusal:
    """A named, expected refusal that must not be mistaken for normal mode."""

    code: str
    detail: str


@dataclass(frozen=True, kw_only=True)
class IncidentResolution:
    """Result-backed resolution with an ergonomic boundary-facing inspection API."""

    result: Result[ExecutionContext, IncidentConfigurationRefusal]

    @property
    def is_successful(self) -> bool:
        """Whether resolving the trusted operation context succeeded."""
        return is_successful(self.result)

    def unwrap(self) -> ExecutionContext:
        """Return the resolved context after a caller has checked success."""
        return self.result.unwrap()

    def failure(self) -> IncidentConfigurationRefusal:
        """Return the named refusal after a caller has checked failure."""
        return self.result.failure()


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
    for field_name, value in (
        ("incident_item_id", identity.incident_item_id),
        ("attempt_id", identity.attempt_id),
        ("phase", identity.phase),
        ("repository", identity.repository),
        ("base_sha", identity.base_sha),
        ("head_sha", identity.head_sha),
        ("operation_id", identity.operation_id),
    ):
        if not value.strip():
            return IncidentConfigurationRefusal(
                code="invalid-incident-identity",
                detail=f"incident operation identity has an empty {field_name}",
            )
    return None


def _revert_refusal(*, identity: OperationIdentity | None) -> IncidentConfigurationRefusal | None:
    """Require an emergency operation to name the merge it is allowed to undo."""
    if identity is None or identity.recorded_incident_merge_sha is None:
        return IncidentConfigurationRefusal(
            code="missing-recorded-incident-merge",
            detail="an emergency revert requires the recorded incident merge SHA it reverses",
        )
    if not identity.recorded_incident_merge_sha.strip():
        return IncidentConfigurationRefusal(
            code="invalid-recorded-incident-merge",
            detail="an emergency revert recorded incident merge SHA must not be empty",
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
    if mode is ExecutionMode.NORMAL:
        return _success(context=ExecutionContext(mode=mode, invocation=invocation, identity=None))
    refusal = _identity_refusal(identity=identity)
    if refusal is not None:
        return _failure(refusal=refusal)
    if mode is ExecutionMode.EMERGENCY_REVERT:
        revert_refusal = _revert_refusal(identity=identity)
        if revert_refusal is not None:
            return _failure(refusal=revert_refusal)
    return _success(context=ExecutionContext(mode=mode, invocation=invocation, identity=identity))
