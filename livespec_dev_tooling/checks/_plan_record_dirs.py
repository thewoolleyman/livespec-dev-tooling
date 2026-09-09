"""Reading the plan store: the direct plan-record directories and their anchors.

The checkout half of the plan-record inputs, held apart from the verdicts that
grade it (`_plan_record_anchors`). Only DIRECT children of `plan/` and
`plan/archive/` are plan records — a nested directory is research inside one,
not a record of its own — and each is read once, so a verdict never re-reads the
filesystem to answer a question the projection already carries.

`anchor` is the file's ONE legible line or None; `raw` is the bytes as written.
Keeping both is what lets `plan_anchor_present` say whether it met an absent
anchor or an illegible one, which are different repairs.

THE SCAN IS ON THE `IOResult` RAILWAY — `livespec-dev-tooling-qndn.4`. It walks
the filesystem directly rather than through an injected seam, so it IS the I/O
boundary and `IOResult` rather than `Result` is the honest container. A repo
that keeps NO `plan/` tree and a `plan/` tree this process could not walk were
the same empty list before, and `plan_anchor_present` grades what it is handed
— so a checkout the scan could not read reported as a conforming repo holding
no plan records at all.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

# Carried rather than inherited from an importer: without it the vendored
# `returns` resolves only because some module up the import chain happens to
# carry the preamble, which is a property of the caller rather than of this file.
_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.io import IOFailure, IOResult, IOSuccess  # noqa: E402  — vendor-path-aware import.

from livespec_dev_tooling.checks._plan_record_model import (  # noqa: E402
    PLAN_ANCHOR_FILENAME,
    UNASSIGNED_ANCHOR,
)

__all__: list[str] = [
    "ARCHIVE_DIR_NAME",
    "PLAN_DIR_NAME",
    "PlanDirectory",
    "PlanTreeUnreadable",
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


@dataclass(frozen=True, kw_only=True)
class PlanTreeUnreadable:
    """The `plan/` tree EXISTS and this process could not walk it.

    `reason` is the discriminator a caller branches on and `detail` is the
    operator-facing evidence, matching `_plan_ledger.LedgerReadFailed` field
    for field so a caller reporting an unread input renders both the same way.

    An ABSENT tree is deliberately not a member: it is an ANSWER (this repo
    keeps no plan records) rather than a read that did not happen.
    """

    reason: Literal["plan-tree-unreadable"]
    detail: str


def plan_directories(
    *, plan_dir: Path, tenant_re: re.Pattern[str]
) -> IOResult[list[PlanDirectory], PlanTreeUnreadable]:
    """Return every direct `plan/<slug>/` and `plan/archive/<slug>/` record.

    `IOSuccess([])` means the walk HAPPENED and the checkout keeps no plan
    records — including the case where there is no `plan/` tree at all, which
    is an answer this repo's layout legitimately gives. `IOFailure` means the
    record set is UNKNOWN.

    The catch is NARROW and ENUMERATED (`OSError`), the sanctioned hand-rolled
    seam lift, and it spans the anchor reads as well as the two directory
    enumerations: a tree half-walked is not a smaller record set, it is an
    unknown one. A bug raised in here still propagates.
    """
    if not plan_dir.is_dir():
        return IOSuccess([])
    try:
        live = sorted(
            path for path in plan_dir.iterdir() if path.is_dir() and path.name != ARCHIVE_DIR_NAME
        )
        archive_dir = plan_dir / ARCHIVE_DIR_NAME
        archived = (
            sorted(path for path in archive_dir.iterdir() if path.is_dir())
            if archive_dir.is_dir()
            else []
        )
        found = [
            *(_directory_of(path=path, archived=False, tenant_re=tenant_re) for path in live),
            *(_directory_of(path=path, archived=True, tenant_re=tenant_re) for path in archived),
        ]
        return IOSuccess(found)
    except OSError as unreadable:
        return IOFailure(PlanTreeUnreadable(reason="plan-tree-unreadable", detail=str(unreadable)))


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
