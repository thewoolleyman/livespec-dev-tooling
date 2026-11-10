"""Tests that the kill matrix's planning stage does its per-target work once, not per mutant.

A real target generates tens of thousands of mutants (82,617 for the
orchestrator), so anything planning repeats for each mutant — walking the
tree, parsing a source file, or folding the whole coverage map — multiplies
into hours before a single mutant runs.
"""

from __future__ import annotations

import importlib
import subprocess
from pathlib import Path

import pytest

from livespec_dev_tooling.mutation_kill_matrix import Mutant

__all__: list[str] = []


_TWO_FUNCTIONS = """\
def f(value):
    return value + 1


class Box:
    def g(self, value):
        doubled = value * 2
        return doubled
"""


def _package(*, root: Path) -> Path:
    """Write a src-layout package with one function and one method."""
    (root / "src" / "pkg").mkdir(parents=True)
    _ = (root / "src" / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    _ = (root / "src" / "pkg" / "core.py").write_text(_TWO_FUNCTIONS, encoding="utf-8")
    return root


def _not_a_checkout(
    *, args: list[str], cwd: Path, timeout: float | None = None
) -> subprocess.CompletedProcess[str]:
    """Answer every command as failed, so the cache lists files by walking the tree."""
    _ = cwd, timeout
    return subprocess.CompletedProcess(args, 1, "", "")


def test_the_locator_walks_the_tree_and_parses_each_source_file_once(*, tmp_path: Path) -> None:
    """Later lookups answer from the snapshot the locator took, not from a fresh walk and parse."""
    module = importlib.import_module("livespec_dev_tooling.mutation_kill_matrix_selection")
    target = _package(root=tmp_path)
    locator = module.MutantLocator(target=target)

    first = locator.locate(identifier="pkg.core.x_f__mutmut_1")
    _ = (target / "src" / "pkg" / "core.py").write_text("\n\n\n" + _TWO_FUNCTIONS, encoding="utf-8")
    _ = (target / "src" / "pkg" / "late.py").write_text(_TWO_FUNCTIONS, encoding="utf-8")
    method = locator.locate(identifier="pkg.core.xǁBoxǁg__mutmut_1")

    assert first.location() == "src/pkg/core.py:2-2"
    assert method.location() == "src/pkg/core.py:7-8"
    assert locator.locate(identifier="pkg.late.x_f__mutmut_1") is None
    assert locator.locate(identifier="pkg.core.x_missing__mutmut_1") is None


def test_selection_uses_the_measured_test_set_it_is_given() -> None:
    """The set of measured tests is computed once and handed to every mutant's selection."""
    module = importlib.import_module("livespec_dev_tooling.mutation_kill_matrix_selection")
    coverage = {"src/pkg/core.py": {2: frozenset({"t.py::t1"})}}
    span = module.MutantSpan(path="src/pkg/core.py", first_line=2, last_line=2)
    tests = ["t.py::t1", "t.py::t2"]

    measured = module.measured_tests(coverage=coverage)

    assert measured == frozenset({"t.py::t1"})
    assert (
        module.select_tests(span=span, coverage=coverage, tests=tests, measured=measured) == tests
    )
    assert module.select_tests(
        span=span, coverage=coverage, tests=tests, measured=frozenset(tests)
    ) == ["t.py::t1"]


def test_planning_reports_its_progress_as_done_over_total(
    *, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A long planning stage says how far it has got, so a stall can be told from slow progress."""
    module = importlib.import_module("livespec_dev_tooling.mutation_kill_matrix_stages")
    target = _package(root=tmp_path)
    generated = [
        Mutant(identifier="pkg.core.x_f__mutmut_1", location="mutmut:pkg.core.x_f__mutmut_1"),
        Mutant(identifier="pkg.core.x_f__mutmut_2", location="mutmut:pkg.core.x_f__mutmut_2"),
    ]

    plans = module.plan_mutants(
        execute=_not_a_checkout,
        target=target,
        generated=generated,
        attributable=["t.py::t1"],
        coverage=None,
        timeout=60.0,
    )

    assert [plan.mutant.location for plan in plans] == ["src/pkg/core.py:2-2"] * 2
    assert capsys.readouterr().err.splitlines()[-1] == "mutation-kill-matrix: planned 2/2 mutants"
