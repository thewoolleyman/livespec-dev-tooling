"""Green-leg coverage for radar structure validation."""

from __future__ import annotations

import importlib
from datetime import date

import pytest


def test_structural_validation_reports_every_malformed_reference_shape() -> None:
    """References require one colon and two non-empty components."""
    radar = importlib.import_module("livespec_dev_tooling.radar.radar")
    entry = radar.RadarEntry(
        kind="item",
        tenant="tenant-c",
        id="item-c",
        words="radar target",
        said_at=date(2026, 11, 2),
        blocked_by=("tenant-b:item-b", "missing-id:", ":missing-tenant", "too:many:parts"),
    )

    assert radar.validate_structure((entry,)) == (
        "radar entry 0 tenant-c:item-c has malformed blocked_by reference 'missing-id:'",
        "radar entry 0 tenant-c:item-c has malformed blocked_by reference ':missing-tenant'",
        "radar entry 0 tenant-c:item-c has malformed blocked_by reference 'too:many:parts'",
    )


def test_invalid_committed_radar_is_rejected_at_import() -> None:
    """The import-time guard rejects duplicate targets in committed data."""
    radar = importlib.import_module("livespec_dev_tooling.radar.radar")
    entry = radar.RadarEntry(
        kind="plan",
        tenant="livespec-dev-tooling",
        id="livespec-dev-tooling-w7ley3",
        words="duplicate target",
        said_at=date(2026, 11, 2),
    )

    with pytest.raises(ValueError, match=r"duplicate radar entry livespec-dev-tooling:"):
        radar.validate_structure.ensure(entries=(entry, entry))
