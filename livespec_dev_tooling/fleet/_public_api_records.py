"""_public_api_records — what a consumption measurement PRODUCES, not how it is taken.

Split out of `_public_api_graph`, which keeps the measurement RULES — module
resolution, the two member-locality guards, the re-export walk, the unparsed
census — and the two values a measurement is taken OVER and reported IN
(`MemberSources`, `FleetConsumption`). This file holds only what one PRODUCES,
so nothing here imports that module and the dependency runs one way.

Each record keeps the contract argument that shaped it, because each argument
is why a field is SEPARATE rather than fused into its neighbour, and the reader
who reaches for the field reaches for this file.

THE FAILURE RECORD LIVES HERE, beside the success ones, because
`PartialConsumption` is a measurement OUTCOME rather than a measurement rule:
it says the oracle answered over fewer sources than it was handed, and it
carries the graph it did build so a partial answer is still usable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from livespec_dev_tooling.fleet._public_api_unresolved import UnresolvedReach

__all__: list[str] = [
    "ConsumptionEdge",
    "ConsumptionGraph",
    "PartialConsumption",
    "UnparsedSource",
]


@dataclass(frozen=True, kw_only=True)
class ConsumptionEdge:
    """One function defined in one member and reached from another.

    `uniquely_resolved` is False when the import's dotted suffix matched more
    than one defining file across the fleet. The edge is still emitted — doubt
    resolves toward more enforcement — but a consumer of this graph must be
    able to say "and this one is ambiguous" rather than assert it flatly.
    """

    defining_member: str
    defining_file: Path
    function: str
    consuming_member: str
    consuming_file: Path
    uniquely_resolved: bool


@dataclass(frozen=True, kw_only=True)
class UnparsedSource:
    """A source file the graph could not read, and therefore did not measure."""

    member: str
    file: Path
    detail: str


@dataclass(frozen=True, kw_only=True)
class ConsumptionGraph:
    """Every cross-member consumption, plus what could not be measured.

    `unresolved` rides BESIDE `edges` rather than inside them because it is a
    different outcome: an edge says a member's function is consumed across a
    boundary, while an `UnresolvedReach` says a sibling imports a name no file
    it resolved to binds — a broken consumer rather than a declaration gap.
    """

    edges: tuple[ConsumptionEdge, ...]
    unparsed: tuple[UnparsedSource, ...]
    unresolved: tuple[UnresolvedReach, ...]


@dataclass(frozen=True, kw_only=True)
class PartialConsumption:
    """The measurement was taken over FEWER sources than it was handed.

    The failure track of `cross_member_consumption`, inhabited exactly when at
    least one member's source would not parse. `graph.unparsed` names those
    files; `graph.edges` carries every edge the readable files did yield, and
    that is deliberate on both counts. One syntactically invalid file must not
    kill a nine-member sweep, so the partial answer travels rather than being
    discarded — and it must not travel as though it were a whole one, which is
    what a bare `ConsumptionGraph` return made it do.

    The census stays IN the graph rather than being lifted into this record: a
    consumer reports per-member blind spots from `graph.unparsed`, and moving
    that list here would put one list in two places for the sake of a shape.
    What the railway adds is that the consumer can no longer receive a partial
    measurement in the same spelling as a complete one and forget the
    difference — a field can be left unread, a failure track cannot.
    """

    graph: ConsumptionGraph
