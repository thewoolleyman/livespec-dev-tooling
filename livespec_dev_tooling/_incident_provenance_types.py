"""Queries and immutable historical proofs for the canonical authority process."""

from __future__ import annotations

from dataclasses import dataclass

__all__: list[str] = ["HistoricalIncidentProof", "IncidentCommitQuery", "IncidentProvenanceRefusal"]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-gvylzw


@dataclass(frozen=True, kw_only=True)
class IncidentCommitQuery:
    """The exact receipt and landed commit a normal historical reader verifies."""

    repository: str
    item_id: str
    attempt_id: str
    phase: str
    operation_id: str
    generation: int
    owner: str
    base: str
    head: str
    pr_number: int
    commit_sha: str
    tree_sha: str


@dataclass(frozen=True, kw_only=True)
class IncidentProvenanceRefusal:
    """A named failure, distinct from ordinary mode or normal verification."""

    code: str
    detail: str


@dataclass(frozen=True, kw_only=True)
class HistoricalIncidentProof:
    """Historical attribution only: this grants no current effects or normal proof."""

    query: IncidentCommitQuery
    committed_token_id: str
    current_token_id: str
    original_paths: tuple[str, ...]
    deferred_work: tuple[str, ...]
    repayment_required: bool
