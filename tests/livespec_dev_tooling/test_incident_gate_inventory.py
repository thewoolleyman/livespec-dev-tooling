"""The real aggregate inventory supplies bounded incident gate selection."""

from __future__ import annotations

from livespec_dev_tooling.incident_gate_inventory import inventory_gates
from livespec_dev_tooling.incident_local_gates import select_gates

__all__: list[str] = []

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-cerkbn


def test_timing_annotations_preserve_inventory_order_and_other_declarations() -> None:
    gates = inventory_gates(
        inventory="""# canonical inventory
check-lint # purity: tree-pure # incident-timing: fast
check-coverage # incident-timing: slow # purity: tree-pure
check-new
"""
    )
    assert [gate.name for gate in gates] == ["check-lint", "check-coverage", "check-new"]
    assert [gate.command for gate in gates] == [
        ("just", "check-lint"),
        ("just", "check-coverage"),
        ("just", "check-new"),
    ]
    assert [selection.selected for selection in select_gates(gates=gates)] == [True, False, False]


def test_ambiguous_declarations_never_select_work() -> None:
    gates = inventory_gates(
        inventory="""check-duplicate # incident-timing: fast
check-duplicate # incident-timing: fast
check-conflicting # incident-timing: fast # incident-timing: slow
check-invalid # incident-timing: FAST
check-empty # incident-timing:
"""
    )
    assert len(gates) == 4
    assert not any(selection.selected for selection in select_gates(gates=gates))


def test_only_recipe_names_become_command_arguments() -> None:
    gates = inventory_gates(
        inventory="""check-good # incident-timing: fast
check-good; touch unexpected # incident-timing: fast
check-with extra-argument # incident-timing: fast
--evaluate # incident-timing: fast
"""
    )
    assert [gate.command for gate in gates] == [("just", "check-good")]
