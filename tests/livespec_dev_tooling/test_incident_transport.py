"""Context transport cannot substitute for independent receipt authority."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest
from returns.pipeline import is_successful

from livespec_dev_tooling.incident_execution import (
    EXPEDITED_INCIDENT_RESPONSE,
    EXPEDITED_INCIDENT_RESPONSE_REVERT,
    ExecutionContext,
    ExecutionMode,
    Invocation,
    OperationIdentity,
    validate_execution_context,
)
from livespec_dev_tooling.incident_transport import (
    CONTEXT_ENV,
    child_environment,
    decode_execution_context,
    encode_execution_context,
    normal_child_environment,
)

__all__: list[str] = []


def _context(*, mode: str = ExecutionMode.EXPEDITED_REPAIR) -> ExecutionContext:
    """Model context independently authenticated by the receiving caller."""
    identity = OperationIdentity(
        incident_item_id="incident-123",
        attempt_id="attempt-1",
        phase="repair",
        repository="owner/repo",
        base_sha="a" * 40,
        head_sha="b" * 40,
        operation_id="operation-1",
    )
    if mode == ExecutionMode.EMERGENCY_REVERT:
        identity = replace(identity, phase="reverting", recorded_incident_merge_sha="c" * 40)
    return ExecutionContext(
        mode=mode,
        invocation=Invocation.ORDINARY,
        identity=None if mode == ExecutionMode.NORMAL else identity,
    )


@pytest.mark.parametrize("mode", ["normal", "expedited-repair", "emergency-revert"])
def test_same_operation_transport_round_trips(*, mode: str) -> None:
    context = _context(mode=mode)
    payload = encode_execution_context(context=context).unwrap()
    assert decode_execution_context(payload=payload, trusted_context=context).unwrap() == context


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", True),
        ("schema_version", 1.0),
        ("schema_version", 2),
        ("schema_version", None),
        ("mode", "normal"),
        ("invocation", "normal-master"),
        ("identity", None),
        ("extra", "value"),
    ],
)
def test_schema_and_mode_mismatch_refuse(*, field: str, value: object) -> None:
    context = _context()
    payload = json.loads(encode_execution_context(context=context).unwrap())
    payload[field] = value
    result = decode_execution_context(payload=json.dumps(payload), trusted_context=context)
    assert result.failure().code == "invalid-incident-transport"


@pytest.mark.parametrize(
    "field",
    [
        "incident_item_id",
        "attempt_id",
        "phase",
        "repository",
        "base_sha",
        "head_sha",
        "operation_id",
        "recorded_incident_merge_sha",
    ],
)
def test_every_identity_field_is_bound(*, field: str) -> None:
    context = _context(mode=ExecutionMode.EMERGENCY_REVERT)
    payload = json.loads(encode_execution_context(context=context).unwrap())
    payload["identity"][field] = "foreign-or-stale"
    assert not decode_execution_context(
        payload=json.dumps(payload), trusted_context=context
    ).is_successful


@pytest.mark.parametrize(
    "payload",
    [
        "{",
        "[]",
        "null",
        "{}",
        "1",
        "true",
        '{"schema_version":1,"schema_version":1}',
        "x" * 16385,
        "[" * 1100,
        '"\\ud800"',
        None,
    ],
)
def test_bad_payload_cannot_select_a_fallback(*, payload: str) -> None:
    assert (
        decode_execution_context(payload=payload, trusted_context=_context()).failure().code
        == "invalid-incident-transport"
    )


def test_missing_schema_member_refuses() -> None:
    context = _context()
    payload = json.loads(encode_execution_context(context=context).unwrap())
    del payload["identity"]["operation_id"]
    assert not decode_execution_context(
        payload=json.dumps(payload), trusted_context=context
    ).is_successful


@pytest.mark.parametrize(
    "invocation", [Invocation.NORMAL_MASTER, Invocation.NORMAL_FACTORY_FOLLOW_UP]
)
def test_trusted_normal_ignores_bad_transport_and_clears_all_fields(*, invocation: str) -> None:
    context = replace(_context(mode="normal"), invocation=invocation)
    ambient = {
        EXPEDITED_INCIDENT_RESPONSE: "malformed",
        EXPEDITED_INCIDENT_RESPONSE_REVERT: "bad",
        CONTEXT_ENV: "{",
        "KEEP": "yes",
    }
    assert decode_execution_context(payload="{", trusted_context=context).unwrap() == context
    assert child_environment(context=context, environ=ambient).unwrap() == {"KEEP": "yes"}
    assert normal_child_environment(environ=ambient) == {"KEEP": "yes"}
    assert ambient[CONTEXT_ENV] == "{"


@pytest.mark.parametrize(
    "context",
    [
        ExecutionContext(mode="alien", invocation="ordinary", identity=None),
        ExecutionContext(mode="normal", invocation="typo", identity=None),
        replace(_context(), invocation="normal-master"),
        replace(_context(), mode="normal"),
        replace(_context(), identity=None),
    ],
)
def test_constructed_context_is_revalidated_before_transport(*, context: ExecutionContext) -> None:
    assert not validate_execution_context(context=context).is_successful
    assert not is_successful(encode_execution_context(context=context))
    assert not decode_execution_context(payload="{}", trusted_context=context).is_successful
    assert not is_successful(child_environment(context=context, environ={}))


def test_encoder_never_emits_a_payload_the_decoder_rejects_for_size() -> None:
    context = _context()
    assert context.identity is not None
    too_big = replace(context, identity=replace(context.identity, operation_id="x" * 16384))
    assert encode_execution_context(context=too_big).failure().code == "invalid-incident-transport"
    assert (
        child_environment(context=too_big, environ={}).failure().code
        == "invalid-incident-transport"
    )
    assert (
        decode_execution_context(payload="{}", trusted_context=too_big).failure().code
        == "invalid-incident-transport"
    )
    bounded = replace(context, identity=replace(context.identity, operation_id="x" * 15000))
    encoded = encode_execution_context(context=bounded).unwrap()
    assert decode_execution_context(payload=encoded, trusted_context=bounded).unwrap() == bounded
