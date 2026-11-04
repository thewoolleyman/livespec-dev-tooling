"""Ledger-backed radar loading."""

from __future__ import annotations

import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.io import IOFailure  # noqa: E402  — vendor-path-aware import after sys.path insert.
from returns.unsafe import (  # noqa: E402  — vendor-path-aware import after sys.path insert.
    unsafe_perform_io,
)

from livespec_dev_tooling.checks._plan_ledger import bd_items_reader  # noqa: E402
from livespec_dev_tooling.radar.radar import RADAR, RadarEntry, validate_structure  # noqa: E402

__all__: list[str] = [
    "TENANT_REPOSITORIES",
    "LoadedRadar",
    "RadarLoadError",
    "bd_ledger_reader",
    "load_radar",
]

TENANT_REPOSITORIES: Mapping[str, Path] = {
    "livespec-dev-tooling": Path("/data/projects/livespec-dev-tooling"),
    "livespec-orch-beads-fabro": Path("/data/projects/livespec-orchestrator-beads-fabro"),
    "livespec-overseer": Path("/data/projects/livespec-overseer"),
    "livespec": Path("/data/projects/livespec"),
    "hetzner-xubuntu-info": Path("/data/projects/hetzner-xubuntu-info"),
}


class LedgerReader(Protocol):
    """Read the complete ledger population for one radar tenant."""

    def __call__(self, *, tenant: str, repository: Path) -> Mapping[str, Mapping[str, object]]:
        """Return records keyed by id."""
        ...


@dataclass(frozen=True, kw_only=True, slots=True)
class LoadedRadar:
    """A validated radar and its non-refusing informational findings."""

    entries: tuple[RadarEntry, ...]
    findings: tuple[str, ...]


class RadarLoadError(Exception):
    """A radar whose ledger-backed validation found one or more defects."""

    entries: tuple[RadarEntry, ...] = ()

    def __init__(self, *, defects: tuple[str, ...]) -> None:
        super().__init__("\n".join(defects))
        self.defects = defects


def bd_ledger_reader(*, tenant: str, repository: Path) -> Mapping[str, Mapping[str, object]]:
    """Read every ledger record, including closed ones, for one tenant."""
    _ = tenant
    read = bd_items_reader(repo=repository)
    if isinstance(read, IOFailure):
        raise TypeError(unsafe_perform_io(read.failure()).detail)
    records = unsafe_perform_io(read.unwrap())
    return {
        identifier: record for record in records if isinstance(identifier := record.get("id"), str)
    }


def load_radar(
    *,
    entries: tuple[RadarEntry, ...] = RADAR,
    reader: LedgerReader = bd_ledger_reader,
    repositories: Mapping[str, Path] = TENANT_REPOSITORIES,
) -> LoadedRadar:
    """Load entries after validating them against their tenant ledgers."""
    targets = {entry.tenant for entry in entries} | {
        reference.split(":", maxsplit=1)[0] for entry in entries for reference in entry.blocked_by
    }
    records = {tenant: reader(tenant=tenant, repository=repositories[tenant]) for tenant in targets}
    defects = [*validate_structure(entries)]
    defects.extend(_unresolved_defects(entries=entries, records=records))
    defects.extend(_covered_item_defects(entries=entries, records=records))
    defects.extend(
        _plan_directory_defects(entries=entries, records=records, repositories=repositories)
    )
    if defects:
        raise RadarLoadError(defects=tuple(defects))
    findings = tuple(
        f"radar entry {entry.tenant}:{entry.id} is done"
        for entry in entries
        if _closed(record=records[entry.tenant][entry.id])
    )
    return LoadedRadar(entries=entries, findings=findings)


def _unresolved_defects(
    *, entries: tuple[RadarEntry, ...], records: Mapping[str, Mapping[str, Mapping[str, object]]]
) -> list[str]:
    """Report missing entry and cross-tenant blocker targets."""
    defects = [
        f"radar entry {entry.tenant}:{entry.id} does not resolve"
        for entry in entries
        if entry.id not in records[entry.tenant]
    ]
    for entry in entries:
        for reference in entry.blocked_by:
            tenant, identifier = reference.split(":", maxsplit=1)
            if identifier not in records[tenant]:
                defects.append(f"blocked_by reference {reference} does not resolve")
    return defects


def _covered_item_defects(
    *, entries: tuple[RadarEntry, ...], records: Mapping[str, Mapping[str, Mapping[str, object]]]
) -> list[str]:
    """Report direct item entries already covered by a listed plan."""
    plans = tuple(entry for entry in entries if entry.kind == "plan")
    return [
        f"radar item {entry.tenant}:{entry.id} is a child of listed plan {plan.id}"
        for entry in entries
        if entry.kind == "item"
        for plan in plans
        if entry.tenant == plan.tenant
        and _is_child(
            item_id=entry.id,
            plan_id=plan.id,
            record=records[entry.tenant].get(entry.id, {}),
        )
    ]


def _plan_directory_defects(
    *,
    entries: tuple[RadarEntry, ...],
    records: Mapping[str, Mapping[str, Mapping[str, object]]],
    repositories: Mapping[str, Path],
) -> list[str]:
    """Report plan epics lacking their declared on-disk plan directory."""
    defects: list[str] = []
    for entry in entries:
        if entry.kind != "plan" or entry.id not in records[entry.tenant]:
            continue
        metadata = records[entry.tenant][entry.id].get("metadata")
        metadata_map: Mapping[str, object] = (
            cast("Mapping[str, object]", metadata)
            if isinstance(metadata, Mapping)
            else cast("Mapping[str, object]", {})
        )
        slug = metadata_map.get("plan_slug")
        if not isinstance(slug, str) or not (repositories[entry.tenant] / "plan" / slug).is_dir():
            defects.append(f"plan entry {entry.tenant}:{entry.id} has no plan directory")
    return defects


def _is_child(*, item_id: str, plan_id: str, record: Mapping[str, object]) -> bool:
    """Return whether a dotted id or explicit parent-child edge names the plan."""
    if item_id.startswith(f"{plan_id}."):
        return True
    dependencies = record.get("dependencies", ())
    raw_rows = cast("list[object]", dependencies) if isinstance(dependencies, list) else []
    rows = tuple(
        cast("Mapping[str, object]", dependency)
        for dependency in raw_rows
        if isinstance(dependency, Mapping)
    )
    return any(
        dependency.get("type", dependency.get("dependency_type")) == "parent-child"
        and dependency.get("depends_on_id", dependency.get("id")) == plan_id
        for dependency in rows
    )


def _closed(*, record: Mapping[str, object]) -> bool:
    """Return whether a ledger record is closed."""
    return record.get("status") == "closed"
