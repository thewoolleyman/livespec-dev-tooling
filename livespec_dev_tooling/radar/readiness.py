"""Pure readiness projection for maintainer radar entries."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Literal, cast

from livespec_dev_tooling.radar.radar import RadarEntry

__all__: list[str] = ["RadarReadiness", "plan_children", "readiness"]

Target = tuple[str, str]
Record = Mapping[str, object]


@dataclass(frozen=True, kw_only=True, slots=True)
class RadarReadiness:
    """The current state and unresolved blockers for one radar target."""

    state: Literal["DONE", "READY", "NOT READY"]
    blockers: tuple[str, ...]


def readiness(*, entry: RadarEntry, records: Mapping[Target, Record]) -> RadarReadiness:
    """Project one radar entry's readiness from already-read ledger records."""
    record = records.get((entry.tenant, entry.id), {})
    if _is_closed(record=record):
        return RadarReadiness(state="DONE", blockers=())
    blockers = tuple(
        dict.fromkeys(
            (
                *_open_edge_blockers(entry=entry, record=record, records=records),
                *_open_declared_blockers(entry=entry, records=records),
            )
        )
    )
    state: Literal["READY", "NOT READY"] = "NOT READY" if blockers else "READY"
    return RadarReadiness(state=state, blockers=blockers)


def plan_children(*, entry: RadarEntry, records: Mapping[Target, Record]) -> tuple[str, ...]:
    """Return a plan's dotted-id and explicit parent-child descendants."""
    dotted_prefix = f"{entry.id}."
    children = {
        target
        for target, record in records.items()
        if target[0] == entry.tenant
        and (
            target[1].startswith(dotted_prefix)
            or _has_edge(record=record, edge="parent-child", target=entry.id)
        )
    }
    return tuple(f"{tenant}:{identifier}" for tenant, identifier in sorted(children))


def _open_edge_blockers(
    *, entry: RadarEntry, record: Record, records: Mapping[Target, Record]
) -> Iterable[str]:
    """Yield open same-tenant targets connected by ledger `blocks` edges."""
    for dependency in _dependencies(record=record):
        identifier = _edge_target(dependency=dependency, edge="blocks")
        if identifier is not None and not _is_closed(
            record=records.get((entry.tenant, identifier), {})
        ):
            yield f"{entry.tenant}:{identifier}"


def _open_declared_blockers(
    *, entry: RadarEntry, records: Mapping[Target, Record]
) -> Iterable[str]:
    """Yield open cross-tenant blocker references declared by the radar entry."""
    for reference in entry.blocked_by:
        tenant, identifier = reference.split(":", maxsplit=1)
        if not _is_closed(record=records.get((tenant, identifier), {})):
            yield reference


def _has_edge(*, record: Record, edge: str, target: str) -> bool:
    """Return whether a record has a dependency of one kind to one target."""
    return any(
        _edge_target(dependency=dependency, edge=edge) == target
        for dependency in _dependencies(record=record)
    )


def _dependencies(*, record: Record) -> list[Record]:
    """Return dependency rows, treating an omitted field as no edges."""
    dependencies = record.get("dependencies", ())
    return cast("list[Record]", dependencies) if isinstance(dependencies, list) else []


def _edge_target(*, dependency: Record, edge: str) -> str | None:
    """Read a target from either dependency-row spelling when its edge matches."""
    relation = dependency.get("type", dependency.get("dependency_type"))
    identifier = dependency.get("depends_on_id", dependency.get("id"))
    return identifier if relation == edge and isinstance(identifier, str) else None


def _is_closed(*, record: Record) -> bool:
    """Return whether the ledger record is in its terminal closed state."""
    return record.get("status") == "closed"
