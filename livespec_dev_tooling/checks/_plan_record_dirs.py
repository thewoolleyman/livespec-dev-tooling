"""Reading the plan store: the direct plan-record directories and their anchors.

The checkout half of the plan-record inputs, held apart from the verdicts that
grade it (`_plan_record_anchors`). Only DIRECT children of `plan/` and
`plan/archive/` are plan records — a nested directory is research inside one,
not a record of its own — and each is read once, so a verdict never re-reads the
filesystem to answer a question the projection already carries.

`anchor` is the file's ONE legible line or None; `raw` is the bytes as written.
Keeping both is what lets `plan_anchor_present` say whether it met an absent
anchor or an illegible one, which are different repairs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from livespec_dev_tooling.checks._plan_record_model import (
    PLAN_ANCHOR_FILENAME,
    UNASSIGNED_ANCHOR,
)

__all__: list[str] = [
    "ARCHIVE_DIR_NAME",
    "PLAN_DIR_NAME",
    "PlanDirectory",
    "plan_directories",
]

PLAN_DIR_NAME = "plan"
ARCHIVE_DIR_NAME = "archive"


@dataclass(frozen=True, kw_only=True)
class PlanDirectory:
    """One direct plan-record directory and the anchor line it carries.

    `anchor` is None when the file is absent OR when its content is not one
    legible line — the two states `plan_anchor_present` reports — and `raw` is
    the bytes as written, so a finding can say which of the two it met.
    """

    relative: str
    slug: str
    archived: bool
    raw: str | None
    anchor: str | None


def plan_directories(*, plan_dir: Path, tenant_re: re.Pattern[str]) -> list[PlanDirectory]:
    """Return every direct `plan/<slug>/` and `plan/archive/<slug>/` record."""
    if not plan_dir.is_dir():
        return []
    live = sorted(
        path for path in plan_dir.iterdir() if path.is_dir() and path.name != ARCHIVE_DIR_NAME
    )
    archive_dir = plan_dir / ARCHIVE_DIR_NAME
    archived = (
        sorted(path for path in archive_dir.iterdir() if path.is_dir())
        if archive_dir.is_dir()
        else []
    )
    return [
        *(_directory_of(path=path, archived=False, tenant_re=tenant_re) for path in live),
        *(_directory_of(path=path, archived=True, tenant_re=tenant_re) for path in archived),
    ]


def _directory_of(*, path: Path, archived: bool, tenant_re: re.Pattern[str]) -> PlanDirectory:
    anchor_path = path / PLAN_ANCHOR_FILENAME
    relative = (
        f"{PLAN_DIR_NAME}/{ARCHIVE_DIR_NAME}/{path.name}"
        if archived
        else f"{PLAN_DIR_NAME}/{path.name}"
    )
    raw = anchor_path.read_text(encoding="utf-8") if anchor_path.is_file() else None
    return PlanDirectory(
        relative=relative,
        slug=path.name,
        archived=archived,
        raw=raw,
        anchor=_anchor_line(raw=raw, tenant_re=tenant_re),
    )


def _anchor_line(*, raw: str | None, tenant_re: re.Pattern[str]) -> str | None:
    """Return the legible anchor line, or None when absent or malformed."""
    if raw is None:
        return None
    lines = [line for line in raw.splitlines() if line.strip() != ""]
    if len(lines) != 1:
        return None
    value = lines[0].strip()
    if value == UNASSIGNED_ANCHOR or tenant_re.match(value) is not None:
        return value
    return None
