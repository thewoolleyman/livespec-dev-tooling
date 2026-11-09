"""Replay a journaled rollback-conflict onto the canonical incident chain.

`incident_inverse` hands a genuine overlap to the recovery principal, whose durable
result is the recovery journal. The journal is the controller's own record and
stays available when the tenant is not, but it is not the incident item's
lifecycle: only the orchestrator's `record-rollback-conflict` action writes the
`rollback-conflict` phase and the `blocked` status. This module is that action's
one caller in dev-tooling.

The write goes through the manifest's installed canonical reader command, the
same process `CurrentAuthorityReader` uses, and names the CURRENT `reverting`
generation it acts on. It takes nothing from caller JSON: the orchestrator
re-reads the chain and refuses an identity that is not that generation.

Every field of the payload is a function of the journaled receipt, so a repeat
for the same action and head (after a timeout or a restart) sends byte-identical
bytes, and the orchestrator recovers its one recorded transition rather than
adding a second. A reply that does not prove the transition, or no reply at all,
returns False: the conflict stays in the journal and the caller replays it later.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from livespec_dev_tooling._incident_inverse_types import (
    InverseConflictRequest,
    InverseForge,
    LandedIncident,
    RecoveryOutcome,
)
from livespec_dev_tooling._incident_observer_types import RecoveryIntent

__all__: list[str] = [
    "ConflictChain",
    "is_conflict_receipt",
    "record_inverse_conflict",
    "replay_conflict",
]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-fdquen
_ACTION = "record-rollback-conflict"
_REVERTING = "reverting"
_CONFLICT_PHASE = "rollback-conflict"
_BLOCKED = "blocked"
_RECEIPT_PREFIX = "rollback-conflict:"


def is_conflict_receipt(*, receipt: str | None) -> bool:
    """Whether a recorded receipt is a journaled conflict rather than a revert merge."""
    return receipt is not None and receipt.startswith(_RECEIPT_PREFIX)


def replay_conflict(
    *, intent: RecoveryIntent, receipt: str | None, chain: ConflictChain | None
) -> None:
    """Carry a journaled conflict to the canonical chain; a failed write is retried later.

    The write is idempotent on the chain, so replaying an already-recorded conflict
    adds no transition. The result is deliberately unused: the journal alone decides
    the outcome, and an unreachable tenant must not turn a recorded conflict pending.
    """
    if chain is not None and receipt is not None and is_conflict_receipt(receipt=receipt):
        _ = chain.record(intent=intent, receipt=receipt)


def record_inverse_conflict(
    *,
    intent: RecoveryIntent,
    scope: LandedIncident,
    head: str,
    reason: str,
    forge: InverseForge,
    chain: ConflictChain | None,
) -> RecoveryOutcome:
    """Journal one genuine overlap through the principal, then replay it onto the chain."""
    receipt = forge.record_conflict(
        request=InverseConflictRequest(
            intent=intent,
            scope=scope,
            expected_head=head,
            reason=reason,
            receipt=(
                f"{_RECEIPT_PREFIX}{intent.action_id}:owner:{intent.registration.owner}:head:{head}"
            ),
        )
    )
    replay_conflict(intent=intent, receipt=receipt, chain=chain)
    return RecoveryOutcome(
        status="rollback-conflict" if receipt else "pending",
        reason="overlapping later work requires identified owner resolution",
        receipt=receipt,
    )


@dataclass(frozen=True, kw_only=True)
class ConflictChain:
    """The installed canonical reader as the writer of one owned rollback-conflict."""

    command: tuple[str, ...]
    repo: Path
    timeout_seconds: int = 45

    def record(self, *, intent: RecoveryIntent, receipt: str) -> bool:
        """True only when the reply proves the conflict is on the chain, blocked."""
        if not self.command:
            return False
        identity = _identity(intent=intent)
        conflict = {
            "receipt": receipt,
            "release_condition": f"the incident owner resolves the later-work overlap: {receipt}",
        }
        argv = [
            *self.command,
            _ACTION,
            "--repo",
            str(self.repo),
            *[part for name, value in identity.items() for part in ("--" + name, str(value))],
            "--rollback-conflict-json",
            json.dumps(conflict, sort_keys=True, separators=(",", ":")),
        ]
        return _recorded(reply=self._read_reply(argv=argv), identity=identity)

    def _read_reply(self, *, argv: list[str]) -> object:
        try:
            done = subprocess.run(  # noqa: S603 -- approved installed reader argv; no shell or request command.
                argv,
                cwd=self.repo,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
            return json.loads(done.stdout) if done.returncode == 0 else None
        except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
            return None


def _identity(*, intent: RecoveryIntent) -> dict[str, str | int]:
    """The `reverting` generation a conflict is owed to.

    A regression reopen names its own generation; any other cause names the
    registration, which the orchestrator refuses unless that is `reverting`.
    """
    registration = intent.registration
    regression = intent.regression
    return {
        "repository": registration.repository,
        "item": registration.incident_item_id,
        "attempt": registration.attempt_id if regression is None else regression.attempt_id,
        "phase": _REVERTING if regression is not None else registration.phase,
        "operation": registration.operation_id if regression is None else regression.operation_id,
        "generation": registration.generation if regression is None else regression.generation,
        "owner": registration.owner if regression is None else regression.owner,
    }


def _mapping(*, value: object) -> dict[str, object]:
    return cast("dict[str, object]", value) if isinstance(value, dict) else {}


def _recorded(*, reply: object, identity: dict[str, str | int]) -> bool:
    body = _mapping(value=reply)
    if (
        type(body.get("schema")) is not int
        or body.get("schema") != 1
        or body.get("status") != "verified"
        or body.get("normal_factory_proof") is not False
    ):
        return False
    result = _mapping(value=body.get("result"))
    attempt = _mapping(value=_mapping(value=result.get("reading")).get("attempt"))
    generation = identity["generation"]
    return (
        result.get("lifecycle_state") == _BLOCKED
        and attempt.get("phase") == _CONFLICT_PHASE
        and attempt.get("repository") == identity["repository"]
        and attempt.get("item_id") == identity["item"]
        and attempt.get("owner") == identity["owner"]
        and type(attempt.get("generation")) is int
        and isinstance(generation, int)
        and attempt.get("generation") == generation + 1
    )
