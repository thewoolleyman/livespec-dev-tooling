"""Retain complete original-run facts and gate canonical correction proposals."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict

from livespec_dev_tooling._incident_run_types import (
    CorrectedAttempt,
    EvidenceDebt,
    EvidenceRefusal,
    ExpectedJob,
    JobEvidence,
    OriginalRun,
    RunEvidence,
    RunSnapshot,
)

__all__: list[str] = ["build_run_evidence", "evidence_digest", "validate_correction"]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-kobmka
_FAILED = frozenset(("failure", "timed_out", "action_required", "startup_failure"))
_CONCLUSIONS = _FAILED | {"success", "neutral", "skipped", "cancelled", "stale"}
_ACTIVE = frozenset(("queued", "in_progress", "waiting", "pending", "requested"))


def _refuse(*, detail: str) -> EvidenceRefusal:
    return EvidenceRefusal(code="incident-original-run-invalid", detail=detail)


def _graph_valid(*, original: OriginalRun) -> bool:
    names = {job.name for job in original.expected}
    if not names or len(names) != len(original.expected) or "" in names:
        return False
    remaining = {job.name: set(job.needs) for job in original.expected}
    if any(not needs <= names for needs in remaining.values()):
        return False
    while remaining:
        roots = {name for name, needs in remaining.items() if not needs}
        if not roots:
            return False
        remaining = {name: needs - roots for name, needs in remaining.items() if name not in roots}
    return True


def _identity_valid(*, original: OriginalRun, snapshot: RunSnapshot) -> bool:
    return (
        all(
            (
                original.repository,
                original.item_id,
                original.attempt_id,
                original.operation_id,
                original.owner,
                original.merge_sha,
                original.tree_sha,
                original.revert_sha,
                original.workflow_path,
                original.graph_digest,
            )
        )
        and all(
            type(v) is int and v > 0
            for v in (
                original.pr_number,
                original.generation,
                original.run_id,
                original.run_attempt,
            )
        )
        and original.graph_revision == original.merge_sha
        and (
            snapshot.repository,
            snapshot.run_id,
            snapshot.run_attempt,
            snapshot.head_sha,
            snapshot.graph_digest,
        )
        == (
            original.repository,
            original.run_id,
            original.run_attempt,
            original.merge_sha,
            original.graph_digest,
        )
        and snapshot.complete_listing is True
        and _graph_valid(original=original)
    )


def _states(*, original: OriginalRun, snapshot: RunSnapshot) -> tuple[JobEvidence, ...]:
    by_name = {job.name: job for job in snapshot.jobs}
    result: dict[str, JobEvidence] = {}
    remaining: list[ExpectedJob] = list(original.expected)
    while remaining:
        for expected in tuple(remaining):
            if not set(expected.needs) <= result.keys():
                continue
            observed = by_name.get(expected.name)
            blocked = any(result[name].state != "completed" for name in expected.needs)
            if observed is None:
                state = "never-created" if snapshot.status == "completed" else "pending"
            elif observed.status != "completed":
                state = "pending"
            elif observed.conclusion == "success":
                state = "completed"
            elif observed.conclusion in _FAILED:
                state = "failed"
            elif observed.conclusion == "skipped":
                state = "prerequisite-blocked" if blocked else "skipped"
            else:
                state = "cancelled" if observed.conclusion == "cancelled" else "unverified"
            result[expected.name] = JobEvidence(
                name=expected.name,
                state=state,
                job_id=observed.job_id if observed else None,
                conclusion=observed.conclusion if observed else None,
                evidence_url=observed.evidence_url if observed else "",
            )
            remaining.remove(expected)
    return tuple(result[job.name] for job in original.expected)


def build_run_evidence(
    *, original: OriginalRun, snapshot: RunSnapshot, continuation_id: str
) -> RunEvidence | EvidenceRefusal:
    """A terminal workflow cannot turn absent or skipped checks into executed proof."""
    if not continuation_id or not _identity_valid(original=original, snapshot=snapshot):
        return _refuse(detail="incomplete identity, graph, listing or debt continuation")
    if snapshot.status not in _ACTIVE | {"completed"}:
        return _refuse(detail="unsupported original run status")
    names = [job.name for job in snapshot.jobs]
    ids = [job.job_id for job in snapshot.jobs]
    if len(names) != len(set(names)) or len(ids) != len(set(ids)):
        return _refuse(detail="duplicate original-attempt job identity")
    if any(
        type(job.job_id) is not int
        or job.job_id <= 0
        or not job.evidence_url
        or job.status not in _ACTIVE | {"completed"}
        or (job.status == "completed" and job.conclusion not in _CONCLUSIONS)
        or (job.status != "completed" and job.conclusion is not None)
        or (snapshot.status == "completed" and job.status != "completed")
        for job in snapshot.jobs
    ):
        return _refuse(detail="inconsistent or incomplete authenticated job observation")
    jobs = _states(original=original, snapshot=snapshot)
    debts = tuple(
        EvidenceDebt(
            job_name=job.name,
            owner=original.owner,
            original_tree=original.tree_sha,
            continuation_id=continuation_id,
            reason=job.state,
        )
        for job in jobs
        if job.state not in {"completed", "failed"}
    )
    return RunEvidence(
        original=original,
        source_snapshot=snapshot,
        terminal=snapshot.status == "completed",
        jobs=jobs,
        debts=debts,
    )


def evidence_digest(*, evidence: RunEvidence) -> str:
    """Bind classification and correction to the entire collected original scope."""
    return hashlib.sha256(json.dumps(asdict(evidence), sort_keys=True).encode()).hexdigest()


def validate_correction(
    *, evidence: RunEvidence, proposal: CorrectedAttempt
) -> CorrectedAttempt | EvidenceRefusal:
    """Admit a proposal only; the canonical lifecycle writer owns the transition."""
    if (
        not evidence.terminal
        or proposal.original != evidence.original
        or proposal.evidence_digest != evidence_digest(evidence=evidence)
        or not proposal.classification_receipt
        or not proposal.next_attempt_id
        or proposal.next_attempt_id == evidence.original.attempt_id
        or not proposal.next_head_sha
    ):
        return _refuse(
            detail="correction needs terminal original evidence and exact classification"
        )
    resolved = dict(proposal.resolved_jobs)
    if len(resolved) != len(proposal.resolved_jobs) or any(
        not value for value in resolved.values()
    ):
        return _refuse(detail="measured resolutions need distinct checks and retained receipts")
    obligations = {job.name for job in evidence.jobs if job.state != "completed"}
    if not set(resolved) <= obligations:
        return _refuse(detail="resolution names a check outside the original unresolved set")
    repaired = proposal.next_head_sha != evidence.original.merge_sha and bool(
        proposal.repair_diff_digest
    )
    if not repaired and (not obligations or not obligations <= resolved.keys()):
        return _refuse(
            detail="unchanged reland needs measured resolution of every revealed problem"
        )
    return proposal
