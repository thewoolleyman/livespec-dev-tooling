"""Tests for `livespec_dev_tooling/fleet/_contract_scope.py`.

The live-table test is the REGRESSION GUARD itself: it drives
`undeclared_narrowings` over the real `OBLIGATION_ROWS`, so a row registered
with a narrowed `applies_to` and no recorded reason fails `just check` rather
than reporting PASS over a population nobody chose (livespec-dev-tooling-thw26i).

The synthetic-row tests are the EVIDENCE that the guard bites. A guard shown
only to pass is not evidence, so each failure mode below is exercised against a
deliberately-narrowed row rather than asserted in prose: an undeclared
narrowing, a declaration that drifted from the row's real exclusion set in
either direction, an unknown kind, a blank reason, and an adoption debt with no
measurement behind it.
"""

from __future__ import annotations

from livespec_dev_tooling.fleet._contract_classes import ALL_CLASSES
from livespec_dev_tooling.fleet._contract_model import ObligationRow
from livespec_dev_tooling.fleet._contract_rows import OBLIGATION_ROWS
from livespec_dev_tooling.fleet._contract_scope import (
    ADOPTION_DEBT,
    CLAUSE_SCOPED,
    ROW_SCOPE_DECLARATIONS,
    RowScopeDeclaration,
    adoption_debt_row_ids,
    undeclared_narrowings,
)
from livespec_dev_tooling.fleet._rows_instructions import assert_agent_instruction_surface

__all__: list[str] = []


def _row(*, applies_to: frozenset[str], row_id: str = "widget-row") -> ObligationRow:
    """A synthetic row carrying a REAL assert, because scope is all that is read.

    `undeclared_narrowings` reads `row_id` and `applies_to` and never invokes
    `assert_member` — the guard judges WHO a row runs against, not what it
    asserts. The row model still requires a `RowFn`, so this passes the one
    belonging to the row the guard was written for rather than a local
    stand-in: a stub defined here would be a body no test could ever execute.
    """
    return ObligationRow(
        row_id=row_id,
        obligation_type="committed-file",
        applies_to=applies_to,
        assert_member=assert_agent_instruction_surface,
        manual_hint="widget",
    )


def _declaration(**overrides: object) -> RowScopeDeclaration:
    fields: dict[str, object] = {
        "row_id": "widget-row",
        "excluded": ALL_CLASSES - {"impl-plugin"},
        "kind": CLAUSE_SCOPED,
        "clause": "widget clause",
        "reason": "widget reason",
    }
    fields.update(overrides)
    return RowScopeDeclaration(**fields)  # pyright: ignore[reportArgumentType]


def test_every_narrowing_in_the_live_table_is_declared() -> None:
    # THE GUARD, over the table both engines actually walk. A new row whose
    # applies_to omits a class, or an edit that moves an existing row's scope
    # without revisiting its recorded reason, fails here.
    assert undeclared_narrowings(rows=OBLIGATION_ROWS) == ()


def test_a_deliberately_narrowed_row_with_no_declaration_is_reported() -> None:
    # The evidence that the guard FAILS rather than merely passing: exactly the
    # shape `agent-instruction-surface` shipped in — a live row asserted against
    # one class of seven, with nothing anywhere saying so.
    findings = undeclared_narrowings(
        rows=(_row(applies_to=frozenset({"impl-plugin"})),), declarations=()
    )
    assert len(findings) == 1
    assert "widget-row" in findings[0]
    assert "no entry in ROW_SCOPE_DECLARATIONS" in findings[0]
    assert "core" in findings[0]


def test_a_row_covering_every_class_needs_no_declaration() -> None:
    assert undeclared_narrowings(rows=(_row(applies_to=ALL_CLASSES),), declarations=()) == ()


def test_a_declaration_that_drifted_from_the_rows_real_exclusion_is_reported() -> None:
    # Drift is caught in BOTH directions by comparing sets rather than by
    # trusting the declaration: a declaration that merely tracked the row would
    # document nothing.
    findings = undeclared_narrowings(
        rows=(_row(applies_to=ALL_CLASSES - {"console"}),),
        declarations=(_declaration(),),
    )
    assert len(findings) == 1
    assert "does not match the row's actual" in findings[0]


def test_a_declaration_for_a_row_that_is_not_narrowed_is_reported() -> None:
    findings = undeclared_narrowings(
        rows=(_row(applies_to=ALL_CLASSES),), declarations=(_declaration(),)
    )
    assert len(findings) == 1
    assert "no row of that id is narrowed" in findings[0]


def test_an_unknown_scope_kind_is_reported() -> None:
    findings = undeclared_narrowings(
        rows=(_row(applies_to=frozenset({"impl-plugin"})),),
        declarations=(_declaration(kind="because"),),
    )
    assert len(findings) == 1
    assert "unknown scope kind" in findings[0]


def test_a_declaration_with_a_blank_reason_is_reported() -> None:
    findings = undeclared_narrowings(
        rows=(_row(applies_to=frozenset({"impl-plugin"})),),
        declarations=(_declaration(reason="   "),),
    )
    assert len(findings) == 1
    assert "carries no reason" in findings[0]


def test_an_adoption_debt_without_a_measurement_is_reported() -> None:
    # The debt kind is the one that does NOT fail the run, so it is the one a
    # future narrowing could hide behind. Requiring the origin/master offender
    # count is what keeps it a debt with a discharge condition rather than a
    # permanent exemption spelled differently.
    findings = undeclared_narrowings(
        rows=(_row(applies_to=frozenset({"impl-plugin"})),),
        declarations=(_declaration(kind=ADOPTION_DEBT),),
    )
    assert len(findings) == 1
    assert "must carry `measured`" in findings[0]


def test_an_adoption_debt_with_a_measurement_is_accepted() -> None:
    assert (
        undeclared_narrowings(
            rows=(_row(applies_to=frozenset({"impl-plugin"})),),
            declarations=(_declaration(kind=ADOPTION_DEBT, measured="2026-09-06: 8 of 10"),),
        )
        == ()
    )


def test_agent_instruction_surface_is_declared_an_adoption_debt() -> None:
    """THE SCOPE, stated: covered `impl-plugin`; excluded the other six as DEBT.

    Not `clause-scoped`. The clause names every governed repo, so the six
    classes the row does not run against are IN the obligation and out of the
    row — the row is narrower than the clause it enforces, which is the finding
    livespec-dev-tooling-thw26i was filed for. Recording it as a debt with a
    measurement is what stops it reading as a scoping decision, and the
    measurement is what the widening is gated on: `plan/rop-railway-enforcement/`
    carries the standing constraint that arming ahead of adoption reddens the
    fleet (`46c5dab`, reverted in `f4247110`), and this row is ALREADY armed at
    error severity, so widening `applies_to` IS the arming.
    """
    declaration = next(d for d in ROW_SCOPE_DECLARATIONS if d.row_id == "agent-instruction-surface")
    assert declaration.kind == ADOPTION_DEBT
    assert declaration.excluded == ALL_CLASSES - {"impl-plugin"}
    assert "Fleet agent-instruction core" in declaration.clause
    assert "8 of 10" in declaration.measured
    # The matcher, stated next to the count — a headings-only measurement of the
    # same fleet returns SEVEN, because `livespec` carries 5/5 headings and no
    # guard registration. Two sessions reported that wrong-scoped number.
    assert "beads-access-guard registration" in declaration.measured
    assert adoption_debt_row_ids() == ("agent-instruction-surface",)


def test_the_other_three_narrowings_are_declared_clause_scoped() -> None:
    # The contrast is the point: three rows are narrow because their clauses are
    # narrow, and exactly one is narrow because adoption has not landed. Before
    # this module the four were indistinguishable.
    clause_scoped = {d.row_id for d in ROW_SCOPE_DECLARATIONS if d.kind == CLAUSE_SCOPED}
    assert clause_scoped == {"workflow-release-dispatch", "copier-answers", "dev-tooling-pin"}
    for declaration in ROW_SCOPE_DECLARATIONS:
        assert declaration.clause, declaration.row_id
        assert declaration.reason, declaration.row_id


def test_every_declaration_names_a_row_that_exists_in_the_table() -> None:
    row_ids = {row.row_id for row in OBLIGATION_ROWS}
    for declaration in ROW_SCOPE_DECLARATIONS:
        assert declaration.row_id in row_ids
