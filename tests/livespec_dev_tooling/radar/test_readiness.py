"""Tests for the pure radar readiness reader."""

from __future__ import annotations

import importlib
from datetime import date


def test_closed_target_is_done_and_needs_no_work() -> None:
    """A closed radar target is done, not ready or blocked."""
    radar = importlib.import_module("livespec_dev_tooling.radar.radar")
    reader = importlib.import_module("livespec_dev_tooling.radar.readiness")
    entry = radar.RadarEntry(
        kind="item",
        tenant="tenant-a",
        id="target",
        words="target",
        said_at=date(2026, 11, 3),
        blocked_by=(),
    )

    result = reader.readiness(
        entry=entry,
        records={("tenant-a", "target"): {"status": "closed"}},
    )

    assert result.state == "DONE"
    assert result.blockers == ()


def test_open_target_names_only_open_blocks_edges_and_declared_blockers() -> None:
    """Only open `blocks` edges and declared references make a target not ready."""
    radar = importlib.import_module("livespec_dev_tooling.radar.radar")
    reader = importlib.import_module("livespec_dev_tooling.radar.readiness")
    entry = radar.RadarEntry(
        kind="item",
        tenant="tenant-a",
        id="target",
        words="target",
        said_at=date(2026, 11, 3),
        blocked_by=("tenant-b:declared-open", "tenant-b:declared-closed"),
    )
    records = {
        ("tenant-a", "target"): {
            "status": "active",
            "dependencies": [
                {"depends_on_id": "list-open", "type": "blocks"},
                {"id": "show-open", "dependency_type": "blocks"},
                {"depends_on_id": "list-closed", "type": "blocks"},
                {"depends_on_id": "child", "type": "parent-child"},
                {"id": "related", "dependency_type": "relates-to"},
                {"depends_on_id": "discovered", "type": "discovered-from"},
                {"id": "nearby", "dependency_type": "related"},
                {"depends_on_id": "duplicate", "type": "duplicates"},
            ],
        },
        ("tenant-a", "list-open"): {"status": "active"},
        ("tenant-a", "show-open"): {"status": "ready"},
        ("tenant-a", "list-closed"): {"status": "closed"},
        ("tenant-a", "child"): {"status": "active"},
        ("tenant-a", "related"): {"status": "active"},
        ("tenant-a", "discovered"): {"status": "active"},
        ("tenant-a", "nearby"): {"status": "active"},
        ("tenant-a", "duplicate"): {"status": "active"},
        ("tenant-b", "declared-open"): {"status": "active"},
        ("tenant-b", "declared-closed"): {"status": "closed"},
    }

    result = reader.readiness(entry=entry, records=records)

    assert result.state == "NOT READY"
    assert result.blockers == (
        "tenant-a:list-open",
        "tenant-a:show-open",
        "tenant-b:declared-open",
    )


def test_absent_dependencies_means_an_open_target_is_ready() -> None:
    """The ledger's omitted zero-value dependency field has no edges."""
    radar = importlib.import_module("livespec_dev_tooling.radar.radar")
    reader = importlib.import_module("livespec_dev_tooling.radar.readiness")
    entry = radar.RadarEntry(
        kind="item",
        tenant="tenant-a",
        id="target",
        words="target",
        said_at=date(2026, 11, 3),
        blocked_by=(),
    )

    result = reader.readiness(
        entry=entry,
        records={("tenant-a", "target"): {"status": "active"}},
    )

    assert result.state == "READY"
    assert result.blockers == ()


def test_plan_children_unites_dotted_descendants_and_parent_child_edges() -> None:
    """Neither Beads plan-child representation is complete on its own."""
    radar = importlib.import_module("livespec_dev_tooling.radar.radar")
    reader = importlib.import_module("livespec_dev_tooling.radar.readiness")
    entry = radar.RadarEntry(
        kind="plan",
        tenant="tenant-a",
        id="epic",
        words="plan",
        said_at=date(2026, 11, 3),
        blocked_by=(),
    )
    records = {
        ("tenant-a", "epic.dotted"): {"status": "active"},
        ("tenant-a", "list-child"): {
            "dependencies": [{"depends_on_id": "epic", "type": "parent-child"}],
        },
        ("tenant-a", "show-child"): {
            "dependencies": [{"id": "epic", "dependency_type": "parent-child"}],
        },
        ("tenant-a", "unrelated"): {"status": "active"},
    }

    assert reader.plan_children(entry=entry, records=records) == (
        "tenant-a:epic.dotted",
        "tenant-a:list-child",
        "tenant-a:show-child",
    )
