"""Edge cases for trusted incident execution mode resolution."""

from __future__ import annotations

import importlib

import pytest

__all__: list[str] = []


def _module() -> object:
    """Load the public incident resolver module."""
    return importlib.import_module("livespec_dev_tooling.incident_execution")


def _identity(*, module: object) -> object:
    """Build one complete operation identity for a selected incident mode."""
    return module.OperationIdentity(
        incident_item_id="livespec-dev-tooling-incident",
        attempt_id="attempt-001",
        phase="expedited-repair",
        repository="thewoolleyman/livespec-dev-tooling",
        base_sha="a" * 40,
        head_sha="b" * 40,
        operation_id="operation-001",
    )


@pytest.mark.parametrize("value", [None, "", "0", "false", "no", "off"])
def test_documented_false_values_remain_normal(*, value: str | None) -> None:
    """Unset and documented false spellings must retain ordinary execution."""
    module = _module()

    parsed = module.parse_incident_truth_value(name="FLAG", value=value)

    assert parsed.unwrap() is False


@pytest.mark.parametrize("value", ["1", "true", "yes", "on", " TRUE "])
def test_documented_true_values_select_an_incident_mode(*, value: str) -> None:
    """The shared parser accepts every documented truthy spelling once."""
    module = _module()

    parsed = module.parse_incident_truth_value(name="FLAG", value=value)

    assert parsed.unwrap() is True


def test_malformed_ordinary_flags_are_named_configuration_refusals() -> None:
    """A typo cannot quietly choose normal gate behavior."""
    module = _module()

    resolved = module.resolve_execution_context(
        environ={module.EXPEDITED_INCIDENT_RESPONSE: "sometimes"},
        invocation=module.Invocation.ORDINARY,
        identity=None,
    )

    assert not resolved.is_successful
    assert resolved.failure().code == "invalid-incident-flag"


def test_revert_wins_over_repair_and_requires_a_complete_identity() -> None:
    """The stronger emergency signal selects only a recorded incident merge."""
    module = _module()

    unrecorded = module.resolve_execution_context(
        environ={module.EXPEDITED_INCIDENT_RESPONSE_REVERT: "1"},
        invocation=module.Invocation.ORDINARY,
        identity=_identity(module=module),
    )
    assert not unrecorded.is_successful

    selected = module.resolve_execution_context(
        environ={
            module.EXPEDITED_INCIDENT_RESPONSE: "1",
            module.EXPEDITED_INCIDENT_RESPONSE_REVERT: "1",
        },
        invocation=module.Invocation.ORDINARY,
        identity=module.OperationIdentity(
            incident_item_id="livespec-dev-tooling-incident",
            attempt_id="attempt-001",
            phase="emergency-revert",
            repository="thewoolleyman/livespec-dev-tooling",
            base_sha="a" * 40,
            head_sha="b" * 40,
            operation_id="operation-001",
            recorded_incident_merge_sha="c" * 40,
        ),
    )
    missing = module.resolve_execution_context(
        environ={module.EXPEDITED_INCIDENT_RESPONSE_REVERT: "1"},
        invocation=module.Invocation.ORDINARY,
        identity=None,
    )

    assert selected.unwrap().mode is module.ExecutionMode.EMERGENCY_REVERT
    assert unrecorded.failure().code == "missing-recorded-incident-merge"
    assert missing.failure().code == "missing-incident-identity"


def test_invalid_identity_and_revert_flag_refuse_without_falling_back_to_normal() -> None:
    """Trust failures remain named configuration refusals at ordinary boundaries."""
    module = _module()

    invalid_identity = module.resolve_execution_context(
        environ={module.EXPEDITED_INCIDENT_RESPONSE: "1"},
        invocation=module.Invocation.ORDINARY,
        identity=module.OperationIdentity(
            incident_item_id="livespec-dev-tooling-incident",
            attempt_id="attempt-001",
            phase="expedited-repair",
            repository="thewoolleyman/livespec-dev-tooling",
            base_sha="a" * 40,
            head_sha="",
            operation_id="operation-001",
        ),
    )
    invalid_revert = module.resolve_execution_context(
        environ={
            module.EXPEDITED_INCIDENT_RESPONSE: "1",
            module.EXPEDITED_INCIDENT_RESPONSE_REVERT: "broken",
        },
        invocation=module.Invocation.ORDINARY,
        identity=_identity(module=module),
    )

    assert invalid_identity.failure().code == "invalid-incident-identity"
    assert invalid_revert.failure().code == "invalid-incident-flag"


def test_ordinary_invocation_preserves_normal_gate_selection_without_flags() -> None:
    """An ordinary invocation stays normal when it carries no incident signal."""
    module = _module()

    resolved = module.resolve_execution_context(
        environ={},
        invocation=module.Invocation.ORDINARY,
        identity=None,
    )

    assert resolved.unwrap().mode is module.ExecutionMode.NORMAL


@pytest.mark.parametrize(
    "invocation",
    ["normal-master", "normal-factory-follow-up"],
)
def test_trusted_normal_origins_ignore_even_malformed_inherited_flags(*, invocation: str) -> None:
    """Master and factory follow-up must force normal before flag parsing."""
    module = _module()

    resolved = module.resolve_execution_context(
        environ={
            module.EXPEDITED_INCIDENT_RESPONSE: "not-a-boolean",
            module.EXPEDITED_INCIDENT_RESPONSE_REVERT: "also-not-a-boolean",
        },
        invocation=invocation,
        identity=_identity(module=module),
    )

    assert resolved.unwrap().mode is module.ExecutionMode.NORMAL
    assert resolved.unwrap().identity is None
