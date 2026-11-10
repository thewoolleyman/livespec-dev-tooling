"""Consistency checks for the result of a verified canonical history reply.

The authority client has already checked the process protocol. This decoder checks
only the exact attribution. It does not read an authority store, validate a token
chain, authorize current effects or manufacture normal proof.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import cast

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.result import Failure, Result, Success  # noqa: E402 — vendor-path-aware import.

from livespec_dev_tooling._incident_provenance_types import (  # noqa: E402
    HistoricalIncidentProof,
    IncidentCommitQuery,
    IncidentProvenanceRefusal,
)

__all__: list[str] = ["decode_historical_result"]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-gvylzw
_IDENTITY_FIELDS = (
    "repository",
    "item_id",
    "attempt_id",
    "phase",
    "operation_id",
    "generation",
    "owner",
    "base",
    "head",
    "pr_number",
)


def _texts(*, value: object) -> tuple[str, ...] | None:
    if not isinstance(value, list) or not all(
        isinstance(entry, str) for entry in cast(list[object], value)
    ):
        return None
    return tuple(cast(list[str], value))


def _refuse(
    *, code: str, detail: str
) -> Result[HistoricalIncidentProof, IncidentProvenanceRefusal]:
    return Failure(IncidentProvenanceRefusal(code=code, detail=detail))


def _invalid() -> Result[HistoricalIncidentProof, IncidentProvenanceRefusal]:
    return _refuse(
        code="incident-reader-invalid-response",
        detail="canonical history reader did not supply a complete schema-1 historical reply",
    )


def decode_historical_result(
    *, result: dict[str, object], query: IncidentCommitQuery
) -> Result[HistoricalIncidentProof, IncidentProvenanceRefusal]:
    raw_attempt = result.get("attempt")
    committed = result.get("committed_token_id")
    current = result.get("current_token_id")
    if (
        not isinstance(raw_attempt, dict)
        or not isinstance(committed, str)
        or not committed
        or not isinstance(current, str)
        or not current
    ):
        return _invalid()
    attempt = cast(dict[str, object], raw_attempt)
    if any(
        type(attempt.get(field)) is not type(getattr(query, field))
        or attempt.get(field) != getattr(query, field)
        for field in _IDENTITY_FIELDS
    ):
        return _refuse(
            code="incident-provenance-identity-mismatch",
            detail="historical reply does not match the exact recorded incident receipt",
        )
    commits = _texts(value=attempt.get("landed_commits"))
    trees = _texts(value=attempt.get("landed_trees"))
    paths = _texts(value=attempt.get("original_paths"))
    deferred = _texts(value=attempt.get("deferred_work"))
    repayment = attempt.get("repayment_required")
    if (
        commits is None
        or trees is None
        or paths is None
        or not paths
        or deferred is None
        or type(repayment) is not bool
        or len(commits) != len(trees)
    ):
        return _invalid()
    # The identity check above already proved `query.head` is the recorded head.
    # An unmerged expedited PR has no landed pair yet, and its head is the record.
    if query.commit_sha != query.head and (query.commit_sha, query.tree_sha) not in tuple(
        zip(commits, trees, strict=True)
    ):
        return _refuse(
            code="incident-provenance-identity-mismatch",
            detail="commit is neither the recorded head nor a recorded landed pair of this attempt",
        )
    return Success(
        HistoricalIncidentProof(
            query=query,
            committed_token_id=committed,
            current_token_id=current,
            original_paths=paths,
            deferred_work=deferred,
            repayment_required=repayment,
        )
    )
