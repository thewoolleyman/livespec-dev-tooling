"""Refuse malformed trusted inputs before any gate can be selected."""

from dataclasses import replace

import pytest

from livespec_dev_tooling.incident_execution import (
    EXPEDITED_INCIDENT_RESPONSE,
    EXPEDITED_INCIDENT_RESPONSE_REVERT,
    Invocation,
    OperationIdentity,
    resolve_execution_context,
)

__all__: list[str] = []


def identity() -> OperationIdentity:
    """Return the authenticated receipt shape supplied by the owning caller."""
    return OperationIdentity(
        incident_item_id="incident-123",
        attempt_id="attempt-1",
        phase="repair",
        repository="owner/repo",
        base_sha="a" * 40,
        head_sha="b" * 40,
        operation_id="operation-1",
    )


def test_unknown_invocation_is_not_an_ordinary_fallback() -> None:
    result = resolve_execution_context(
        environ={EXPEDITED_INCIDENT_RESPONSE: "1"},
        invocation="normal-mastre",
        identity=identity(),
    )
    assert not result.is_successful
    assert result.failure().code == "invalid-incident-invocation"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("base_sha", "nonsense"),
        ("head_sha", "b" * 39),
        ("repository", "../repo"),
        ("repository", "owner/.."),
        ("phase", "closed"),
        ("attempt_id", ""),
        ("attempt_id", " padded "),
        ("operation_id", "bad\nidentity"),
        ("incident_item_id", 42),
    ],
)
def test_malformed_identity_is_a_named_refusal(*, field: str, value: object) -> None:
    result = resolve_execution_context(
        environ={EXPEDITED_INCIDENT_RESPONSE: "1"},
        invocation=Invocation.ORDINARY,
        identity=replace(identity(), **{field: value}),
    )
    assert not result.is_successful
    assert result.failure().code == "invalid-incident-identity"


@pytest.mark.parametrize("merge", [None, "", "not-a-merge", 42])
def test_revert_requires_a_full_recorded_merge(*, merge: str | None) -> None:
    result = resolve_execution_context(
        environ={EXPEDITED_INCIDENT_RESPONSE_REVERT: "1"},
        invocation=Invocation.ORDINARY,
        identity=replace(identity(), phase="reverting", recorded_incident_merge_sha=merge),
    )
    assert not result.is_successful
    assert result.failure().code in {
        "missing-recorded-incident-merge",
        "invalid-recorded-incident-merge",
    }


def test_non_identity_object_is_refused() -> None:
    result = resolve_execution_context(
        environ={EXPEDITED_INCIDENT_RESPONSE: "1"},
        invocation=Invocation.ORDINARY,
        identity={"incident_item_id": "forged"},
    )
    assert result.failure().code == "invalid-incident-identity"


def test_malformed_revert_flag_is_not_a_repair_fallback() -> None:
    result = resolve_execution_context(
        environ={EXPEDITED_INCIDENT_RESPONSE: "1", EXPEDITED_INCIDENT_RESPONSE_REVERT: "broken"},
        invocation=Invocation.ORDINARY,
        identity=identity(),
    )
    assert result.failure().code == "invalid-incident-flag"


def test_repair_validates_an_optional_recorded_merge() -> None:
    result = resolve_execution_context(
        environ={EXPEDITED_INCIDENT_RESPONSE: "1"},
        invocation=Invocation.ORDINARY,
        identity=replace(identity(), recorded_incident_merge_sha="c" * 64),
    )
    assert result.is_successful
