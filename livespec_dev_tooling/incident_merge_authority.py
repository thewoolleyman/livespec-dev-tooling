"""Whether the incident-merge principal MAY merge one pull request, from the chain alone.

`SPECIFICATION/contracts.md` "Expedited incident execution", paragraph
"Incident-merge principal": the canonical incident authority chain is the SOLE
authority for an incident merge. This module is that decision, pure over an
injected chain reader. It reads no label, no `EXPEDITED_INCIDENT_RESPONSE`
environment flag, no other flag or environment variable and no commit subject,
so none of them can stand in for a genesis record.

The reader returns the same verified-result shape `call_authority` checks, and a
reader refusal is any named refusal (`AuthorityRefusal` satisfies it). This module
never reaches the authority process itself: the caller that does injects the
reader, so it stays off the provenance guard's authority-caller allowlist. A
verified reading carries the
current attempt record the canonical `read-current` reply already publishes
(`attempt`, `is_current`) plus two fields the merge decision needs and nothing
else yet reads: `genesis_writer`, the writer action that published the item's
genesis record, and `item_status`, the incident work item's stored status.

The forge-side conditions (the `expedited-incident-response` label and the
effective required-check set concluded `success` on the head) and the merge
itself belong to the caller; this decision covers the chain's half only.
"""

from __future__ import annotations

import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol, cast

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.pipeline import is_successful  # noqa: E402 — vendor-path-aware import.
from returns.result import Result  # noqa: E402 — vendor-path-aware import.

__all__: list[str] = [
    "GENESIS_WRITER_ACTION",
    "MERGE_REFUSAL_REASONS",
    "MergeAuthorityVerdict",
    "MergeChainReader",
    "MergeRefusalReason",
    "NamedRefusal",
    "decide",
]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-u3nbm3

MergeRefusalReason = Literal[
    "no-genesis-record",
    "incident-closed",
    "attempt-superseded",
    "attempt-not-pr-bound",
    "pr-number-mismatch",
    "base-head-mismatch",
    "incident-inverse",
]
MERGE_REFUSAL_REASONS: frozenset[str] = frozenset(
    (
        "no-genesis-record",
        "incident-closed",
        "attempt-superseded",
        "attempt-not-pr-bound",
        "pr-number-mismatch",
        "base-head-mismatch",
        "incident-inverse",
    )
)
# The incident authority writer's genesis action: the only genesis that authorizes.
# `file-incident` files the item and claim and writes no chain root.
GENESIS_WRITER_ACTION = "publish-genesis"
_CLOSED_STATUS = "closed"
# The orchestrator's phase table (`_incident_phases.py`): the finished phases, the
# recovery phases whose only merge is the recovery principal's inverse, and the
# one phase in which an expedited repair PR is the attempt's own carrier.
_CLOSED_PHASES = frozenset(("closed", "drill-closed"))
_INVERSE_PHASES = frozenset(("reverting", "rollback-conflict"))
_REPAIR_PHASE = "repair"
_PR_BOUND = "pr-bound"


class NamedRefusal(Protocol):
    """A reader's named refusal: the shape of the authority client's `AuthorityRefusal`."""

    @property
    def code(self) -> str: ...
    @property
    def detail(self) -> str: ...


class MergeChainReader(Protocol):
    """Reads the canonical incident authority chain for one incident work item."""

    def __call__(self, *, incident_id: str) -> Result[dict[str, Any], NamedRefusal]: ...


@dataclass(frozen=True, kw_only=True)
class MergeAuthorityVerdict:
    """Allowed (`reason` None), or refused with exactly one named reason."""

    allowed: bool
    reason: MergeRefusalReason | None
    detail: str


def _refuse(*, reason: MergeRefusalReason, detail: str) -> MergeAuthorityVerdict:
    return MergeAuthorityVerdict(allowed=False, reason=reason, detail=detail)


def _bound_refusal(
    *, attempt: Mapping[str, object], pr_number: int, base_sha: str, head_sha: str
) -> MergeAuthorityVerdict | None:
    """The current attempt must be pr-bound to THIS PR at its forge-read base and head."""
    carrier = attempt.get("carrier")
    empty: Mapping[str, object] = {}
    shape = cast("Mapping[str, object]", carrier) if isinstance(carrier, dict) else empty
    state = shape.get("state")
    bound = attempt.get("pr_number")
    if state != _PR_BOUND or type(bound) is not int or bound <= 0:
        return _refuse(reason="attempt-not-pr-bound", detail="current attempt binds no PR")
    if bound != pr_number:
        return _refuse(reason="pr-number-mismatch", detail=f"chain binds PR {bound}")
    if (attempt.get("base"), attempt.get("head")) != (base_sha, head_sha):
        return _refuse(reason="base-head-mismatch", detail="forge-read base/head differ")
    return None


def _attempt_refusal(
    *, reading: Mapping[str, object], attempt: Mapping[str, object], incident_id: str
) -> MergeAuthorityVerdict | None:
    phase = attempt.get("phase")
    if reading.get("item_status") == _CLOSED_STATUS or phase in _CLOSED_PHASES:
        return _refuse(reason="incident-closed", detail=incident_id)
    if reading.get("is_current") is not True:
        return _refuse(reason="attempt-superseded", detail="bound attempt is not current")
    if phase in _INVERSE_PHASES:
        return _refuse(reason="incident-inverse", detail=f"current phase {phase}")
    if phase != _REPAIR_PHASE:
        return _refuse(reason="attempt-superseded", detail=f"current phase {phase}")
    return None


def decide(
    *,
    reader: MergeChainReader,
    incident_id: str,
    pr_number: int,
    base_sha: str,
    head_sha: str,
) -> MergeAuthorityVerdict:
    """Allow the merge only when the incident authority chain alone authorizes it.

    A reader that cannot establish the chain (a missing, ambiguous or invalid
    genesis, or an outage) refuses as `no-genesis-record`, naming the authority's
    own code in the detail: the merge fails closed, never open.
    """
    checked = reader(incident_id=incident_id)
    if not is_successful(checked):
        refusal = checked.failure()
        return _refuse(reason="no-genesis-record", detail=f"{refusal.code}: {refusal.detail}")
    reading = checked.unwrap()
    writer = reading.get("genesis_writer")
    if writer != GENESIS_WRITER_ACTION:
        return _refuse(
            reason="no-genesis-record",
            detail=f"genesis not written by {GENESIS_WRITER_ACTION} (found {writer!r})",
        )
    raw = reading.get("attempt")
    if not isinstance(raw, dict):
        return _refuse(reason="attempt-not-pr-bound", detail="chain publishes no current attempt")
    attempt = cast("Mapping[str, object]", raw)
    if attempt.get("item_id") != incident_id:
        return _refuse(reason="no-genesis-record", detail="chain names another incident")
    verdict = _attempt_refusal(reading=reading, attempt=attempt, incident_id=incident_id) or (
        _bound_refusal(attempt=attempt, pr_number=pr_number, base_sha=base_sha, head_sha=head_sha)
    )
    return verdict or MergeAuthorityVerdict(allowed=True, reason=None, detail=incident_id)
