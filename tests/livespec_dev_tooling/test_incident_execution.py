"""Trusted incident execution mode resolution."""

from __future__ import annotations

import importlib
from pathlib import Path

__all__: list[str] = []


def test_an_expedited_invocation_binds_its_identity_before_gate_selection() -> None:
    """Repair mode is a typed context, not an ambient flag a gate re-reads."""
    module_path = Path("livespec_dev_tooling/incident_execution.py")
    assert module_path.is_file()
    module = importlib.import_module("livespec_dev_tooling.incident_execution")
    identity = module.OperationIdentity(
        incident_item_id="livespec-dev-tooling-incident",
        attempt_id="attempt-001",
        phase="expedited-repair",
        repository="thewoolleyman/livespec-dev-tooling",
        base_sha="a" * 40,
        head_sha="b" * 40,
        operation_id="operation-001",
    )

    resolved = module.resolve_execution_context(
        environ={module.EXPEDITED_INCIDENT_RESPONSE: "1"},
        invocation=module.Invocation.ORDINARY,
        identity=identity,
    )

    assert resolved.is_successful
    context = resolved.unwrap()
    assert context.mode is module.ExecutionMode.EXPEDITED_REPAIR
    assert context.identity == identity
