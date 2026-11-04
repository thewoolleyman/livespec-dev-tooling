"""Non-authorizing results at the protected recovery journal boundary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

__all__: list[str] = ["JournalResult", "RetainedAction"]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-dln3ac


@dataclass(frozen=True, kw_only=True)
class JournalResult:
    """An effect observation or reservation, never a forge mutation grant."""

    status: Literal["absent", "reserved", "recorded", "refused", "unavailable"]
    reason: str
    receipt: str | None = None
    request_sha256: str | None = None
    authorizes_current_effects: Literal[False] = False


@dataclass(frozen=True, kw_only=True)
class RetainedAction:
    """The independently retained immutable action and its separate disposition."""

    intent: dict[str, Any]
    status: str
    receipt: str | None
