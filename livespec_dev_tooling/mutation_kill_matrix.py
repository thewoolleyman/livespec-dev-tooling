"""Engine-neutral report primitives for Rule-26 mutation kill matrices.

The report deliberately holds plain mutant identifiers, source locations, and
pytest-style test identities rather than a mutation engine's private data.
Adapters for mutmut, cargo-mutants, and other engines can therefore write the
same JSON document.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

__all__: list[str] = ["Mutant", "MutationKillMatrixReport", "build_report", "write_report"]


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
