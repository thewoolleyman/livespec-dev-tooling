"""The Rule-26 kill matrix's preparation stages: generate, measure and plan.

1. `generate` writes mutmut's mutant catalogue, lists it and collects the
   target's tests.  It calls the pinned mutmut 3.2.3's own generation
   functions rather than `mutmut run`, which would go on to run mutmut's own
   stats pass, a clean test run and a forked run of every mutant, all of
   which this engine discards.
2. `measure` runs the suite once under per-test coverage.  The same run
   records each test's outcome and duration on the unmutated source, so a test
   that fails there, or runs longer than the per-test timeout, is a baseline
   failure and takes no part in attribution.  This run arms no per-test timer:
   a timer kills its process, and with it the coverage data.
3. `plan_mutants` locates each mutant's function, selects the tests whose
   coverage executes it (see `mutation_kill_matrix_selection`), and computes
   its cache key (see `mutation_kill_matrix_cache`).
"""

from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from livespec_dev_tooling.mutation_kill_matrix import Mutant
from livespec_dev_tooling.mutation_kill_matrix_cache import CacheKeys
from livespec_dev_tooling.mutation_kill_matrix_execution import (
    PLUGIN_MODULE,
    PYTHON,
    CommandExecutor,
    WorkerTree,
    outcome_environment,
    read_outcomes,
    run_selected,
)
from livespec_dev_tooling.mutation_kill_matrix_selection import (
    MutantSpan,
    PerTestCoverage,
    locate_mutant,
    measure_per_test_coverage,
    select_tests,
)

__all__: list[str] = [
    "ENGINE_VERSION",
    "MutantPlan",
    "generate",
    "measure",
    "plan_mutants",
]


ENGINE_VERSION = "3.2.3"
_GENERATION_FAILED = "mutmut could not generate mutants for the kill matrix"
# What `mutmut run` does before it starts testing, and nothing after: it sets
# the same environment marker, reads the [tool.mutmut] configuration, and
# writes the catalogue under mutants/.
_GENERATE = (
    "import os\n"
    "from pathlib import Path\n"
    "os.environ['MUTANT_UNDER_TEST'] = 'mutant_generation'\n"
    "import mutmut.__main__ as mutmut_cli\n"
    "mutmut_cli.read_config()\n"
    "Path('mutants').mkdir(exist_ok=True)\n"
    "mutmut_cli.create_mutants()\n"
    "mutmut_cli.copy_also_copy_files()\n"
)
_NO_MUTANTS = "mutmut generated no mutants for the kill matrix"


@dataclass(frozen=True, kw_only=True)
class MutantPlan:
    """One mutant's located span, the tests selected to run against it, and its cache key."""

    mutant: Mutant
    span: MutantSpan | None
    selected: list[str]
    key: str


def _mutants_from_results(*, output: str) -> list[Mutant]:
    """Translate mutmut's public results rows into portable mutant rows."""
    rows = [line.strip().rpartition(": ") for line in output.strip().splitlines()]
    return [
        Mutant(identifier=identifier, location=f"mutmut:{identifier}") for identifier, _, _ in rows
    ]


def _collected_tests(*, output: str) -> list[str]:
    """Extract pytest node IDs from quiet collection output."""
    return sorted(line.strip() for line in output.splitlines() if "::" in line and " " not in line)


def _checked_command(
    *, execute: CommandExecutor, args: list[str], target: Path, failure: str
) -> subprocess.CompletedProcess[str]:
    """Run a setup command that must succeed before attribution can be sound."""
    result = execute(args=args, cwd=target)
    if result.returncode != 0:
        raise RuntimeError(failure)
    return result


def generate(*, execute: CommandExecutor, target: Path) -> tuple[list[Mutant], list[str]]:
    """Generate and list mutmut's mutants, then collect the target's tests."""
    generated = execute(args=[*PYTHON, "-c", _GENERATE], cwd=target)
    if generated.returncode != 0:
        raise RuntimeError(_GENERATION_FAILED)
    results = _checked_command(
        execute=execute,
        args=[*PYTHON, "-m", "mutmut", "results", "--all", "True"],
        target=target,
        failure="mutmut results failed while listing generated mutants",
    )
    mutants = _mutants_from_results(output=results.stdout)
    if not mutants:
        raise RuntimeError(_NO_MUTANTS)
    collected = _checked_command(
        execute=execute,
        args=[*PYTHON, "-m", "pytest", "--collect-only", "-q", "--ignore=mutants"],
        target=target,
        failure="pytest collection failed for the kill matrix",
    )
    return mutants, _collected_tests(output=collected.stdout)


def measure(
    *, execute: CommandExecutor, target: Path, tests: list[str], timeout: float
) -> tuple[PerTestCoverage | None, frozenset[str]]:
    """Measure per-test coverage and, from the same run, the baseline failures.

    Any test the coverage run did not report (its process died first) is run
    again against the unmutated target, this time under the per-test timer.
    """
    with tempfile.TemporaryDirectory(prefix="kill-matrix-baseline-") as scratch:
        outcomes = Path(scratch) / "baseline-outcomes.jsonl"
        coverage = measure_per_test_coverage(
            target=target,
            execute=execute,
            environment=outcome_environment(outcomes=outcomes, timeout=0.0),
            plugin_args=("-p", PLUGIN_MODULE),
        )
        recorded = read_outcomes(outcomes=outcomes, slower_than=timeout)
        missing = [test for test in tests if test not in recorded]
        if missing:
            baseline = WorkerTree(root=target, scratch=Path(scratch))
            recorded |= run_selected(execute=execute, tree=baseline, tests=missing, timeout=timeout)
    return coverage, frozenset(test for test in tests if recorded.get(test, False))


def plan_mutants(
    *,
    execute: CommandExecutor,
    target: Path,
    generated: list[Mutant],
    attributable: list[str],
    coverage: PerTestCoverage | None,
    timeout: float,
) -> list[MutantPlan]:
    """Locate every mutant, select its tests and compute its cache key."""
    spans = {
        mutant.identifier: locate_mutant(target=target, identifier=mutant.identifier)
        for mutant in generated
    }
    # Judge "measured" only on the files that hold mutants: tests sit inside
    # the measured tree, so every test's own body would otherwise give it a
    # context, and a test that reaches the source only where coverage cannot
    # follow (a bare subprocess) would never run against any mutant.
    source_paths = {span.path for span in spans.values() if span is not None}
    source_coverage = (
        None
        if coverage is None
        else {path: lines for path, lines in coverage.items() if path in source_paths}
    )
    keys = CacheKeys(
        target=target,
        coverage=coverage,
        engine_version=ENGINE_VERSION,
        timeout=timeout,
        execute=execute,
    )
    plans: list[MutantPlan] = []
    for generated_mutant in generated:
        span = spans[generated_mutant.identifier]
        mutant = (
            generated_mutant
            if span is None
            else Mutant(
                identifier=generated_mutant.identifier,
                location=span.location(),
                function_digest=span.function_digest,
            )
        )
        selected = select_tests(span=span, coverage=source_coverage, tests=attributable)
        key = keys.key(identifier=mutant.identifier, span=span, selected=selected)
        plans.append(MutantPlan(mutant=mutant, span=span, selected=selected, key=key))
    return plans
