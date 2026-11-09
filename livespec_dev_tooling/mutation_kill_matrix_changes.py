"""The Rule-26 kill matrix's what-changed summary against a previous report.

Mutants compare by identifier and tests by node id.  A listed entry is `new`
when its identifier or node id is absent from the previous report, and
`changed` otherwise.  A mutant identifier can name a different mutation once
its function changes, so every listed mutant also carries how its function
compares: `function changed` when the two reports' function digests differ,
`function unknown` when either report lacks one, and `function unchanged`
otherwise.
"""

from __future__ import annotations

from typing import cast

__all__: list[str] = [
    "build_changes",
]


def _rows(*, document: dict[str, object]) -> dict[str, dict[str, object]]:
    """Index a report's mutant rows by identifier."""
    rows = cast("list[dict[str, object]]", document.get("mutants", []))
    return {str(row["identifier"]): row for row in rows}


def _names(*, document: dict[str, object], field: str) -> set[str]:
    """Return one list field of a report as a set of strings."""
    return {str(name) for name in cast("list[object]", document.get(field, []))}


def _known_tests(*, document: dict[str, object]) -> set[str]:
    """Every test node id a report names, wherever it names it."""
    named = _names(document=document, field="tests")
    for field in ("redundancy_candidates", "unapplied_coverage_tests", "baseline_failures"):
        named |= _names(document=document, field=field)
    for row in _rows(document=document).values():
        named |= {str(test) for test in cast("list[object]", row.get("killed_by", []))}
    return named


def _function(*, previous: dict[str, object] | None, current: dict[str, object]) -> str:
    """Compare one mutant's function digests across the two reports."""
    before = previous.get("function_digest") if previous is not None else None
    after = current.get("function_digest")
    if before is None or after is None:
        return "function unknown"
    return "function unchanged" if before == after else "function changed"


def build_changes(*, previous: dict[str, object], current: dict[str, object]) -> dict[str, object]:
    """List the newly redundant tests and the newly surviving mutants since `previous`."""
    known_tests = _known_tests(document=previous)
    before_candidates = _names(document=previous, field="redundancy_candidates")
    before_survivors = _names(document=previous, field="surviving_mutants")
    before_rows = _rows(document=previous)
    current_rows = _rows(document=current)
    return {
        "previous_source_revision": previous.get("source_revision"),
        "source_revision": current.get("source_revision"),
        "new_redundancy_candidates": [
            {"test": test, "status": "changed" if test in known_tests else "new"}
            for test in sorted(
                _names(document=current, field="redundancy_candidates") - before_candidates
            )
        ],
        "new_surviving_mutants": [
            {
                "mutant": mutant,
                "status": "changed" if mutant in before_rows else "new",
                "function": _function(
                    previous=before_rows.get(mutant), current=current_rows[mutant]
                ),
            }
            for mutant in sorted(
                _names(document=current, field="surviving_mutants") - before_survivors
            )
        ],
    }
