"""Report released adopter inventories that differ from current default branches.

Each comparison renders the adopter's normal workflow and check-target inventory
through the same renderer used to create the released entry.  The shell sweep
owns the remote reads; this module owns the deterministic comparison and its
release-blocking report.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from livespec_dev_tooling.incident_ci_inventory import (
    InventorySource,
    decode_inventory,
    render_inventory,
)
from livespec_dev_tooling.incident_strict_json import strict_json

__all__: list[str] = [
    "InventoryCurrent",
    "InventoryDifference",
    "RepositorySnapshot",
    "audit_entries",
    "compare_entry",
    "main",
    "render_report",
]


@dataclass(frozen=True, kw_only=True)
class RepositorySnapshot:
    """The two renderer inputs at one adopter default-branch head."""

    repository: str
    head: str
    workflow: str
    inventory: str


@dataclass(frozen=True, kw_only=True)
class InventoryCurrent:
    """One released entry whose current-default render remains byte-identical."""

    repository: str
    recorded_source: str
    current_head: str


@dataclass(frozen=True, kw_only=True)
class InventoryDifference:
    """One released entry whose current-default render has changed."""

    repository: str
    recorded_source: str
    current_head: str
    added: tuple[str, ...]
    removed: tuple[str, ...]
    reclassified: tuple[str, ...]


InventoryReading = InventoryCurrent | InventoryDifference


def _source(*, text: str) -> InventorySource:
    """Read the validated source that every adopter entry is required to carry."""
    _ = decode_inventory(text=text)
    document = cast("dict[str, Any]", strict_json(text=text, limit=None))
    source = cast("dict[str, str]", document["source"])
    return InventorySource(repository=source["repository"], commit=source["commit"])


def compare_entry(*, path: Path, snapshot: RepositorySnapshot) -> InventoryDifference | None:
    """Compare one committed entry with a render at its current default head."""
    committed = path.read_text(encoding="utf-8")
    source = _source(text=committed)
    if source.repository != snapshot.repository:
        message = f"{path} records {source.repository}, not {snapshot.repository}"
        raise ValueError(message)
    fresh = render_inventory(
        workflow=snapshot.workflow,
        inventory=snapshot.inventory,
        source=InventorySource(repository=source.repository, commit=source.commit),
    )
    if fresh == committed:
        return None
    previous = {target.name: target.classification for target in decode_inventory(text=committed)}
    current = {target.name: target.classification for target in decode_inventory(text=fresh)}
    return InventoryDifference(
        repository=snapshot.repository,
        recorded_source=source.commit,
        current_head=snapshot.head,
        added=tuple(sorted(current.keys() - previous.keys())),
        removed=tuple(sorted(previous.keys() - current.keys())),
        reclassified=tuple(
            f"{name}: {previous[name]} -> {current[name]}"
            for name in sorted(previous.keys() & current.keys())
            if previous[name] != current[name]
        ),
    )


def audit_entries(
    *, directory: Path, read_snapshot: Callable[[str], RepositorySnapshot]
) -> tuple[InventoryReading, ...]:
    """Read every committed adopter entry, with no separately maintained repository list."""
    readings: list[InventoryReading] = []
    for path in sorted(directory.rglob("*.json")):
        repository = path.relative_to(directory).with_suffix("").as_posix()
        snapshot = read_snapshot(repository)
        difference = compare_entry(path=path, snapshot=snapshot)
        if difference is None:
            source = _source(text=path.read_text(encoding="utf-8"))
            readings.append(
                InventoryCurrent(
                    repository=repository,
                    recorded_source=source.commit,
                    current_head=snapshot.head,
                )
            )
        else:
            readings.append(difference)
    return tuple(readings)


def render_report(*, readings: Sequence[InventoryReading]) -> tuple[str, ...]:
    """Render clean and stale inventory readings for a release or scheduled job log."""
    lines: list[str] = []
    for reading in readings:
        prefix = "stale" if isinstance(reading, InventoryDifference) else "current"
        line = f"{prefix}\t{reading.repository}\trecorded_source={reading.recorded_source}"
        lines.append(line + f"\tcurrent_head={reading.current_head}")
        if isinstance(reading, InventoryDifference):
            lines.extend(f"added\t{reading.repository}\t{name}" for name in reading.added)
            lines.extend(f"removed\t{reading.repository}\t{name}" for name in reading.removed)
            lines.extend(
                f"reclassified\t{reading.repository}\t{change}" for change in reading.reclassified
            )
    return tuple(lines)


def main(*, argv: Sequence[str]) -> int:
    """Report one entry passed by the all-entry remote-reading shell sweep."""
    parser = argparse.ArgumentParser(prog="incident-ci-inventory-freshness")
    _ = parser.add_argument("entry", type=Path)
    _ = parser.add_argument("repository")
    _ = parser.add_argument("head")
    _ = parser.add_argument("workflow", type=Path)
    _ = parser.add_argument("inventory", type=Path)
    args = parser.parse_args(list(argv))
    snapshot = RepositorySnapshot(
        repository=str(args.repository),
        head=str(args.head),
        workflow=args.workflow.read_text(encoding="utf-8"),
        inventory=args.inventory.read_text(encoding="utf-8"),
    )
    difference = compare_entry(path=args.entry, snapshot=snapshot)
    if difference is None:
        source = _source(text=args.entry.read_text(encoding="utf-8"))
        readings: tuple[InventoryReading, ...] = (
            InventoryCurrent(
                repository=snapshot.repository,
                recorded_source=source.commit,
                current_head=snapshot.head,
            ),
        )
    else:
        readings = (difference,)
    _ = sys.stdout.write("\n".join(render_report(readings=readings)) + "\n")
    return int(difference is not None)


if __name__ == "__main__":
    raise SystemExit(main(argv=sys.argv[1:]))
