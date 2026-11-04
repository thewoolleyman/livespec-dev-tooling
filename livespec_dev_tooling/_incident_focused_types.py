"""Typed records shared by focused incident scope, measurement and proof."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, TypedDict

__all__: list[str] = [
    "CoverageDocument",
    "CoverageFile",
    "FocusedScope",
    "Identity",
    "ManualReproduction",
    "Measurement",
    "ResolvedContext",
]


class Identity(Protocol):
    incident_item_id: str
    attempt_id: str
    phase: str
    repository: str
    base_sha: str
    head_sha: str
    operation_id: str


class ResolvedContext(Protocol):
    mode: str
    identity: Identity | None


@dataclass(frozen=True, kw_only=True)
class ManualReproduction:
    """Operator-observed reproduction, preserved verbatim beside measured proof."""

    procedure: str
    expected: str
    observed: str
    outcome: str


@dataclass(frozen=True, kw_only=True)
class FocusedScope:
    """Exact tree and explicit cumulative file/test selection for one collection."""

    tree_hash: str
    source_prefixes: tuple[str, ...]
    test_prefixes: tuple[str, ...]
    related_tests: tuple[str, ...]
    prior_paths: tuple[str, ...] = ()
    related_test_reason: str = ""
    deferred_tests: tuple[tuple[str, str], ...] = ()
    timeout: float = 59


class CoverageSummary(TypedDict, total=False):
    percent_covered: float


class CoverageFile(TypedDict, total=False):
    summary: CoverageSummary
    missing_lines: list[int]
    missing_branches: list[list[int]]


class CoverageDocument(TypedDict):
    files: dict[str, CoverageFile]


@dataclass(frozen=True, kw_only=True)
class Measurement:
    selected: set[str]
    dispositions: dict[str, str]
    tests: dict[str, object]
    report: dict[str, object]
    coverage: dict[str, CoverageFile]
