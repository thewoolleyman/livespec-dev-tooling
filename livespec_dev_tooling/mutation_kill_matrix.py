"""Portable Rule-26 mutation kill-matrix report primitives.

The report intentionally contains only mutant identifiers, source locations,
function digests and test node identifiers.  That keeps the artifact usable by
mutmut, cargo-mutants, and shell or TypeScript mutation engines without
encoding any engine-private state.

Every field except `run` is matrix content: two runs over the same source
revision carry the same matrix content whatever their worker count or cache.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

__all__: list[str] = [
    "RUN_METADATA_FIELD",
    "Mutant",
    "MutationKillMatrixReport",
    "RunMetadata",
    "build_report",
    "matrix_content",
    "write_json",
    "write_report",
]


RUN_METADATA_FIELD = "run"


@dataclass(frozen=True, kw_only=True)
class Mutant:
    """A generated mutant represented independently of its producing engine."""

    identifier: str
    location: str
    function_digest: str | None = None


@dataclass(frozen=True, kw_only=True)
class RunMetadata:
    """How one run was executed; the only report fields that are not matrix content."""

    workers: int = 1
    incremental: bool = False
    reused_mutants: int = 0


@dataclass(frozen=True, kw_only=True)
class MutationKillMatrixReport:
    """The portable, machine-readable Rule-26 report document."""

    engine_name: str
    engine_version: str
    source_revision: str
    test_selection_method: str
    mutants: tuple[Mutant, ...]
    tests: tuple[str, ...]
    killers_by_mutant: dict[str, tuple[str, ...]]
    unapplied_mutants: tuple[str, ...]
    baseline_failures: tuple[str, ...]
    redundancy_candidates: tuple[str, ...]
    unapplied_coverage_tests: tuple[str, ...]
    per_test_timeout_seconds: float | None
    run: RunMetadata = field(default_factory=RunMetadata)

    def to_dict(self) -> dict[str, object]:
        """Return the stable JSON-compatible report representation."""
        unapplied = set(self.unapplied_mutants)
        return {
            "engine": {"name": self.engine_name, "version": self.engine_version},
            "source_revision": self.source_revision,
            "test_selection_method": self.test_selection_method,
            "per_test_timeout_seconds": self.per_test_timeout_seconds,
            "mutants_generated": len(self.mutants),
            "mutants_applied": len(self.mutants) - len(unapplied),
            "mutants_unapplied": len(unapplied),
            "mutants": [
                _mutant_row(mutant=mutant, killers=self.killers_by_mutant)
                for mutant in self.mutants
            ],
            "tests": list(self.tests),
            "surviving_mutants": [
                mutant.identifier
                for mutant in self.mutants
                if mutant.identifier not in unapplied
                and not self.killers_by_mutant[mutant.identifier]
            ],
            "unapplied_mutants": list(self.unapplied_mutants),
            "baseline_failures": list(self.baseline_failures),
            "redundancy_candidates": list(self.redundancy_candidates),
            "unapplied_coverage_tests": list(self.unapplied_coverage_tests),
            RUN_METADATA_FIELD: {
                "workers": self.run.workers,
                "incremental": self.run.incremental,
                "reused_mutants": self.run.reused_mutants,
            },
        }


def _mutant_row(*, mutant: Mutant, killers: dict[str, tuple[str, ...]]) -> dict[str, object]:
    """Render one mutant; the digest appears only when its function was located."""
    row: dict[str, object] = {
        "identifier": mutant.identifier,
        "location": mutant.location,
        "killed_by": list(killers[mutant.identifier]),
    }
    if mutant.function_digest is not None:
        row["function_digest"] = mutant.function_digest
    return row


def build_report(  # noqa: PLR0913 — one keyword per field the spec v165 report carries.
    *,
    engine_name: str,
    engine_version: str,
    source_revision: str,
    test_selection_method: str,
    mutants: list[Mutant],
    tests: list[str],
    killers_by_mutant: dict[str, set[str]],
    unapplied_mutants: frozenset[str] = frozenset(),
    selected_for_unapplied: frozenset[str] = frozenset(),
    baseline_failures: frozenset[str] = frozenset(),
    per_test_timeout_seconds: float | None = None,
    run: RunMetadata | None = None,
) -> MutationKillMatrixReport:
    """Build a report that attributes each mutant to its killing tests.

    A test is valuable when it killed a mutant no other test killed.  Every
    other test is an unapplied-coverage test when it was selected for a mutant
    the engine could not apply (that mutant may be the one only it catches),
    and a redundancy candidate otherwise.  A baseline failure is neither,
    because its value was never measured.
    """
    normalized_killers = {
        mutant.identifier: ()
        if mutant.identifier in unapplied_mutants
        else tuple(sorted(killers_by_mutant.get(mutant.identifier, set()) - baseline_failures))
        for mutant in mutants
    }
    unique_killers = {
        killer for killers in normalized_killers.values() if len(killers) == 1 for killer in killers
    }
    unvalued = set(tests) - baseline_failures - unique_killers
    unapplied_coverage = unvalued & selected_for_unapplied
    return MutationKillMatrixReport(
        engine_name=engine_name,
        engine_version=engine_version,
        source_revision=source_revision,
        test_selection_method=test_selection_method,
        mutants=tuple(mutants),
        tests=tuple(sorted(tests)),
        killers_by_mutant=normalized_killers,
        unapplied_mutants=tuple(
            mutant.identifier for mutant in mutants if mutant.identifier in unapplied_mutants
        ),
        baseline_failures=tuple(sorted(baseline_failures & set(tests))),
        redundancy_candidates=tuple(sorted(unvalued - unapplied_coverage)),
        unapplied_coverage_tests=tuple(sorted(unapplied_coverage)),
        per_test_timeout_seconds=per_test_timeout_seconds,
        run=run or RunMetadata(),
    )


def matrix_content(*, document: dict[str, object]) -> dict[str, object]:
    """Return a report document without its run metadata."""
    return {key: value for key, value in document.items() if key != RUN_METADATA_FIELD}


def write_report(*, report: MutationKillMatrixReport, path: Path) -> None:
    """Write one deterministic report to its documented destination."""
    write_json(document=report.to_dict(), path=path)


def write_json(*, document: dict[str, object], path: Path) -> None:
    """Write one deterministic JSON document, creating its directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
