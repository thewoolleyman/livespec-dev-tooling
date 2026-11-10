"""The chain generations a rollback-conflict write names, and the replies that prove them.

The orchestrator's `reopen-regression` and `record-rollback-conflict` actions each act on
one exact chain generation, named by the authority's shared identity flags and re-read
by the orchestrator. This module owns that identity (`Generation`), the one canonical
payload encoding, and the checks of what each action's reply must prove; the writer in
`incident_conflict_chain` owns the calls themselves.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any, cast

from livespec_dev_tooling._incident_observer_types import ObserverRegistration

__all__: list[str] = [
    "Generation",
    "canonical",
    "proves_conflict",
    "recorded_reopen",
    "reopen_reply",
    "say",
]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-fdquen
_REVERTING = "reverting"
_CONFLICT_PHASE = "rollback-conflict"
_BLOCKED = "blocked"


@dataclass(frozen=True, kw_only=True)
class Generation:
    """One chain generation exactly as the authority's identity flags name it."""

    repository: str
    item: str
    attempt: str
    phase: str
    operation: str
    generation: int
    owner: str

    @classmethod
    def of(cls, *, registration: ObserverRegistration) -> Generation:
        return cls(
            repository=registration.repository,
            item=registration.incident_item_id,
            attempt=registration.attempt_id,
            phase=registration.phase,
            operation=registration.operation_id,
            generation=registration.generation,
            owner=registration.owner,
        )

    def flags(self) -> dict[str, object]:
        return {
            "repository": self.repository,
            "item": self.item,
            "attempt": self.attempt,
            "phase": self.phase,
            "operation": self.operation,
            "generation": self.generation,
            "owner": self.owner,
        }


def canonical(*, value: Mapping[str, object]) -> str:
    """The canonical encoding the orchestrator requires of every JSON payload."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def say(*, words: str) -> None:
    _ = sys.stderr.write(f"incident-conflict-chain: {words}\n")


def _mapping(*, value: object) -> dict[str, Any]:
    return cast("dict[str, Any]", value) if isinstance(value, dict) else {}


def _attempt(*, result: dict[str, Any]) -> dict[str, Any]:
    return _mapping(value=_mapping(value=result.get("reading")).get("attempt"))


def _same_incident(*, attempt: dict[str, Any], identity: Generation) -> bool:
    return (
        attempt.get("repository") == identity.repository
        and attempt.get("item_id") == identity.item
        and attempt.get("owner") == identity.owner
    )


def _next_generation(*, attempt: dict[str, Any], identity: Generation) -> bool:
    return type(attempt.get("generation")) is int and attempt.get("generation") == (
        identity.generation + 1
    )


def reopen_reply(*, result: dict[str, Any], current: Generation) -> Generation | None:
    """The `reverting` generation a reopen recorded, or None when the reply is anything else."""
    attempt = _attempt(result=result)
    attempt_id, operation = attempt.get("attempt_id"), attempt.get("operation_id")
    if (
        attempt.get("phase") != _REVERTING
        or not _same_incident(attempt=attempt, identity=current)
        or not _next_generation(attempt=attempt, identity=current)
        or not isinstance(attempt_id, str)
        or not isinstance(operation, str)
    ):
        say(words="the reopen reply is not the reverting generation of this incident")
        return None
    return replace(
        current,
        attempt=attempt_id,
        phase=_REVERTING,
        operation=operation,
        generation=current.generation + 1,
    )


def recorded_reopen(*, current: Generation, finding: Mapping[str, object]) -> Generation:
    """The generation an already-recorded reopen produced, named the way the orchestrator names it.

    A reopen names the merged attempt the chain has already moved past, which the orchestrator
    refuses as a stale observation. Its successor is `recovery-<digest>` over the attempt it
    acted on and the finding (`operation_digest` in `_incident_recovery_plan.py`); the chain
    verifies this identity, so a wrong derivation is a refusal and never a wrong write.
    """
    digest = hashlib.sha256(
        canonical(
            value={
                "item_id": current.item,
                "operation_id": current.operation,
                "generation": current.generation,
                "finding": finding,
            }
        ).encode()
    ).hexdigest()[:24]
    attempt = f"recovery-{digest}"
    return replace(
        current,
        attempt=attempt,
        phase=_REVERTING,
        operation=f"{attempt}#{_REVERTING}",
        generation=current.generation + 1,
    )


def proves_conflict(*, result: dict[str, Any], identity: Generation) -> bool:
    attempt = _attempt(result=result)
    return (
        result.get("lifecycle_state") == _BLOCKED
        and attempt.get("phase") == _CONFLICT_PHASE
        and attempt.get("attempt_id") == identity.attempt
        and _same_incident(attempt=attempt, identity=identity)
        and _next_generation(attempt=attempt, identity=identity)
    )
