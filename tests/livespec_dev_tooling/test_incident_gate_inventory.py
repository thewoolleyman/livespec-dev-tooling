"""The real aggregate inventory supplies bounded incident gate selection."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from livespec_dev_tooling.check_inventory import inventory_members
from livespec_dev_tooling.incident_gate_inventory import inventory_gates, timing_classes
from livespec_dev_tooling.incident_local_gates import GateResult, execute_plan, select_gates

__all__: list[str] = []

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-cerkbn


def test_timing_annotations_preserve_inventory_order_and_other_declarations() -> None:
    gates = inventory_gates(
        inventory="""# canonical inventory
check-lint # purity: tree-pure # incident-timing: fast
check-coverage # incident-timing: slow # purity: tree-pure
"""
    )
    assert [gate.name for gate in gates] == ["check-lint", "check-coverage"]
    assert [gate.command for gate in gates] == [
        ("just", "check-lint"),
        ("just", "check-coverage"),
    ]
    assert [selection.selected for selection in select_gates(gates=gates)] == [True, False]


def test_an_unannotated_member_refuses_naming_it() -> None:
    # livespec-dev-tooling-dixgta: a member with no timing class is never deferred
    # in silence; deferring it would let an inventory defer every gate unread.
    with pytest.raises(ValueError, match=re.escape("'check-new'")):
        _ = inventory_gates(inventory="check-lint # incident-timing: fast\ncheck-new\n")


@pytest.mark.parametrize(
    ("member", "inventory"),
    [
        (
            "check-duplicate",
            "check-duplicate # incident-timing: fast\ncheck-duplicate # incident-timing: fast\n",
        ),
        (
            "check-conflicting",
            "check-conflicting # incident-timing: fast # incident-timing: slow\n",
        ),
        ("check-invalid", "check-invalid # incident-timing: FAST\n"),
        ("check-empty", "check-empty # incident-timing:\n"),
    ],
)
def test_an_unrecognised_timing_declaration_refuses_naming_the_member(
    *, member: str, inventory: str
) -> None:
    with pytest.raises(ValueError, match=re.escape(f"'{member}'")):
        _ = inventory_gates(inventory=inventory)


def test_a_duplicated_member_is_told_it_is_listed_twice_not_that_its_class_is_unrecognised() -> (
    None
):
    # livespec-dev-tooling-dixgta: a member listed twice with valid declarations is a
    # duplicate, and its refusal says so rather than calling its timing unrecognised.
    duplicate = "check-twice # incident-timing: fast\ncheck-twice # incident-timing: fast\n"
    with pytest.raises(ValueError, match=re.escape("'check-twice' is listed 2 times")):
        _ = inventory_gates(inventory=duplicate)
    with pytest.raises(ValueError, match="no single recognised incident-timing class"):
        _ = inventory_gates(inventory="check-invalid # incident-timing: FAST\n")


def test_only_recipe_names_become_command_arguments() -> None:
    gates = inventory_gates(inventory="check-good # incident-timing: fast\n")
    assert [gate.command for gate in gates] == [("just", "check-good")]


@pytest.mark.parametrize(
    "line", ["check-good; touch unexpected", "check-with extra-argument", "--evaluate"]
)
def test_a_member_that_is_not_a_bare_recipe_name_refuses_naming_it(*, line: str) -> None:
    # livespec-dev-tooling-dixgta: a member the hook cannot hand to `just` is never
    # skipped without a word; the hook refuses and names the member line.
    with pytest.raises(ValueError, match=re.escape(line)):
        _ = inventory_gates(
            inventory=f"check-good # incident-timing: fast\n{line} # incident-timing: fast\n"
        )


def test_a_member_without_the_check_prefix_is_run_or_deferred_by_its_timing() -> None:
    # livespec-dev-tooling-dixgta: livespec's `check:` array lists
    # `e2e-test-claude-code-mock`; the hook reads every member, whatever its prefix.
    gates = inventory_gates(
        inventory="""check-lint # incident-timing: fast
e2e-test-claude-code-mock  # incident-timing: slow
smoke-mock # incident-timing: fast
"""
    )
    assert [gate.command for gate in gates] == [
        ("just", "check-lint"),
        ("just", "e2e-test-claude-code-mock"),
        ("just", "smoke-mock"),
    ]
    assert [selection.selected for selection in select_gates(gates=gates)] == [True, False, True]


def test_the_deferral_of_a_slow_member_without_the_prefix_is_its_receipt_line(
    *, tmp_path: Path
) -> None:
    gates = inventory_gates(inventory="e2e-test-claude-code-mock  # incident-timing: slow\n")
    report = execute_plan(plan=select_gates(gates=gates), cwd=tmp_path)
    assert report.results == (
        GateResult(name="e2e-test-claude-code-mock", status="deferred", reason="known slow gate"),
    )
    assert report.exit_status == 0


def test_this_repositorys_own_inventory_reads_the_same_gates() -> None:
    # Every member of this repository's own inventory carries the `check-` prefix,
    # so reading every member leaves its gates, order and classes unchanged.
    text = (Path(__file__).resolve().parents[2] / "check-targets.txt").read_text()
    names = [member.name for member in inventory_members(text=text)]
    assert [gate.name for gate in inventory_gates(inventory=text)] == names
    assert list(timing_classes(inventory=text)) == names


def test_timing_classes_are_the_one_reading_both_expedited_paths_use() -> None:
    assert timing_classes(
        inventory="""check-fast # incident-timing: fast
check-slow # purity: tree-pure # incident-timing: slow
check-upper # incident-timing: FAST
check-twice # incident-timing: fast
check-twice # incident-timing: fast
check-none
check-precondition # incident-timing: not-applicable # incident-precondition: green-master-ci
"""
    ) == {
        "check-fast": "fast",
        "check-slow": "slow",
        "check-upper": "unclassified",
        "check-twice": "unclassified",
        "check-none": "unclassified",
        "check-precondition": "not-applicable",
    }
