"""Tests for the ledger-backed radar validation command."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import date
from pathlib import Path
from typing import Literal, cast

import pytest

from livespec_dev_tooling.radar import loader
from livespec_dev_tooling.radar.radar import RadarEntry


def _entry(
    *, kind: Literal["item", "plan"], identifier: str, blocked_by: tuple[str, ...] = ()
) -> RadarEntry:
    """Build a radar entry with fixture-stable descriptive fields."""
    return RadarEntry(
        kind=kind,
        tenant="tenant-a",
        id=identifier,
        words="target",
        said_at=date(2026, 11, 4),
        blocked_by=blocked_by,
    )


def test_validate_radar_accumulates_ledger_defects_and_closed_entries(tmp_path: Path) -> None:
    """Edit-time validation names every defect, including closed radar entries."""
    plan = _entry(kind="plan", identifier="plan-a")
    child = _entry(kind="item", identifier="plan-a.1", blocked_by=("tenant-b:missing",))

    def reader(*, tenant: str, repository: Path) -> Mapping[str, Mapping[str, object]]:
        _ = tenant, repository
        return {
            "plan-a": {"status": "closed", "metadata": {"plan_slug": "alpha"}},
            "plan-a.1": {"status": "ready"},
        }

    assert hasattr(loader, "validate_radar")
    validate = cast("Callable[..., tuple[str, ...]]", loader.validate_radar)
    assert validate(
        entries=(plan, child),
        reader=reader,
        repositories={"tenant-a": tmp_path, "tenant-b": tmp_path},
    ) == (
        "blocked_by reference tenant-b:missing does not resolve",
        "radar item tenant-a:plan-a.1 is a child of listed plan plan-a",
        "plan entry tenant-a:plan-a has no plan directory",
        "radar entry tenant-a:plan-a is closed",
    )


def test_main_reports_each_validation_defect(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The command exits nonzero and names each reported validation defect."""
    monkeypatch.setattr(
        loader,
        "validate_radar",
        lambda: ("first defect", "second defect"),
    )

    assert loader.main() == 1
    assert [record.message for record in caplog.records] == ["first defect", "second defect"]


def test_validate_radar_keeps_structurally_malformed_blockers_as_defects(tmp_path: Path) -> None:
    """A malformed blocker is reported instead of reaching the ledger lookup."""
    entry = _entry(kind="item", identifier="item-a", blocked_by=("malformed",))

    def reader(*, tenant: str, repository: Path) -> Mapping[str, Mapping[str, object]]:
        _ = tenant, repository
        return {"item-a": {"status": "ready"}}

    assert loader.validate_radar(
        entries=(entry,), reader=reader, repositories={"tenant-a": tmp_path}
    ) == ("radar entry 0 tenant-a:item-a has malformed blocked_by reference 'malformed'",)
