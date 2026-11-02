"""Tests for the committed maintainer radar."""

from __future__ import annotations

import dataclasses
import importlib
from datetime import date
from pathlib import Path


def test_radar_exports_seeded_typed_entries() -> None:
    """The committed radar is the ordered, typed maintainer transcription."""
    module_path = Path(__file__).parents[3] / "livespec_dev_tooling" / "radar" / "radar.py"
    assert module_path.is_file()

    radar = importlib.import_module("livespec_dev_tooling.radar.radar")

    assert [field.name for field in dataclasses.fields(radar.RadarEntry)] == [
        "kind",
        "tenant",
        "id",
        "words",
        "said_at",
        "blocked_by",
    ]
    assert isinstance(radar.RADAR, tuple)
    assert len(radar.RADAR) == 14
    assert radar.RADAR[0].id == "livespec-dev-tooling-w7ley3"
    assert all(entry.kind == "plan" for entry in radar.RADAR)
    assert all(entry.said_at == date(2026, 11, 2) for entry in radar.RADAR)


def test_structural_validation_names_duplicate_indexes_and_bad_references() -> None:
    """Offline validation diagnoses the two defects that need no ledger."""
    radar = importlib.import_module("livespec_dev_tooling.radar.radar")

    assert hasattr(radar, "validate_structure")

    entry = radar.RadarEntry(
        kind="item",
        tenant="tenant-a",
        id="item-a",
        words="radar target",
        said_at=date(2026, 11, 2),
        blocked_by=("tenant-b:item-b",),
    )
    duplicate_errors = radar.validate_structure((entry, entry))
    assert duplicate_errors == ("duplicate radar entry tenant-a:item-a at indexes 0 and 1",)

    malformed = radar.RadarEntry(
        kind="item",
        tenant="tenant-c",
        id="item-c",
        words="radar target",
        said_at=date(2026, 11, 2),
        blocked_by=("missing-id:",),
    )
    assert radar.validate_structure((malformed,)) == (
        "radar entry 0 tenant-c:item-c has malformed blocked_by reference 'missing-id:'",
    )
