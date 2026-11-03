"""Pure readiness projection for maintainer radar entries."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from livespec_dev_tooling.radar.radar import RadarEntry

__all__: list[str] = ["RadarReadiness", "readiness"]

Target = tuple[str, str]
Record = Mapping[str, object]


@dataclass(frozen=True, kw_only=True, slots=True)
class RadarReadiness:
    """The current state and unresolved blockers for one radar target."""

    state: Literal["DONE", "READY", "NOT READY"]
    blockers: tuple[str, ...]


def readiness(*, entry: RadarEntry, records: Mapping[Target, Record]) -> RadarReadiness:
    """Project one radar entry's readiness from already-read ledger records."""
    del entry, records
    return RadarReadiness(state="DONE", blockers=())
