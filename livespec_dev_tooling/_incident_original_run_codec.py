"""Decode original-run evidence the independent controller retained."""

from __future__ import annotations

from typing import Any, cast

from livespec_dev_tooling._incident_run_types import (
    EvidenceDebt,
    ExpectedJob,
    JobEvidence,
    ObservedJob,
    OriginalRun,
    RunEvidence,
    RunSnapshot,
)

__all__: list[str] = ["decode_evidence"]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-zvntys


def _rows(*, value: object) -> list[dict[str, Any]]:
    return cast("list[dict[str, Any]]", value)


def decode_evidence(*, value: object) -> RunEvidence:
    """Rebuild evidence the controller retained as `asdict` JSON; malformed raises."""
    data = cast("dict[str, Any]", value)
    original = dict(cast("dict[str, Any]", data["original"]))
    original["expected"] = tuple(
        ExpectedJob(name=row["name"], needs=tuple(row["needs"]))
        for row in _rows(value=original["expected"])
    )
    snapshot = dict(cast("dict[str, Any]", data["source_snapshot"]))
    snapshot["jobs"] = tuple(ObservedJob(**row) for row in _rows(value=snapshot["jobs"]))
    return RunEvidence(
        original=OriginalRun(**original),
        source_snapshot=RunSnapshot(**snapshot),
        terminal=data["terminal"],
        jobs=tuple(JobEvidence(**row) for row in _rows(value=data["jobs"])),
        debts=tuple(EvidenceDebt(**row) for row in _rows(value=data["debts"])),
    )
