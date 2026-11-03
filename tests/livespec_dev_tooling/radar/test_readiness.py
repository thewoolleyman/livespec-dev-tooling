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
