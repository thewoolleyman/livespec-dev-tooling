"""One vantage's reading of the incident enablement record, and the armed fence on it.

The reading is exactly one of `enabled`, `absent`, `stale`, `revoked`, `unavailable` or
`no-installation`. `armed` is the installation's arming state as its answer echoes it,
or None when the vantage holds no answer (an unreachable query route, or no
installation): a vantage that cannot know the arming state never refuses on it.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Protocol, cast

__all__: list[str] = [
    "READINGS",
    "REVERT_PHASES",
    "EnablementReader",
    "EnablementReading",
    "answer_reading",
    "fence_refusal",
]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-exdkra
READINGS = frozenset({"enabled", "absent", "stale", "revoked", "unavailable", "no-installation"})
REVERT_PHASES = frozenset({"reverting", "emergency-revert"})
_ANSWERED = READINGS - {"no-installation"}


@dataclass(frozen=True, kw_only=True)
class EnablementReading:
    """What one vantage read, from which installation, and the arming state it echoed."""

    reading: str
    armed: bool | None
    installation: str
    detail: str = ""

    def record(self) -> dict[str, Any]:
        """The reading as the vantage's artefact records it."""
        return asdict(self)


class EnablementReader(Protocol):
    """Read the enablement record for one repository at this vantage."""

    def __call__(self, *, repository: str) -> EnablementReading: ...


def answer_reading(
    *,
    answer: object,
    installation: str,
    repository: str,
    compare_own: bool = False,
    own_identity: str | None = None,
) -> EnablementReading:
    """Parse an installation's query answer; an unparseable one is `unavailable`.

    With `compare_own` (the hooks compare against their own read of core, `own_identity`),
    an `enabled` answer whose confirmed identity differs from that read reads `stale`, and
    `unavailable` when that own read failed.
    """
    reply = cast("dict[str, Any]", answer) if isinstance(answer, dict) else {}
    armed: object = reply.get("armed")
    status: object = reply.get("status")
    if (
        status not in _ANSWERED
        or not isinstance(armed, bool)
        or reply.get("query") != {"repository": repository}
    ):
        detail = str(reply.get("reason", "the query answer is malformed"))
        return EnablementReading(
            reading="unavailable", armed=None, installation=installation, detail=detail
        )
    reading = status
    confirmed = reply.get("confirmed_manifest_sha256")
    detail = "" if confirmed is None else f"confirmed {confirmed}"
    if compare_own and reading == "enabled" and confirmed != own_identity:
        reading = "unavailable" if own_identity is None else "stale"
        detail = f"controller confirmed {confirmed}; own read of core: {own_identity or 'failed'}"
    return EnablementReading(reading=reading, armed=armed, installation=installation, detail=detail)


def fence_refusal(*, reading: EnablementReading, repository: str, revert: bool) -> str | None:
    """Name the refusal an armed installation's not-enabled reading requires, or None.

    Expedited repair is refused on every reading but `enabled`; an emergency revert on
    every such reading except `unavailable`. A disarmed or unknown arming state refuses
    nothing: the vantage records its reading and continues.
    """
    if (
        reading.armed is not True
        or reading.reading == "enabled"
        or (revert and reading.reading == "unavailable")
    ):
        return None
    named = f"{reading.reading} ({reading.detail})" if reading.detail else reading.reading
    where = f"{repository} at installation {reading.installation}"
    return f"incident mode is not enabled for {where}: {named}"
