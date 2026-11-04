"""Ledger fixture coverage for radar loading."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import date
from pathlib import Path
from typing import Literal

import pytest
from returns.io import IOFailure, IOSuccess

from livespec_dev_tooling.checks._plan_ledger import LedgerReadFailed
from livespec_dev_tooling.radar import loader
from livespec_dev_tooling.radar.loader import RadarLoadError, bd_ledger_reader, load_radar
from livespec_dev_tooling.radar.radar import RadarEntry


def _entry(
    *,
    kind: Literal["item", "plan"] = "item",
    identifier: str = "item-a",
    blocked_by: tuple[str, ...] = (),
) -> RadarEntry:
    """Build an entry for a tenant-local ledger fixture."""
    return RadarEntry(
        kind=kind,
        tenant="tenant-a",
        id=identifier,
        words="target",
        said_at=date(2026, 11, 4),
        blocked_by=blocked_by,
    )


def _reader(
    *, records: dict[str, dict[str, object]]
) -> Callable[..., Mapping[str, Mapping[str, object]]]:
    def read(*, tenant: str, repository: Path) -> dict[str, dict[str, object]]:
        _ = tenant, repository
        return records

    return read


def test_load_reports_done_without_refusing_a_closed_entry(tmp_path: Path) -> None:
    """Closed radar entries are findings, not consumer-facing defects."""
    entry = _entry(kind="plan", identifier="plan-a", blocked_by=("tenant-a:cleared",))
    (tmp_path / "plan" / "alpha").mkdir(parents=True)
    loaded = load_radar(
        entries=(entry,),
        reader=_reader(
            records={
                "plan-a": {"status": "closed", "metadata": {"plan_slug": "alpha"}},
                "cleared": {"status": "closed"},
            }
        ),
        repositories={"tenant-a": tmp_path},
    )
    assert loaded.entries == (entry,)
    assert loaded.findings == ("radar entry tenant-a:plan-a is done",)


def test_load_reports_child_plan_directory_and_blocker_defects(tmp_path: Path) -> None:
    """Every ledger-backed defect is accumulated before refusal."""
    plan = _entry(kind="plan", identifier="plan-a")
    child = _entry(identifier="plan-a.1", blocked_by=("tenant-b:missing",))
    with pytest.raises(RadarLoadError) as raised:
        _ = load_radar(
            entries=(plan, child),
            reader=_reader(
                records={
                    "plan-a": {"status": "ready", "metadata": {"plan_slug": "alpha"}},
                    "plan-a.1": {"status": "ready"},
                }
            ),
            repositories={"tenant-a": tmp_path, "tenant-b": tmp_path},
        )
    assert raised.value.entries == ()
    assert raised.value.defects == (
        "blocked_by reference tenant-b:missing does not resolve",
        "radar item tenant-a:plan-a.1 is a child of listed plan plan-a",
        "plan entry tenant-a:plan-a has no plan directory",
    )


def test_load_detects_a_parent_child_edge_without_a_dotted_identifier(tmp_path: Path) -> None:
    """A plan covers children recorded only by their explicit ledger edge."""
    plan = _entry(kind="plan", identifier="plan-a")
    child = _entry(identifier="separately-named")
    (tmp_path / "plan" / "alpha").mkdir(parents=True)

    with pytest.raises(RadarLoadError) as raised:
        _ = load_radar(
            entries=(plan, child),
            reader=_reader(
                records={
                    "plan-a": {"status": "ready", "metadata": {"plan_slug": "alpha"}},
                    "separately-named": {
                        "status": "ready",
                        "dependencies": [{"id": "plan-a", "dependency_type": "parent-child"}],
                    },
                }
            ),
            repositories={"tenant-a": tmp_path},
        )

    assert raised.value.defects == (
        "radar item tenant-a:separately-named is a child of listed plan plan-a",
    )


def test_bd_ledger_reader_projects_records_and_raises_read_failures(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The concrete seam includes closed records and never masks a failed read."""

    def successful_reader(*, repo: Path) -> IOSuccess[list[dict[str, object]]]:
        _ = repo
        return IOSuccess([{"id": "open"}, {"id": "closed"}, {"title": "no-id"}])

    monkeypatch.setattr(loader, "bd_items_reader", successful_reader)

    assert bd_ledger_reader(tenant="tenant-a", repository=tmp_path) == {
        "open": {"id": "open"},
        "closed": {"id": "closed"},
    }

    def failing_reader(*, repo: Path) -> IOFailure[LedgerReadFailed]:
        _ = repo
        return IOFailure(LedgerReadFailed(reason="bd-failed", detail="no credential"))

    monkeypatch.setattr(loader, "bd_items_reader", failing_reader)

    with pytest.raises(TypeError, match="no credential"):
        _ = bd_ledger_reader(tenant="tenant-a", repository=tmp_path)
