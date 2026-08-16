"""plan_epic_parity — plan archive state must match ledger epic state.

Disposition: RE-SCOPED against ratified Planning Lane v197 and the v059
orchestrator realization.

The old check read git `handoff.md` / `epic.md` anchor documents. Those carriers
are retired: a plan is now anchored by ledger epic metadata (`plan_slug`), and
handoff entries are ledger comments. The surviving invariant is the lifecycle
binding: a direct `plan/<slug>/` directory is active iff its same-tenant plan
epic is open, and a direct `plan/archive/<slug>/` directory is archived iff its
same-tenant plan epic is done/closed. The archived-regroom converse also
survives: a procedural anchor closure with incomplete same-tenant replacement
descendants is not completion evidence.

ARMED-ONLY: self-skips unless `LIVESPEC_RUN_PLAN_EPIC_PARITY` is truthy and
`BEADS_DOLT_PASSWORD` is present, because it reads ledger state.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Protocol, cast

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import jsoncomment  # noqa: E402  — vendor-path-aware import after sys.path insert.
import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

from livespec_dev_tooling.checks._plan_ledger import (  # noqa: E402
    ItemReader,
    bd_items_reader,
    descendant_offenders,
    parse_status,
    record_id,
)

__all__: list[str] = []


_PLAN_DIR_NAME = "plan"
_ARCHIVE_DIR_NAME = "archive"
_LIVESPEC_CONFIG = ".livespec.jsonc"
_RUN_LEVER = "LIVESPEC_RUN_PLAN_EPIC_PARITY"
_CRED_ENV = "BEADS_DOLT_PASSWORD"
_CLOSED_STATUSES = frozenset({"closed", "done"})
_ACTIVE_REMEDIATION = (
    "reopen the plan epic or archive the plan record whole; ratified Planning "
    "Lane binds `plan/<slug>/` active state to an open ledger epic."
)
_ARCHIVED_REMEDIATION = (
    "move the plan record back to `plan/<slug>/` or close its epic through the "
    "archive gates; archived records must point at done/closed plan epics."
)
_MISSING_REMEDIATION = (
    "ensure exactly one same-tenant ledger epic carries metadata `plan_slug=<slug>`; "
    "the plan anchor is ledger-held and is not a git handoff or epic document."
)
_DESCENDANT_REMEDIATION = (
    "restore the plan to `plan/<slug>/` until every replacement descendant that "
    "depends on its anchor epic is closed with a completion-shaped resolution."
)


class StatusReader(Protocol):
    """Legacy status reader protocol retained for import compatibility."""

    def __call__(self, *, epic_id: str, repo: Path) -> str | None:
        """Return a ledger status for `epic_id`."""
        ...


def _is_armed() -> bool:
    """True iff the RUN lever is truthy AND the beads credential is present."""
    return bool(os.environ.get(_RUN_LEVER)) and bool(os.environ.get(_CRED_ENV))


def _bd_status_reader(*, epic_id: str, repo: Path) -> str | None:
    """Read a ledger epic's status via `bd -C <repo> show <id> --json`."""
    completed = subprocess.run(
        ("bd", "-C", str(repo), "show", epic_id, "--json"),
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        return None
    return parse_status(text=completed.stdout)


def _store_prefix(*, cwd: Path) -> str:
    """Return the repo store prefix from `.livespec.jsonc`'s connection block."""
    parsed = cast(
        "dict[str, object]",
        jsoncomment.loads((cwd / _LIVESPEC_CONFIG).read_text(encoding="utf-8")),
    )
    implementation = cast("dict[str, object]", parsed["implementation"])
    plugin = cast("str", implementation["plugin"])
    block = cast("dict[str, object]", parsed[plugin])
    connection = cast("dict[str, object]", block["connection"])
    return cast("str", connection["prefix"])


def _tenant_id_re(*, tenant_prefix: str) -> re.Pattern[str]:
    """Return the same-tenant work-item id matcher for `tenant_prefix`."""
    return re.compile(rf"^{re.escape(tenant_prefix)}-[a-z0-9]+$")


def _direct_plan_dirs(*, plan_dir: Path) -> list[Path]:
    """Return direct active plan directories."""
    return sorted(
        path for path in plan_dir.iterdir() if path.is_dir() and path.name != _ARCHIVE_DIR_NAME
    )


def _direct_archive_dirs(*, plan_dir: Path) -> list[Path]:
    """Return direct archived plan directories."""
    archive_dir = plan_dir / _ARCHIVE_DIR_NAME
    if not archive_dir.is_dir():
        return []
    return sorted(path for path in archive_dir.iterdir() if path.is_dir())


def _metadata_slug(*, record: dict[str, object]) -> str | None:
    """Return a ledger-held plan slug from a plan epic record."""
    metadata = record.get("metadata")
    if isinstance(metadata, dict):
        typed_metadata = cast("dict[str, object]", metadata)
        slug = typed_metadata.get("plan_slug")
        return slug if isinstance(slug, str) else None
    return None


def _is_plan_epic(*, record: dict[str, object], tenant_id_re: re.Pattern[str]) -> bool:
    """Return True for same-tenant records that can anchor plans."""
    item_id = record_id(record=record)
    return (
        record.get("type") == "epic"
        and item_id is not None
        and tenant_id_re.match(item_id) is not None
    )


def _plan_epics_by_slug(
    *, records: list[dict[str, object]], tenant_id_re: re.Pattern[str]
) -> dict[str, list[dict[str, object]]]:
    """Group same-tenant plan epic records by ledger-held plan slug."""
    grouped: dict[str, list[dict[str, object]]] = {}
    for record in records:
        slug = _metadata_slug(record=record)
        if _is_plan_epic(record=record, tenant_id_re=tenant_id_re) and slug is not None:
            grouped.setdefault(slug, []).append(record)
    return grouped


def _status_tuple(
    *, path: Path, slug: str, grouped: dict[str, list[dict[str, object]]]
) -> tuple[Path, str, str | None] | None:
    """Return one parity status tuple, or None when the anchor is missing/ambiguous."""
    records = grouped.get(slug, [])
    if len(records) != 1:
        return None
    anchor = cast("str", record_id(record=records[0]))
    status = records[0].get("status")
    return (path, anchor, status if isinstance(status, str) else None)


def _statuses(
    *, paths: list[Path], grouped: dict[str, list[dict[str, object]]]
) -> list[tuple[Path, str, str | None]]:
    """Return same-tenant plan anchor statuses for paths with exactly one anchor."""
    found: list[tuple[Path, str, str | None]] = []
    for path in paths:
        status = _status_tuple(path=path, slug=path.name, grouped=grouped)
        if status is not None:
            found.append(status)
    return found


def _missing_anchor_paths(
    *, paths: list[Path], grouped: dict[str, list[dict[str, object]]]
) -> list[Path]:
    """Return plan dirs whose slug lacks exactly one same-tenant metadata anchor."""
    return [path for path in paths if len(grouped.get(path.name, [])) != 1]


def main(
    *,
    status_reader: StatusReader | None = None,
    item_reader: ItemReader | None = None,
) -> int:
    """Run the armed ledger-backed plan parity check."""
    legacy_status_reader = _bd_status_reader if status_reader is None else status_reader
    _ = legacy_status_reader
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    log = structlog.get_logger("plan_epic_parity")
    if not _is_armed():
        log.info(
            "skipped — set LIVESPEC_RUN_PLAN_EPIC_PARITY and provide BEADS_DOLT_PASSWORD to arm",
            run_lever=_RUN_LEVER,
            credential=_CRED_ENV,
        )
        return 0
    cwd = Path.cwd()
    plan_dir = cwd / _PLAN_DIR_NAME
    read_items: ItemReader = bd_items_reader if item_reader is None else item_reader
    records = read_items(repo=cwd)
    tenant_id_re = _tenant_id_re(tenant_prefix=_store_prefix(cwd=cwd))
    grouped = _plan_epics_by_slug(records=records, tenant_id_re=tenant_id_re)
    active_dirs = _direct_plan_dirs(plan_dir=plan_dir) if plan_dir.is_dir() else []
    archived_dirs = _direct_archive_dirs(plan_dir=plan_dir)
    active_statuses = _statuses(paths=active_dirs, grouped=grouped)
    archived_statuses = _statuses(paths=archived_dirs, grouped=grouped)

    missing_active = _missing_anchor_paths(paths=active_dirs, grouped=grouped)
    missing_archived = _missing_anchor_paths(paths=archived_dirs, grouped=grouped)
    active_closed = [entry for entry in active_statuses if entry[2] in _CLOSED_STATUSES]
    archived_open = [entry for entry in archived_statuses if entry[2] not in _CLOSED_STATUSES]
    incomplete_descendants = descendant_offenders(
        statuses=archived_statuses,
        item_reader=read_items,
        tenant_id_re=tenant_id_re,
        repo=cwd,
    )

    for path in [*missing_active, *missing_archived]:
        log.error(
            "plan directory missing ledger epic metadata anchor",
            file=str(path.relative_to(cwd)),
            disposition="re-scoped",
            remediation=_MISSING_REMEDIATION,
        )
    for path, anchor, status in active_closed:
        log.error(
            "active plan directory points at a done/closed ledger epic",
            file=str(path.relative_to(cwd)),
            epic=anchor,
            epic_status=status or "unresolved",
            disposition="re-scoped",
            remediation=_ACTIVE_REMEDIATION,
        )
    for path, anchor, status in archived_open:
        log.error(
            "archived plan directory points at an open or unreadable ledger epic",
            file=str(path.relative_to(cwd)),
            epic=anchor,
            epic_status=status or "unresolved",
            disposition="re-scoped",
            remediation=_ARCHIVED_REMEDIATION,
        )
    for path, anchor, descendant in incomplete_descendants:
        log.error(
            "archived plan thread anchor has an incomplete replacement descendant",
            file=str(path.relative_to(cwd)),
            epic=anchor,
            descendant=descendant,
            disposition="re-scoped",
            remediation=_DESCENDANT_REMEDIATION,
        )
    return (
        1
        if missing_active
        or missing_archived
        or active_closed
        or archived_open
        or incomplete_descendants
        else 0
    )


_parse_status = parse_status


if __name__ == "__main__":
    raise SystemExit(main())
