"""Tests for the kill matrix's what-changed summary."""

from __future__ import annotations

import importlib

__all__: list[str] = []


def test_newly_redundant_tests_and_newly_surviving_mutants_are_listed_and_marked() -> None:
    """New names are `new`, known ones `changed`, and each mutant carries its function's change."""
    module = importlib.import_module("livespec_dev_tooling.mutation_kill_matrix_changes")
    previous: dict[str, object] = {
        "source_revision": "r1",
        "tests": ["t::listed"],
        "redundancy_candidates": ["t::already"],
        "baseline_failures": ["t::was_broken"],
        "surviving_mutants": ["M0"],
        "mutants": [
            {"identifier": "M1", "killed_by": ["t::killer"], "function_digest": "a"},
            {"identifier": "M2", "killed_by": ["t::killer"], "function_digest": "b"},
            {"identifier": "M3", "killed_by": ["t::killer"]},
            {"identifier": "M0", "killed_by": []},
        ],
    }
    current: dict[str, object] = {
        "source_revision": "r2",
        "redundancy_candidates": [
            "t::already",
            "t::listed",
            "t::killer",
            "t::was_broken",
            "t::fresh",
        ],
        "surviving_mutants": ["M0", "M1", "M2", "M3", "M4"],
        "mutants": [
            {"identifier": "M1", "function_digest": "a"},
            {"identifier": "M2", "function_digest": "changed"},
            {"identifier": "M3", "function_digest": "c"},
            {"identifier": "M4", "function_digest": "d"},
            {"identifier": "M0"},
        ],
    }

    summary = module.build_changes(previous=previous, current=current)

    assert summary["previous_source_revision"] == "r1"
    assert summary["source_revision"] == "r2"
    assert summary["new_redundancy_candidates"] == [
        {"status": "new", "test": "t::fresh"},
        {"status": "changed", "test": "t::killer"},
        {"status": "changed", "test": "t::listed"},
        {"status": "changed", "test": "t::was_broken"},
    ]
    assert summary["new_surviving_mutants"] == [
        {"function": "function unchanged", "mutant": "M1", "status": "changed"},
        {"function": "function changed", "mutant": "M2", "status": "changed"},
        {"function": "function unknown", "mutant": "M3", "status": "changed"},
        {"function": "function unknown", "mutant": "M4", "status": "new"},
    ]
