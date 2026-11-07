"""The canonical side of original-run collection: authority reads and item records.

The original identity is authenticated against the canonical attempt history,
collected evidence is recorded on the incident work item once per digest, and
a validated correction is handed to the canonical writer. None of these
operations is emulated from local state.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, cast

from livespec_dev_tooling._incident_observer_types import ObserverRegistration
from livespec_dev_tooling._incident_run_types import CorrectedAttempt, OriginalRun, RunEvidence
from livespec_dev_tooling.incident_run_collector import CanonicalRunAdapter

__all__: list[str] = [
    "EVIDENCE_MARKER",
    "AuthorityPort",
    "CanonicalPorts",
    "CorrectionTarget",
    "LedgerPort",
    "authority_query",
    "canonical_adapter",
    "recorded_digests",
]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-zvntys
EVIDENCE_MARKER = "livespec-incident-original-run-evidence-v1"
_CONFLICT = "the incident item already records other evidence for this original run"

AuthorityPort = Callable[[str, Mapping[str, object], Mapping[str, str]], dict[str, Any]]
LedgerPort = Callable[[Sequence[str]], str]


@dataclass(frozen=True, kw_only=True)
class CanonicalPorts:
    """The registered incident authority process and the incident item's ledger."""

    authority: AuthorityPort
    ledger: LedgerPort


def _canonical(*, value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def authority_query(*, registration: ObserverRegistration) -> dict[str, object]:
    """The whole fenced identity the controller registered for the original run."""
    return {
        "repository": registration.repository,
        "item": registration.incident_item_id,
        "attempt": registration.attempt_id,
        "phase": registration.phase,
        "operation": registration.operation_id,
        "generation": registration.generation,
        "owner": registration.owner,
    }


def _run_key(*, original: OriginalRun) -> dict[str, object]:
    return {
        "item_id": original.item_id,
        "attempt_id": original.attempt_id,
        "generation": original.generation,
        "run_id": original.run_id,
        "run_attempt": original.run_attempt,
    }


def recorded_digests(*, ports: CanonicalPorts, original: OriginalRun) -> tuple[str, ...]:
    """Evidence digests the incident item records for exactly this original run."""
    comments = cast("object", json.loads(ports.ledger(["comments", original.item_id, "--json"])))
    rows = cast("list[object]", comments) if isinstance(comments, list) else []
    key = _run_key(original=original)
    digests: list[str] = []
    for row in rows:
        text = cast("dict[str, object]", row).get("text") if isinstance(row, dict) else None
        if not isinstance(text, str) or not text.startswith(EVIDENCE_MARKER + "\n"):
            continue
        body = cast("object", json.loads(text.removeprefix(EVIDENCE_MARKER + "\n")))
        if not isinstance(body, dict):
            continue
        record = cast("dict[str, object]", body)
        digest = record.get("digest")
        if all(record.get(name) == value for name, value in key.items()) and isinstance(
            digest, str
        ):
            digests.append(digest)
    return tuple(digests)


@dataclass(frozen=True, kw_only=True)
class _Authorize:
    ports: CanonicalPorts
    registration: ObserverRegistration

    def __call__(self, original: OriginalRun) -> bool:
        query = authority_query(registration=self.registration)
        result = self.ports.authority("read-history", query, {})
        attempt = result.get("attempt")
        if not isinstance(attempt, dict):
            return False
        record = cast("dict[str, object]", attempt)
        landed = record.get("landed_commits")
        expected = {
            "repository": original.repository,
            "item_id": original.item_id,
            "attempt_id": original.attempt_id,
            "operation_id": original.operation_id,
            "generation": original.generation,
            "owner": original.owner,
            "pr_number": original.pr_number,
        }
        return (
            all(record.get(name) == value for name, value in expected.items())
            and isinstance(landed, list)
            and original.merge_sha in cast("list[object]", landed)
        )


@dataclass(frozen=True, kw_only=True)
class _Record:
    ports: CanonicalPorts

    def __call__(self, evidence: RunEvidence, digest: str) -> str:
        original = evidence.original
        existing = recorded_digests(ports=self.ports, original=original)
        if digest in existing:
            return digest
        if existing:
            raise ValueError(_CONFLICT)
        body = {
            **_run_key(original=original),
            "digest": digest,
            "merge_sha": original.merge_sha,
            "revert_sha": original.revert_sha,
            "terminal": evidence.terminal,
            "jobs": [[job.name, job.state, job.conclusion, job.job_id] for job in evidence.jobs],
            "debts": [debt.job_name for debt in evidence.debts],
        }
        _ = self.ports.ledger(
            ["comments", "add", original.item_id, EVIDENCE_MARKER + "\n" + _canonical(value=body)]
        )
        return digest


@dataclass(frozen=True, kw_only=True)
class CorrectionTarget:
    """What the canonical `correct-attempt` action needs beyond a validated proposal.

    `query` names the CURRENT attempt, which a recorded revert receipt has moved
    to `collecting-failures`; `base` and `staged_tree` are measured from Git and
    `target_ref` is the corrected attempt's reserved branch.
    """

    query: dict[str, object]
    base: str
    staged_tree: str
    target_ref: str


@dataclass(frozen=True, kw_only=True)
class _Correct:
    ports: CanonicalPorts
    target: CorrectionTarget

    def __call__(self, proposal: CorrectedAttempt, digest: str) -> str:
        target = self.target
        resolutions = _canonical(value=[digest, [list(pair) for pair in proposal.resolved_jobs]])
        evidence_id = (
            proposal.repair_diff_digest or hashlib.sha256(resolutions.encode()).hexdigest()
        )
        correction = {
            "base": target.base,
            "evidence_id": evidence_id,
            "head": proposal.next_head_sha,
            "kind": "repair" if proposal.repair_diff_digest else "measured-resolution",
            "staged_tree": target.staged_tree,
        }
        payload = {"correction-json": _canonical(value=correction), "target-ref": target.target_ref}
        receipt = self.ports.authority("correct-attempt", target.query, payload).get("operation_id")
        return receipt if isinstance(receipt, str) else ""


def canonical_adapter(
    *,
    ports: CanonicalPorts,
    registration: ObserverRegistration,
    target: CorrectionTarget | None = None,
) -> CanonicalRunAdapter:
    """Bind the collector's canonical capability to one registered original run.

    Without a correction target the adapter cannot correct: its writer returns
    no receipt, which the collector refuses.
    """
    return CanonicalRunAdapter(
        authorize=_Authorize(ports=ports, registration=registration),
        record=_Record(ports=ports),
        correct=_Correct(ports=ports, target=target) if target else (lambda _proposal, _digest: ""),
    )
