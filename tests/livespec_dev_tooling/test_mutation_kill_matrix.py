"""Tests for the portable Rule-26 mutation kill-matrix report."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_report_attributes_every_mutant_to_its_killing_tests(*, tmp_path: Path) -> None:
    """The portable report records mutant identities, locations, and killers."""
    module_path = _REPO_ROOT / "livespec_dev_tooling" / "mutation_kill_matrix.py"
    assert module_path.is_file()

    module = importlib.import_module("livespec_dev_tooling.mutation_kill_matrix")
    report = module.build_report(
        engine_name="mutmut",
        engine_version="3.2.3",
        source_revision="abc123",
        test_selection_method="full-matrix",
        mutants=[
            module.Mutant(identifier="M1", location="package/module.py:10"),
            module.Mutant(identifier="M2", location="package/module.py:20"),
        ],
        tests=["tests/test_rule.py::test_a", "tests/test_rule.py::test_b"],
        killers_by_mutant={
            "M1": {"tests/test_rule.py::test_a", "tests/test_rule.py::test_b"},
            "M2": {"tests/test_rule.py::test_a"},
        },
    )

    path = tmp_path / "reports" / "kill-matrix.json"
    module.write_report(report=report, path=path)

    assert json.loads(path.read_text(encoding="utf-8"))["mutants"] == [
        {
            "identifier": "M1",
            "killed_by": ["tests/test_rule.py::test_a", "tests/test_rule.py::test_b"],
            "location": "package/module.py:10",
        },
        {
            "identifier": "M2",
            "killed_by": ["tests/test_rule.py::test_a"],
            "location": "package/module.py:20",
        },
    ]


def test_report_lists_every_mutant_no_test_kills_as_a_survivor() -> None:
    """A mutant with no killer is retained in the portable survivor list."""
    module = importlib.import_module("livespec_dev_tooling.mutation_kill_matrix")
    report = module.build_report(
        engine_name="mutmut",
        engine_version="3.2.3",
        source_revision="abc123",
        test_selection_method="full-matrix",
        mutants=[module.Mutant(identifier="M3", location="package/module.py:30")],
        tests=["tests/test_rule.py::test_a"],
        killers_by_mutant={},
    )

    assert report.to_dict().get("surviving_mutants") == ["M3"]


def test_report_lists_tests_without_unique_kills_as_redundancy_candidates() -> None:
    """Tests that add no exclusive mutant kill are Rule-26 candidates."""
    module = importlib.import_module("livespec_dev_tooling.mutation_kill_matrix")
    report = module.build_report(
        engine_name="mutmut",
        engine_version="3.2.3",
        source_revision="abc123",
        test_selection_method="full-matrix",
        mutants=[
            module.Mutant(identifier="M1", location="package/module.py:10"),
            module.Mutant(identifier="M2", location="package/module.py:20"),
        ],
        tests=[
            "tests/test_rule.py::test_a",
            "tests/test_rule.py::test_b",
            "tests/test_rule.py::test_c",
        ],
        killers_by_mutant={
            "M1": {"tests/test_rule.py::test_a", "tests/test_rule.py::test_b"},
            "M2": {"tests/test_rule.py::test_a"},
        },
    )

    assert report.to_dict().get("redundancy_candidates") == [
        "tests/test_rule.py::test_b",
        "tests/test_rule.py::test_c",
    ]


def test_report_names_the_test_selection_method_the_run_used() -> None:
    """The report states how tests were paired with mutants."""
    module = importlib.import_module("livespec_dev_tooling.mutation_kill_matrix")
    report = module.build_report(
        engine_name="mutmut",
        engine_version="3.2.3",
        source_revision="abc123",
        test_selection_method="coverage-guided: per-test pytest-cov contexts",
        mutants=[module.Mutant(identifier="M1", location="package/module.py:10-12")],
        tests=["tests/test_rule.py::test_a"],
        killers_by_mutant={"M1": {"tests/test_rule.py::test_a"}},
    )

    assert report.to_dict()["test_selection_method"] == (
        "coverage-guided: per-test pytest-cov contexts"
    )


def test_report_separates_unapplied_mutants_baseline_failures_and_their_tests() -> None:
    """Unapplied mutants and baseline failures leave attribution; each test lands in one list."""
    module = importlib.import_module("livespec_dev_tooling.mutation_kill_matrix")
    report = module.build_report(
        engine_name="mutmut",
        engine_version="3.2.3",
        source_revision="abc123",
        test_selection_method="coverage-guided",
        mutants=[
            module.Mutant(identifier="M1", location="pkg.py:2-2", function_digest="d1"),
            module.Mutant(identifier="M2", location="pkg.py:6-6"),
            module.Mutant(identifier="M3", location="pkg.py:9-9"),
        ],
        tests=["t::unique", "t::shared", "t::unapplied_only", "t::broken"],
        killers_by_mutant={
            "M1": {"t::unique", "t::broken"},
            "M2": {"t::shared"},
            "M3": {"t::shared"},
        },
        unapplied_mutants=frozenset({"M2"}),
        selected_for_unapplied=frozenset({"t::unapplied_only", "t::unique"}),
        baseline_failures=frozenset({"t::broken"}),
        per_test_timeout_seconds=30.0,
        run=module.RunMetadata(workers=4, incremental=True, reused_mutants=2),
    )

    document = report.to_dict()

    assert document["mutants"][0] == {
        "function_digest": "d1",
        "identifier": "M1",
        "killed_by": ["t::unique"],
        "location": "pkg.py:2-2",
    }
    assert document["mutants"][1]["killed_by"] == []
    assert (
        document["mutants_generated"],
        document["mutants_applied"],
        document["mutants_unapplied"],
    ) == (3, 2, 1)
    assert document["surviving_mutants"] == []
    assert document["unapplied_mutants"] == ["M2"]
    assert document["baseline_failures"] == ["t::broken"]
    assert document["redundancy_candidates"] == []
    assert document["unapplied_coverage_tests"] == ["t::unapplied_only"]
    assert document["per_test_timeout_seconds"] == 30.0
    assert document["run"] == {"incremental": True, "reused_mutants": 2, "workers": 4}
    assert "run" not in module.matrix_content(document=document)
    assert module.matrix_content(document=document)["tests"] == document["tests"]
