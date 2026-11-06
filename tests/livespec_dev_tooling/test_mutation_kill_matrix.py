"""Tests for the engine-neutral Rule-26 mutation kill-matrix report."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_report_attributes_each_mutant_to_its_killing_tests_and_writes_json(
    *, tmp_path: Path
) -> None:
    """The portable report records mutant identities, locations, and killers."""
    module_path = _REPO_ROOT / "livespec_dev_tooling" / "mutation_kill_matrix.py"
    assert module_path.is_file()

    module = importlib.import_module("livespec_dev_tooling.mutation_kill_matrix")
    report = module.build_report(
        engine="mutmut",
        engine_version="3.2.3",
        source_revision="abc123",
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

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["engine"] == {"name": "mutmut", "version": "3.2.3"}
    assert payload["source_revision"] == "abc123"
    assert payload["mutants_generated"] == 2
    assert payload["mutants"] == [
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
