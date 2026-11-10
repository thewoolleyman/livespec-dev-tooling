"""Coverage-guided test selection for the Rule-26 mutation kill matrix.

Per-test coverage is measured once, with pytest-cov's per-test contexts, and
each mutmut mutant is located at the function body it mutates.  A mutant then
runs only against the tests whose coverage executes that body.  Every case the
measurement cannot vouch for falls back to running every test: a test absent
from the coverage data the caller passes, a mutant whose function cannot be
located, and a function body executed outside any test (at import or
collection time).  The runner passes only the mutated source files' coverage,
so a test that executes none of their lines, such as one that reaches the
source only through an unmeasured subprocess, counts as absent.
"""

from __future__ import annotations

import ast
import hashlib
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from coverage import CoverageData

__all__: list[str] = [
    "COVERAGE_GUIDED_METHOD",
    "FULL_MATRIX_METHOD",
    "MutantLocator",
    "MutantSpan",
    "PerTestCoverage",
    "locate_mutant",
    "measure_per_test_coverage",
    "measured_tests",
    "select_tests",
    "text_digest",
]


COVERAGE_GUIDED_METHOD = (
    "coverage-guided: each mutant runs against the tests whose pytest-cov per-test context "
    "executes its mutated function body; tests that execute no line of a mutated source file, "
    "mutants whose function cannot be located, and bodies executed outside any test run "
    "against every test"
)
FULL_MATRIX_METHOD = (
    "full-matrix: per-test coverage could not be measured, so every collected test runs "
    "against every mutant"
)

_SKIPPED_PARTS = frozenset({"mutants", ".venv", "node_modules"})
_OUTSIDE_ANY_TEST = ""

# A source-relative POSIX path, then line number, then the tests whose
# per-test context executed that line (the empty name is "no test").
PerTestCoverage = dict[str, dict[int, frozenset[str]]]
Executor = Callable[..., object]


@dataclass(frozen=True, kw_only=True)
class MutantSpan:
    """The function body a mutant mutates, as a source-relative line range."""

    path: str
    first_line: int
    last_line: int
    function_digest: str | None = None

    def location(self) -> str:
        """Render the span as the report's portable mutant location."""
        return f"{self.path}:{self.first_line}-{self.last_line}"


def _module_files(*, target: Path) -> dict[str, Path]:
    """Map each first-party module's mutmut dotted name to its source file."""
    modules: dict[str, Path] = {}
    for path in target.rglob("*.py"):
        relative = path.relative_to(target)
        if _SKIPPED_PARTS.intersection(relative.parts):
            continue
        parts = relative.with_suffix("").parts
        dotted = ".".join(parts[:-1] if parts[-1] == "__init__" else parts)
        modules[dotted.removeprefix("src.")] = path
    return modules


def _function_names(*, mangled: str) -> tuple[str, ...]:
    """Decode mutmut's trampoline name into a function or class-and-method path."""
    name = mangled.rpartition("__mutmut_")[0]
    if name.startswith("xǁ"):
        return tuple(name[2:].split("ǁ"))
    if name.startswith("x_"):
        return (name[2:],)
    return ()


def _find_function(*, body: list[ast.stmt], names: tuple[str, ...]) -> ast.stmt | None:
    """Find a top-level function, or a method of a top-level class, by name."""
    head, *rest = names
    for node in body:
        if getattr(node, "name", None) != head:
            continue
        if not rest and isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            return node
        if rest and isinstance(node, ast.ClassDef):
            return _find_function(body=node.body, names=tuple(rest))
    return None


class MutantLocator:
    """Locate mutants against one snapshot of the target.

    The tree is walked once and each source file is read and parsed at most
    once, however many mutants it holds: a real target generates tens of
    thousands of mutants, and a walk and parse per mutant took hours.
    """

    def __init__(self, *, target: Path) -> None:
        self._target = target
        self._modules = _module_files(target=target)
        self._parsed: dict[Path, tuple[str, list[ast.stmt]]] = {}

    def _parse(self, *, source: Path) -> tuple[str, list[ast.stmt]]:
        """Read and parse one source file, once."""
        if source not in self._parsed:
            text = source.read_text(encoding="utf-8")
            self._parsed[source] = (text, ast.parse(text).body)
        return self._parsed[source]

    def locate(self, *, identifier: str) -> MutantSpan | None:
        """Locate the function body a mutmut mutant identifier names, if it can be found."""
        module, _, mangled = identifier.rpartition(".")
        names = _function_names(mangled=mangled)
        source = self._modules.get(module)
        if not names or source is None:
            return None
        text, body = self._parse(source=source)
        function = _find_function(body=body, names=names)
        if not isinstance(function, ast.FunctionDef | ast.AsyncFunctionDef):
            return None
        return MutantSpan(
            path=source.relative_to(self._target).as_posix(),
            first_line=function.body[0].lineno,
            last_line=function.end_lineno or function.body[-1].lineno,
            function_digest=text_digest(text=ast.get_source_segment(text, function) or ""),
        )


def locate_mutant(*, target: Path, identifier: str) -> MutantSpan | None:
    """Locate one mutant; a caller locating many builds one `MutantLocator` instead."""
    return MutantLocator(target=target).locate(identifier=identifier)


def text_digest(*, text: str) -> str:
    """Return the stable digest the report and the result cache use for source text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _test_name(*, context: str) -> str:
    """Strip pytest-cov's `|setup`, `|run` or `|teardown` phase from a context."""
    return context.rpartition("|")[0] if "|" in context else context


def _read_coverage(*, data_file: Path, target: Path) -> PerTestCoverage | None:
    """Read per-test line contexts for the target's files from one coverage data file."""
    if not data_file.is_file():
        return None
    data = CoverageData(basename=str(data_file))
    data.read()
    root = target.resolve()
    coverage: PerTestCoverage = {}
    for measured in data.measured_files():
        path = Path(measured).resolve()
        if not path.is_relative_to(root):
            continue
        coverage[path.relative_to(root).as_posix()] = {
            line: frozenset(_test_name(context=context) for context in contexts)
            for line, contexts in data.contexts_by_lineno(measured).items()
        }
    return coverage or None


def measure_per_test_coverage(
    *,
    target: Path,
    execute: Executor,
    environment: tuple[str, ...] = (),
    plugin_args: tuple[str, ...] = (),
) -> PerTestCoverage | None:
    """Run the target's suite once under per-test contexts and return its line coverage.

    The suite's own exit status is not consulted: a failing test still has a
    coverage context.  No data at all means coverage could not be measured.
    `COVERAGE_FILE` is set explicitly because an inherited one outranks the
    rcfile, and would send this run's data into the caller's own data file.
    `environment` and `plugin_args` let the caller record each test's outcome
    on the unmutated source from this same run.
    """
    with tempfile.TemporaryDirectory(prefix="kill-matrix-coverage-") as workdir:
        data_file = Path(workdir) / ".coverage"
        rcfile = Path(workdir) / "coveragerc"
        _ = rcfile.write_text(f"[run]\ndata_file = {data_file}\n", encoding="utf-8")
        _ = execute(
            args=[
                "env",
                f"COVERAGE_FILE={data_file}",
                *environment,
                sys.executable,
                "-B",
                "-m",
                "pytest",
                "-q",
                "-p",
                "no:cacheprovider",
                f"--cov={target}",
                f"--cov-config={rcfile}",
                "--cov-context=test",
                "--cov-report=",
                # mutmut copies the tests into mutants/; without `testpaths`
                # pytest would collect both copies and fail on the duplicates.
                "--ignore=mutants",
                *plugin_args,
            ],
            cwd=target,
        )
        return _read_coverage(data_file=data_file, target=target)


def measured_tests(*, coverage: PerTestCoverage) -> frozenset[str]:
    """Name every test with a coverage context anywhere in `coverage`."""
    return frozenset(
        name for file in coverage.values() for names in file.values() for name in names
    )


def select_tests(
    *,
    span: MutantSpan | None,
    coverage: PerTestCoverage | None,
    tests: list[str],
    measured: frozenset[str] | None = None,
) -> list[str]:
    """Return the tests one mutant must run against, in collection order.

    `measured` is `measured_tests(coverage=coverage)`; a caller selecting for
    many mutants computes it once and passes it, because it folds the whole
    coverage map.
    """
    if span is None or coverage is None:
        return list(tests)
    lines = coverage.get(span.path, {})
    executing = {
        name
        for line in range(span.first_line, span.last_line + 1)
        for name in lines.get(line, frozenset[str]())
    }
    if _OUTSIDE_ANY_TEST in executing:
        return list(tests)
    known = measured_tests(coverage=coverage) if measured is None else measured
    return [test for test in tests if test in executing or test not in known]
