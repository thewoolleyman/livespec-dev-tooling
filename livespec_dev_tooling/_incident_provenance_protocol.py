"""Consistency checks for replies from the registered canonical history reader.

Only the process adapter calls this decoder. It does not read an authority store,
validate a token chain, authorize current effects or manufacture normal proof.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import cast

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.pipeline import is_successful  # noqa: E402 — vendor-path-aware import.
from returns.result import Failure, Result, Success, safe  # noqa: E402 — vendor-path-aware import.

from livespec_dev_tooling._incident_provenance_types import (  # noqa: E402
    HistoricalIncidentProof,
    IncidentCommitQuery,
    IncidentProvenanceRefusal,
)

__all__: list[str] = ["decode_historical_reply"]

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
_REFUSED_EXIT = 78


def _object(*, pairs: list[tuple[str, object]]) -> dict[str, object] | None:
    """Poison duplicate-key objects instead of silently retaining the last value."""
    value = dict(pairs)
    return value if len(value) == len(pairs) else None


@safe
def _json(*, text: str) -> object:
    """JSON parsing is a data boundary with an expected failure channel."""
    return cast(object, json.loads(text, object_pairs_hook=lambda pairs: _object(pairs=pairs)))


def _mapping(*, value: object) -> dict[str, object]:
    return cast(dict[str, object], value) if isinstance(value, dict) else {}


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


def _verified(
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
    if (query.commit_sha, query.tree_sha) not in tuple(zip(commits, trees, strict=True)):
        return _refuse(
            code="incident-provenance-identity-mismatch",
            detail="commit and tree are not a recorded landed pair for this incident attempt",
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


def _canonical_refusal(
    *, response: dict[str, object], result: dict[str, object]
) -> Result[HistoricalIncidentProof, IncidentProvenanceRefusal]:
    code = result.get("code")
    detail = result.get("detail")
    if (
        response.get("status") == "refused"
        and isinstance(code, str)
        and code
        and isinstance(detail, str)
    ):
        return _refuse(code=code, detail=detail)
    return _invalid()


def decode_historical_reply(
    *, stdout: str, returncode: int, query: IncidentCommitQuery
) -> Result[HistoricalIncidentProof, IncidentProvenanceRefusal]:
    """Check the process protocol and exact attribution without accepting normal proof."""
    if returncode not in {0, _REFUSED_EXIT}:
        return _refuse(
            code="incident-reader-unavailable", detail="canonical history process failed"
        )
    parsed = _json(text=stdout)
    if not is_successful(parsed):
        return _invalid()
    response = _mapping(value=parsed.unwrap())
    if (
        type(response.get("schema")) is not int
        or response.get("schema") != 1
        or response.get("authorizes_current_effects") is not False
        or response.get("normal_factory_proof") is not False
    ):
        return _invalid()
    result = _mapping(value=response.get("result"))
    if returncode == _REFUSED_EXIT:
        return _canonical_refusal(response=response, result=result)
    if response.get("status") != "verified":
        return _invalid()
    return _verified(result=result, query=query)
