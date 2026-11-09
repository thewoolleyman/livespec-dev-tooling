"""Transport a resolved context without turning serialized input into authority.

The receiver obtains trusted_context independently from its authenticated event
and validated receipt. JSON proves consistency with that input, not authority.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from dataclasses import asdict
from pathlib import Path
from typing import cast

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.result import Failure, Result, Success  # noqa: E402 — vendor-path-aware import.

from livespec_dev_tooling.incident_execution import (  # noqa: E402
    EXPEDITED_INCIDENT_RESPONSE,
    EXPEDITED_INCIDENT_RESPONSE_REVERT,
    ExecutionContext,
    ExecutionMode,
    IncidentConfigurationRefusal,
    IncidentResolution,
    Invocation,
    validate_execution_context,
)

__all__: list[str] = [
    "CONTEXT_ENV",
    "child_environment",
    "decode_execution_context",
    "encode_execution_context",
    "gate_child_environment",
    "normal_child_environment",
]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-sh3vz3
CONTEXT_ENV = "LIVESPEC_INCIDENT_CONTEXT"
# The incident hook entrance's own carriers, which no child it starts may inherit.
QUERY_ENV = "LIVESPEC_INCIDENT_AUTHORITY_QUERY"
LOCAL_OPERATION_ENV = "LIVESPEC_INCIDENT_LOCAL_OPERATION"
_MAX_PAYLOAD_BYTES = 16384


def encode_execution_context(
    *,
    context: ExecutionContext,
) -> Result[str, IncidentConfigurationRefusal]:
    """Serialize a valid caller-trusted context into the version-one schema."""
    validated = validate_execution_context(context=context)
    if not validated.is_successful:
        return Failure(validated.failure())
    payload = json.dumps(
        {"schema_version": 1, **asdict(context)},
        sort_keys=True,
        separators=(",", ":"),
    )
    if len(payload.encode("utf-8")) > _MAX_PAYLOAD_BYTES:
        return Failure(
            IncidentConfigurationRefusal(
                code="invalid-incident-transport",
                detail="encoded context exceeds transport limit",
            )
        )
    return Success(payload)


def _transport_refusal(*, detail: str) -> IncidentResolution:
    """Name malformed or mismatched transport; never fall back to normal."""
    return IncidentResolution(
        result=Failure(
            IncidentConfigurationRefusal(
                code="invalid-incident-transport",
                detail=detail,
            )
        )
    )


def _unique_object(*, pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Reject duplicate JSON keys instead of trusting the last spelling."""
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            message = "duplicate JSON key"
            raise ValueError(message)
        result[key] = value
    return result


def decode_execution_context(
    *,
    payload: str,
    trusted_context: ExecutionContext,
) -> IncidentResolution:
    """Compare transport with independently trusted context, never derive trust.

    Trusted master/follow-up ignores inherited transport before parsing it.
    Ordinary input must match every field and its exact JSON scalar type.
    """
    expected = encode_execution_context(context=trusted_context)
    if isinstance(expected, Failure):
        return IncidentResolution(result=Failure(expected.failure()))
    validated = IncidentResolution(result=Success(trusted_context))
    if trusted_context.invocation in {
        Invocation.NORMAL_MASTER,
        Invocation.NORMAL_FACTORY_FOLLOW_UP,
    }:
        return validated
    if (
        not isinstance(cast(object, payload), str)
        or len(payload.encode("utf-8", "surrogatepass")) > _MAX_PAYLOAD_BYTES
    ):
        return _transport_refusal(detail="context payload must be a bounded JSON string")
    try:
        received = json.loads(payload, object_pairs_hook=lambda pairs: _unique_object(pairs=pairs))
        canonical = json.dumps(received, sort_keys=True, separators=(",", ":"))
    except (ValueError, TypeError, RecursionError):
        return _transport_refusal(detail="context payload is malformed or has duplicate keys")
    if canonical != expected.unwrap():
        return _transport_refusal(detail="transport does not match independently trusted context")
    return validated


def normal_child_environment(*, environ: Mapping[str, str]) -> dict[str, str]:
    """Remove both flags and the context carrier without parsing inherited values."""
    excluded = {EXPEDITED_INCIDENT_RESPONSE, EXPEDITED_INCIDENT_RESPONSE_REVERT, CONTEXT_ENV}
    return {key: value for key, value in environ.items() if key not in excluded}


def gate_child_environment(*, environ: Mapping[str, str]) -> dict[str, str]:
    """Remove every incident variable, the entrance's own carriers included.

    Each gate the incident hook routes, and each focused test the incident
    evidence runs, sees neither flag, nor the context, nor the authority query
    or local operation that only the entrance consumes.
    """
    excluded = {QUERY_ENV, LOCAL_OPERATION_ENV}
    child = normal_child_environment(environ=environ)
    return {key: value for key, value in child.items() if key not in excluded}


def child_environment(
    *,
    context: ExecutionContext,
    environ: Mapping[str, str],
) -> Result[dict[str, str], IncidentConfigurationRefusal]:
    """Explicitly project one validated operation after a credential boundary.

    Normal children receive no incident fields. Incident children receive one
    canonical flag and consistency payload, which receivers must authenticate
    independently. This function never mutates the caller's environment.
    """
    encoded = encode_execution_context(context=context)
    if isinstance(encoded, Failure):
        return Failure(encoded.failure())
    child = normal_child_environment(environ=environ)
    if context.mode != ExecutionMode.NORMAL:
        flag = (
            EXPEDITED_INCIDENT_RESPONSE_REVERT
            if context.mode == ExecutionMode.EMERGENCY_REVERT
            else EXPEDITED_INCIDENT_RESPONSE
        )
        child[flag] = "1"
        child[CONTEXT_ENV] = encoded.unwrap()
    return Success(child)
