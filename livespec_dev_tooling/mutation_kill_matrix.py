"""Engine-neutral report primitives for Rule-26 mutation kill matrices.

The report deliberately holds plain mutant identifiers, source locations, and
pytest-style test identities rather than a mutation engine's private data.
Adapters for mutmut, cargo-mutants, and other engines can therefore write the
same JSON document.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

__all__: list[str] = [
    "Mutant",
    "MutationKillMatrixReport",
    "build_report",
    "run_kill_matrix",
    "write_report",
]

_EMPTY_MUTANT_SET = "empty mutant set cannot produce a kill-matrix report"
_MUTMUT_GENERATION_FAILURE = "mutmut failed while generating the kill matrix"
_PYTEST_COLLECTION_FAILURE = "pytest did not collect tests for the kill matrix"
_REPORT_PATH = Path("reports/mutation-kill-matrix.json")
_MUTMUT_STATUSES = frozenset(
    {
        "check was interrupted by user",
        "killed",
        "no tests",
        "not checked",
        "skipped",
        "survived",
        "suspicious",
        "timeout",
    }
)


@dataclass(frozen=True, kw_only=True)
class Mutant:
    """A generated mutant represented independently of its producing engine."""

    identifier: str
    location: str


@dataclass(frozen=True, kw_only=True)
class MutationKillMatrixReport:
    """The portable, machine-readable Rule-26 report document."""

    engine: str
    engine_version: str
    source_revision: str
    mutants: tuple[Mutant, ...]
    killers_by_mutant: dict[str, tuple[str, ...]]
    redundancy_candidates: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        """Return the stable JSON-compatible report representation."""
        mutant_rows = [
            {
                "identifier": mutant.identifier,
                "location": mutant.location,
                "killed_by": list(self.killers_by_mutant[mutant.identifier]),
            }
            for mutant in self.mutants
        ]
        return {
            "engine": {"name": self.engine, "version": self.engine_version},
            "source_revision": self.source_revision,
            "mutants_generated": len(self.mutants),
            "mutants": mutant_rows,
            "surviving_mutants": [
                mutant.identifier
                for mutant in self.mutants
                if not self.killers_by_mutant[mutant.identifier]
            ],
            "redundancy_candidates": list(self.redundancy_candidates),
        }


def build_report(
    *,
    engine: str,
    engine_version: str,
    source_revision: str,
    mutants: list[Mutant],
    tests: list[str],
    killers_by_mutant: dict[str, set[str]],
) -> MutationKillMatrixReport:
    """Build a report, identifying tests with no uniquely killed mutant."""
    if not mutants:
        raise ValueError(_EMPTY_MUTANT_SET)
    normalized_killers = {
        mutant.identifier: tuple(sorted(killers_by_mutant.get(mutant.identifier, set())))
        for mutant in mutants
    }
    unique_killers = {
        killer for killers in normalized_killers.values() if len(killers) == 1 for killer in killers
    }
    return MutationKillMatrixReport(
        engine=engine,
        engine_version=engine_version,
        source_revision=source_revision,
        mutants=tuple(mutants),
        killers_by_mutant=normalized_killers,
        redundancy_candidates=tuple(sorted(set(tests) - unique_killers)),
    )


def write_report(*, report: MutationKillMatrixReport, path: Path) -> None:
    """Write one deterministic JSON report to its documented destination."""
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def run_command(
    *, args: list[str], cwd: Path, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """Run one mutmut or pytest command with text output captured."""
    return subprocess.run(
        args=args,
        capture_output=True,
        check=False,
        cwd=str(cwd),
        env=env,
        text=True,
    )


def _mutants_from_results(*, output: str) -> list[Mutant]:
    """Return the engine-neutral mutant rows from mutmut's public results CLI."""
    mutants: list[Mutant] = []
    for line in output.splitlines():
        identifier, separator, status = line.strip().rpartition(": ")
        if separator and status in _MUTMUT_STATUSES:
            mutants.append(Mutant(identifier=identifier, location=f"mutmut:{identifier}"))
    return mutants


def _pytest_node_ids(*, output: str) -> list[str]:
    """Extract collected pytest node IDs, excluding pytest's summary prose."""
    return sorted(
        line.strip()
        for line in output.splitlines()
        if line.strip().startswith("tests/") and "::" in line
    )


def run_kill_matrix(
    *, repo_root: Path, report_path: Path, source_revision: str
) -> MutationKillMatrixReport:
    """Run every collected pytest test against every mutmut-generated mutant."""
    run_result = run_command(
        args=[sys.executable, "-m", "mutmut", "run"],
        cwd=repo_root,
    )
    if run_result.returncode > 1:
        raise ValueError(_MUTMUT_GENERATION_FAILURE)
    results = run_command(
        args=[sys.executable, "-m", "mutmut", "results", "--all", "True"],
        cwd=repo_root,
    )
    mutants = _mutants_from_results(output=results.stdout)
    if not mutants:
        raise ValueError(_EMPTY_MUTANT_SET)
    mutants_root = repo_root / "mutants"
    collected = run_command(
        args=[sys.executable, "-m", "pytest", "--collect-only", "-q"],
        cwd=mutants_root,
    )
    tests = _pytest_node_ids(output=collected.stdout)
    if collected.returncode != 0 or not tests:
        raise ValueError(_PYTEST_COLLECTION_FAILURE)
    killers_by_mutant: dict[str, set[str]] = {}
    for mutant in mutants:
        killers: set[str] = set()
        for test in tests:
            environment = dict(os.environ)
            environment["MUTANT_UNDER_TEST"] = mutant.identifier
            environment["PY_IGNORE_IMPORTMISMATCH"] = "1"
            result = run_command(
                args=[sys.executable, "-m", "pytest", "-q", test],
                cwd=mutants_root,
                env=environment,
            )
            if result.returncode != 0:
                killers.add(test)
        killers_by_mutant[mutant.identifier] = killers
    report = build_report(
        engine="mutmut",
        engine_version="3.2.3",
        source_revision=source_revision,
        mutants=mutants,
        tests=tests,
        killers_by_mutant=killers_by_mutant,
    )
    write_report(report=report, path=report_path)
    return report


def main() -> int:
    """Generate the documented Rule-26 report for the repository at the cwd."""
    parser = argparse.ArgumentParser(description="Generate a Rule-26 mutation kill-matrix report.")
    _ = parser.add_argument("--report", type=Path, default=_REPORT_PATH)
    arguments = parser.parse_args()
    repo_root = Path.cwd()
    revision = run_command(
        args=["git", "rev-parse", "HEAD"],
        cwd=repo_root,
    ).stdout.strip()
    _ = run_kill_matrix(
        repo_root=repo_root,
        report_path=repo_root / arguments.report,
        source_revision=revision,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
