"""Tests for coverage-guided test selection in the Rule-26 kill matrix."""

from __future__ import annotations

import configparser
import importlib
import os
import subprocess
from pathlib import Path
from types import ModuleType

import pytest
from coverage import CoverageData

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[2]
_MODULE_PATH = _REPO_ROOT / "livespec_dev_tooling" / "mutation_kill_matrix_selection.py"

_TWO_FUNCTIONS = """\
def f(value):
    return value + 1


class Box:
    def g(self, value):
        doubled = value * 2
        return doubled
"""

_CORE_TESTS = """\
from pkg.core import Box, f


def test_f():
    assert f(1) == 2


def test_g():
    assert Box().g(2) == 4
"""


def _selection() -> ModuleType:
    """Import the selection module after proving it ships."""
    assert _MODULE_PATH.is_file()
    return importlib.import_module("livespec_dev_tooling.mutation_kill_matrix_selection")


def _package(*, root: Path) -> Path:
    """Write a src-layout package with one function and one method."""
    (root / "src" / "pkg").mkdir(parents=True)
    _ = (root / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\ntestpaths = ["tests"]\n', encoding="utf-8"
    )
    _ = (root / "src" / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    _ = (root / "src" / "pkg" / "core.py").write_text(_TWO_FUNCTIONS, encoding="utf-8")
    return root


def test_mutants_are_located_at_the_function_body_they_mutate(*, tmp_path: Path) -> None:
    """A mutmut identifier resolves to its function or method body line range."""
    module = _selection()
    target = _package(root=tmp_path)

    function = module.locate_mutant(target=target, identifier="pkg.core.x_f__mutmut_3")
    method = module.locate_mutant(target=target, identifier="pkg.core.xǁBoxǁg__mutmut_1")

    assert function.location() == "src/pkg/core.py:2-2"
    assert method.location() == "src/pkg/core.py:7-8"
    assert module.locate_mutant(target=target, identifier="pkg.core.x_missing__mutmut_1") is None
    assert module.locate_mutant(target=target, identifier="pkg.absent.x_f__mutmut_1") is None
    assert module.locate_mutant(target=target, identifier="pkg.core.unmangled") is None
    assert module.locate_mutant(target=target, identifier="pkg.core.x_Box__mutmut_1") is None


def test_mutmut_working_copies_are_not_first_party_modules(*, tmp_path: Path) -> None:
    """A trampolined copy under mutants/ never stands in for the real source."""
    module = _selection()
    target = _package(root=tmp_path)
    (target / "mutants" / "src" / "pkg").mkdir(parents=True)
    _ = (target / "mutants" / "src" / "pkg" / "core.py").write_text(
        "def f(value):\n    pass\n", encoding="utf-8"
    )

    span = module.locate_mutant(target=target, identifier="pkg.core.x_f__mutmut_1")

    assert span.path == "src/pkg/core.py"


def test_each_mutant_runs_only_against_the_tests_that_execute_it() -> None:
    """T1 executes only F and T2 only G, so each mutant pairs with exactly one test."""
    module = _selection()
    coverage = {"src/pkg/core.py": {2: frozenset({"t.py::t1"}), 7: frozenset({"t.py::t2"})}}
    tests = ["t.py::t1", "t.py::t2"]
    f_span = module.MutantSpan(path="src/pkg/core.py", first_line=2, last_line=2)
    g_span = module.MutantSpan(path="src/pkg/core.py", first_line=7, last_line=8)

    assert module.select_tests(span=f_span, coverage=coverage, tests=tests) == ["t.py::t1"]
    assert module.select_tests(span=g_span, coverage=coverage, tests=tests) == ["t.py::t2"]


def test_unmeasurable_cases_run_against_every_test() -> None:
    """Unmeasured tests, unlocated mutants and import-time bodies fall back to every test."""
    module = _selection()
    span = module.MutantSpan(path="src/pkg/core.py", first_line=2, last_line=2)
    tests = ["t.py::t1", "t.py::unmeasured"]
    measured = {"src/pkg/core.py": {2: frozenset({"t.py::t1"}), 9: frozenset({"t.py::t3"})}}
    at_import = {"src/pkg/core.py": {2: frozenset({""})}}
    elsewhere = module.MutantSpan(path="src/pkg/core.py", first_line=9, last_line=9)

    assert module.select_tests(span=span, coverage=measured, tests=tests) == tests
    assert module.select_tests(span=elsewhere, coverage=measured, tests=tests) == [
        "t.py::unmeasured"
    ]
    assert module.select_tests(span=None, coverage=measured, tests=tests) == tests
    assert module.select_tests(span=span, coverage=None, tests=tests) == tests
    assert module.select_tests(span=span, coverage=at_import, tests=tests) == tests


def _data_file(*, args: list[str]) -> Path:
    """Read the coverage data path from the rcfile the measurement passes pytest-cov."""
    rcfile = next(arg for arg in args if arg.startswith("--cov-config=")).partition("=")[2]
    parser = configparser.ConfigParser()
    _ = parser.read(rcfile)
    return Path(parser["run"]["data_file"])


def test_measured_coverage_maps_each_line_to_its_tests(*, tmp_path: Path) -> None:
    """Per-test contexts are read back with pytest-cov's phase suffix removed."""
    module = _selection()
    target = _package(root=tmp_path)
    source = str(target / "src" / "pkg" / "core.py")

    def execute(*, args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        assert cwd == target
        assert "--cov-context=test" in args
        data = CoverageData(basename=str(_data_file(args=args)))
        data.set_context("t.py::t1|run")
        data.add_lines({source: [2]})
        data.set_context("")
        data.add_lines({source: [1, 5], str(tmp_path.parent / "elsewhere.py"): [1]})
        data.write()
        return subprocess.CompletedProcess(args, 1, "", "")

    coverage = module.measure_per_test_coverage(target=target, execute=execute)

    assert coverage == {
        "src/pkg/core.py": {1: frozenset({""}), 2: frozenset({"t.py::t1"}), 5: frozenset({""})}
    }


def test_no_coverage_data_means_coverage_could_not_be_measured(*, tmp_path: Path) -> None:
    """A suite that writes no coverage data selects nothing from coverage."""
    module = _selection()

    def execute(*, args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args, 4, "", f"unrecognized arguments in {cwd}")

    assert module.measure_per_test_coverage(target=tmp_path, execute=execute) is None


def test_a_real_pytest_cov_run_attributes_lines_to_test_node_ids(*, tmp_path: Path) -> None:
    """The real pytest-cov context format yields pytest node ids per executed line."""
    module = _selection()
    target = _package(root=tmp_path)
    (target / "tests").mkdir()
    _ = (target / "tests" / "test_core.py").write_text(_CORE_TESTS, encoding="utf-8")
    removed = {"COVERAGE_PROCESS_START", "COV_CORE_CONFIG", "COV_CORE_DATAFILE", "COV_CORE_SOURCE"}
    env = {key: value for key, value in os.environ.items() if key not in removed} | {
        "PYTHONPATH": str(target / "src")
    }

    def execute(*, args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            args=args, capture_output=True, check=False, cwd=cwd, env=env, text=True
        )

    coverage = module.measure_per_test_coverage(target=target, execute=execute)

    assert coverage is not None
    assert coverage["src/pkg/core.py"][2] == frozenset({"tests/test_core.py::test_f"})
    assert coverage["src/pkg/core.py"][7] == frozenset({"tests/test_core.py::test_g"})


@pytest.mark.parametrize("missing", ["", "x_", "xǁ"])
def test_identifiers_without_a_function_name_are_unlocated(*, tmp_path: Path, missing: str) -> None:
    """A malformed trampoline name cannot be paired with a body."""
    module = _selection()
    target = _package(root=tmp_path)

    assert module.locate_mutant(target=target, identifier=f"pkg.core.{missing}__mutmut_1") is None
