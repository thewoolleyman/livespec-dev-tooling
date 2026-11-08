"""Mutmut adapter for the portable Rule-26 mutation kill-matrix report.

The report model lives separately so other mutation engines can emit exactly
the same document.  This adapter uses only mutmut's public command-line
surface: it enumerates generated mutants, applies one at a time, and invokes
the collected pytest nodes that coverage pairs with that mutant while it is
present (see `mutation_kill_matrix_selection`).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Protocol

from livespec_dev_tooling.mutation_kill_matrix import (
    Mutant,
    MutationKillMatrixReport,
    build_report,
    write_report,
)
from livespec_dev_tooling.mutation_kill_matrix_selection import (
    COVERAGE_GUIDED_METHOD,
    FULL_MATRIX_METHOD,
    locate_mutant,
    measure_per_test_coverage,
    select_tests,
)

__all__: list[str] = [
    "execute_command",
    "main",
    "run_kill_matrix",
    "source_revision",
]


_REPORT_PATH = Path("reports/mutation-kill-matrix.json")
_MUTMUT_RUN_FAILED = "mutmut run failed while generating the kill matrix"
_NO_MUTANTS = "mutmut generated no mutants for the kill matrix"
# `-B`: an applied mutant usually has the source's size and lands within the
# same second, so a cached `.pyc` would pass its mtime-and-size check and the
# test would run the unmutated module. No child writes bytecode.
_PYTHON = (sys.executable, "-B")


class CommandExecutor(Protocol):
    """Run one command from a package root and capture its result."""

    def __call__(self, *, args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]: ...


def execute_command(*, args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Execute one adapter command without raising for test failures."""
    return subprocess.run(args=args, capture_output=True, check=False, cwd=str(cwd), text=True)


def source_revision(*, target: Path) -> str:
    """Return the target's revision, or a useful value for a standalone fixture."""
    result = execute_command(args=["git", "rev-parse", "HEAD"], cwd=target)
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def _mutants_from_results(*, output: str) -> list[Mutant]:
    """Translate mutmut's public results rows into portable mutant rows."""
    rows = [line.strip().rpartition(": ") for line in output.strip().splitlines()]
    return [
        Mutant(identifier=identifier, location=f"mutmut:{identifier}") for identifier, _, _ in rows
    ]


def _collected_tests(*, output: str) -> list[str]:
    """Extract pytest node IDs from quiet collection output."""
    return sorted(line.strip() for line in output.splitlines() if "::" in line and " " not in line)


def _source_snapshot(*, target: Path) -> dict[Path, bytes]:
    """Capture source bytes so each applied mutant starts from the clean package."""
    return {
        path: path.read_bytes()
        for path in target.rglob("*.py")
        if "mutants" not in path.relative_to(target).parts
    }


def _restore_sources(*, snapshot: dict[Path, bytes]) -> None:
    """Restore the target after a mutant application or a failed test command."""
    for path, content in snapshot.items():
        _ = path.write_bytes(content)


def _checked_command(
    *, execute: CommandExecutor, args: list[str], target: Path, failure: str
) -> subprocess.CompletedProcess[str]:
    """Run a setup command that must succeed before attribution can be sound."""
    result = execute(args=args, cwd=target)
    if result.returncode != 0:
        raise RuntimeError(failure)
    return result


def run_kill_matrix(
    *, target: Path, source_revision: str, execute: CommandExecutor = execute_command
) -> MutationKillMatrixReport:
    """Run each mutmut mutant against the tests that execute it and write one report.

    A mutmut run creates its on-disk mutant catalogue.  The suite then runs
    once under per-test coverage, and each mutant is located at the function
    body it mutates.  Each following ``mutmut apply`` changes one mutant into
    the package, then every test selected for it runs separately; a test not
    selected is recorded as not killing it.  A non-zero pytest result is that
    test's kill.  The source snapshot makes this destructive-looking public
    CLI operation safe for the package being measured.
    """
    generated = execute(args=[*_PYTHON, "-m", "mutmut", "run"], cwd=target)
    if generated.returncode not in (0, 1):
        raise RuntimeError(_MUTMUT_RUN_FAILED)
    results = _checked_command(
        execute=execute,
        args=[*_PYTHON, "-m", "mutmut", "results", "--all", "True"],
        target=target,
        failure="mutmut results failed while listing generated mutants",
    )
    generated_mutants = _mutants_from_results(output=results.stdout)
    if not generated_mutants:
        raise RuntimeError(_NO_MUTANTS)
    collected = _checked_command(
        execute=execute,
        args=[*_PYTHON, "-m", "pytest", "--collect-only", "-q"],
        target=target,
        failure="pytest collection failed for the kill matrix",
    )
    tests = _collected_tests(output=collected.stdout)
    coverage = measure_per_test_coverage(target=target, execute=execute)
    spans = {
        mutant.identifier: locate_mutant(target=target, identifier=mutant.identifier)
        for mutant in generated_mutants
    }
    mutants = [
        Mutant(identifier=mutant.identifier, location=span.location())
        if (span := spans[mutant.identifier]) is not None
        else mutant
        for mutant in generated_mutants
    ]
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
    snapshot = _source_snapshot(target=target)
    killers_by_mutant: dict[str, set[str]] = {}
    try:
        for mutant in mutants:
            _restore_sources(snapshot=snapshot)
            _ = _checked_command(
                execute=execute,
                args=[*_PYTHON, "-m", "mutmut", "apply", mutant.identifier],
                target=target,
                failure=f"mutmut could not apply mutant {mutant.identifier}",
            )
            killers_by_mutant[mutant.identifier] = {
                test
                for test in select_tests(
                    span=spans[mutant.identifier], coverage=source_coverage, tests=tests
                )
                if execute(args=[*_PYTHON, "-m", "pytest", "-q", test], cwd=target).returncode != 0
            }
    finally:
        _restore_sources(snapshot=snapshot)
    report = build_report(
        engine_name="mutmut",
        engine_version="3.2.3",
        source_revision=source_revision,
        test_selection_method=FULL_MATRIX_METHOD if coverage is None else COVERAGE_GUIDED_METHOD,
        mutants=mutants,
        tests=tests,
        killers_by_mutant=killers_by_mutant,
    )
    write_report(report=report, path=target / _REPORT_PATH)
    return report


def main() -> int:
    """Generate a Rule-26 report for the target package path supplied by just."""
    parser = argparse.ArgumentParser(description="Generate a Rule-26 mutation kill matrix.")
    _ = parser.add_argument(
        "target", type=Path, help="package root containing pyproject.toml and tests"
    )
    arguments = parser.parse_args()
    target = arguments.target.resolve()
    if not target.is_dir():
        parser.error(f"target package path is not a directory: {target}")
    _ = run_kill_matrix(
        target=target,
        source_revision=source_revision(target=target),
        execute=execute_command,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
