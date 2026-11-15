"""Tests for the ledger-backed radar loader."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from livespec_dev_tooling.radar.loader import RadarLoadError, load_radar
from livespec_dev_tooling.radar.radar import RadarEntry


def test_load_refuses_every_unresolved_entry_and_returns_no_entries() -> None:
    """A reachable ledger missing radar ids refuses the complete radar."""

    def reader(*, tenant: str, repository: Path) -> dict[str, dict[str, object]]:
        _ = tenant, repository
        return {}

    entry = RadarEntry(
        kind="item",
        tenant="tenant-a",
        id="missing-a",
        words="radar target",
        said_at=date(2026, 11, 4),
        blocked_by=(),
    )

    with pytest.raises(RadarLoadError) as raised:
        _ = load_radar(entries=(entry,), reader=reader, repositories={"tenant-a": Path()})

    assert raised.value.entries == ()
    assert raised.value.defects == ("radar entry tenant-a:missing-a does not resolve",)
