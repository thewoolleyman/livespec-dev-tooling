"""Original-run observations are evidence, never another incident lifecycle."""

from __future__ import annotations

from dataclasses import dataclass

__all__: list[str] = [
    "CorrectedAttempt",
    "EvidenceDebt",
    "EvidenceRefusal",
    "ExpectedJob",
    "JobEvidence",
    "ObservedJob",
    "OriginalRun",
    "RunEvidence",
    "RunSnapshot",
]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-kobmka


@dataclass(frozen=True, kw_only=True)
class EvidenceRefusal:
    code: str
    detail: str


@dataclass(frozen=True, kw_only=True)
class ExpectedJob:
    name: str
    needs: tuple[str, ...] = ()


@dataclass(frozen=True, kw_only=True)
class OriginalRun:
    """A canonical, retained identity with a graph read at the original revision."""

    repository: str
    item_id: str
    attempt_id: str
    operation_id: str
    generation: int
    owner: str
    pr_number: int
    merge_sha: str
    tree_sha: str
    revert_sha: str
    run_id: int
    run_attempt: int
    workflow_path: str
    graph_revision: str
    graph_digest: str
    expected: tuple[ExpectedJob, ...]


@dataclass(frozen=True, kw_only=True)
class ObservedJob:
    name: str
    job_id: int
    status: str
    conclusion: str | None
    evidence_url: str


@dataclass(frozen=True, kw_only=True)
class RunSnapshot:
    repository: str
    run_id: int
    run_attempt: int
    head_sha: str
    status: str
    jobs: tuple[ObservedJob, ...]
    graph_digest: str
    complete_listing: bool


@dataclass(frozen=True, kw_only=True)
class JobEvidence:
    name: str
    state: str
    job_id: int | None
    conclusion: str | None
    evidence_url: str


@dataclass(frozen=True, kw_only=True)
class EvidenceDebt:
    job_name: str
    owner: str
    original_tree: str
    continuation_id: str
    reason: str


@dataclass(frozen=True, kw_only=True)
class RunEvidence:
    original: OriginalRun
    source_snapshot: RunSnapshot
    terminal: bool
    jobs: tuple[JobEvidence, ...]
    debts: tuple[EvidenceDebt, ...]


@dataclass(frozen=True, kw_only=True)
class CorrectedAttempt:
    """A proposal for the canonical writer; this does not create an attempt."""

    original: OriginalRun
    evidence_digest: str
    classification_receipt: str
    next_attempt_id: str
    next_head_sha: str
    repair_diff_digest: str
    resolved_jobs: tuple[tuple[str, str], ...]
