"""plan_thread_epic_parity — plan archive state must match ledger epic state.

The ledger-state PARITY half of plan-lifecycle enforcement. It asserts both
directions deliberately:

* for each ACTIVE plan handoff (`plan/*/handoff.md`, excluding
  `plan/archive/`), FAIL when the anchor epic is `done`/`closed` — the drift
  that leaves a completed plan thread un-archived;
* for each ARCHIVED plan handoff (`plan/archive/**/handoff.md`), FAIL when the
  anchor epic is anything other than `done`/`closed` — the drift that archives
  a thread while its owning epic is still in flight; and FAIL when the archived
  anchor has same-tenant replacement descendants that are not completion-closed
  — the drift that treats a procedural regroom-out/supersession closure as
  finished work.

Only ids under the checked repo's tenant prefix are parity-checked; cross-tenant
prose refs (e.g. `livespec-...`) are ignored (decisions 41/44/45).

ARMED-ONLY: self-skips (structured info, exit 0) UNLESS BOTH the RUN lever
`LIVESPEC_RUN_PLAN_EPIC_PARITY` is truthy AND the beads credential
`BEADS_DOLT_PASSWORD` is present. This keeps the check out of the default blocking
`just check` in credential-less CI and in un-armed local runs — mirroring
`check_mutation` (`LIVESPEC_RUN_MUTATION`) / `fleet_conformance`
(`LIVESPEC_RUN_FLEET_CONFORMANCE`) for the RUN lever, and `master_ci_green` for
the credential-absent skip. The archived-thread converse is also armed-only by
explicit product decision, not by inheritance: it needs the same ledger status
read as the active-thread assertion, and credential-less CI cannot distinguish
an open epic from an unreadable ledger item. So it never self-gates a `just
check`.

The ledger read is an injected seam (`status_reader`) so tests exercise the armed
path without a live ledger; the default reads `bd -C <cwd> show <id> --json`.

Output discipline: per spec, `print` (T20) and `sys.stderr.write`
(`check-no-write-direct`) are banned in dev-tooling/**. Diagnostics flow through
structlog (JSON to stderr); the vendored copy under
`livespec_dev_tooling/_vendor/structlog` is added to `sys.path` at import time.
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

from livespec_dev_tooling.checks._plan_thread_ledger import (  # noqa: E402
    ItemReader,
    bd_items_reader,
    descendant_offenders,
    parse_status,
)

__all__: list[str] = []


_PLAN_DIR_NAME = "plan"
_ARCHIVE_DIR_NAME = "archive"
_HANDOFF_GLOB = "*/handoff.md"
_ARCHIVED_HANDOFF_GLOB = f"{_ARCHIVE_DIR_NAME}/**/handoff.md"
_LIVESPEC_CONFIG = ".livespec.jsonc"
_RUN_LEVER = "LIVESPEC_RUN_PLAN_EPIC_PARITY"
_CRED_ENV = "BEADS_DOLT_PASSWORD"
_CLOSED_STATUSES = frozenset({"closed", "done"})

_ANCHOR_RE = re.compile(r"\*\*Ledger anchor:\*\*\s*(?:epic\s*)?`?([^`\n)]*?)`?(?:\s|$|\))")

_REMEDIATION = (
    "the plan thread is complete — archive it with "
    "`git mv plan/<topic> plan/archive/<topic>`; an active thread pointing at a "
    "done/closed epic is the un-archived-thread drift this check prevents."
)

_ARCHIVED_REMEDIATION = (
    "restore the thread to `plan/<topic>` until its ledger epic is done/closed; "
    "an archived thread pointing at an open or unreadable epic is premature."
)

_DESCENDANT_REMEDIATION = (
    "restore the thread to `plan/<topic>` until every replacement descendant "
    "that depends on its anchor epic is closed with a completion-shaped "
    "resolution; a procedural anchor closure is not completion evidence."
)


class StatusReader(Protocol):
    """Resolve a ledger epic id to its status string (or None when unresolvable)."""

    def __call__(self, *, epic_id: str, repo: Path) -> str | None:
        """Return the ledger status of `epic_id` under `repo`."""
        ...


class StatusPredicate(Protocol):
    """Return True when a ledger status violates one side of parity."""

    def __call__(self, *, status: str | None) -> bool:
        """Return whether `status` is a parity violation."""
        ...


def _active_handoffs(*, plan_dir: Path) -> list[Path]:
    """Return active `plan/<topic>/handoff.md` paths, excluding `plan/archive/`."""
    return sorted(
        path for path in plan_dir.glob(_HANDOFF_GLOB) if path.parent.name != _ARCHIVE_DIR_NAME
    )


def _archived_handoffs(*, plan_dir: Path) -> list[Path]:
    """Return archived `plan/archive/**/handoff.md` paths."""
    return sorted(plan_dir.glob(_ARCHIVED_HANDOFF_GLOB))


def _tenant_id_re(*, tenant_prefix: str) -> re.Pattern[str]:
    """Return the same-tenant work-item id matcher for `tenant_prefix`."""
    return re.compile(rf"^{re.escape(tenant_prefix)}-[a-z0-9]+$")


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


def _same_tenant_anchor(*, text: str, tenant_id_re: re.Pattern[str]) -> str | None:
    """Return the handoff's same-tenant anchor id, else None."""
    match = _ANCHOR_RE.search(text)
    if match is None:
        return None
    token = match.group(1).strip().strip("`").strip()
    return token if tenant_id_re.match(token) is not None else None


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


def _is_closed_status(*, status: str | None) -> bool:
    """Return True when `status` is a ledger-closed state."""
    return status in _CLOSED_STATUSES


def _is_not_closed_status(*, status: str | None) -> bool:
    """Return True when `status` is not a ledger-closed state."""
    return status not in _CLOSED_STATUSES


def _handoff_statuses(
    *,
    paths: list[Path],
    tenant_id_re: re.Pattern[str],
    reader: StatusReader,
    repo: Path,
) -> list[tuple[Path, str, str | None]]:
    """Return same-tenant handoff anchor statuses for `paths`."""
    statuses: list[tuple[Path, str, str | None]] = []
    for path in paths:
        anchor = _same_tenant_anchor(
            text=path.read_text(encoding="utf-8"),
            tenant_id_re=tenant_id_re,
        )
        if anchor is None:
            continue
        statuses.append((path, anchor, reader(epic_id=anchor, repo=repo)))
    return statuses


def _offenders(
    *,
    statuses: list[tuple[Path, str, str | None]],
    violates: StatusPredicate,
) -> list[tuple[Path, str, str]]:
    """Return handoff statuses that violate a parity predicate."""
    offenders: list[tuple[Path, str, str]] = []
    for path, anchor, status in statuses:
        if violates(status=status):
            offenders.append((path, anchor, status or "unresolved"))
    return offenders


def main(
    *,
    status_reader: StatusReader | None = None,
    item_reader: ItemReader | None = None,
) -> int:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    log = structlog.get_logger("plan_thread_epic_parity")
    if not _is_armed():
        log.info(
            "skipped — set LIVESPEC_RUN_PLAN_EPIC_PARITY and provide BEADS_DOLT_PASSWORD to arm",
            run_lever=_RUN_LEVER,
            credential=_CRED_ENV,
        )
        return 0
    reader: StatusReader = _bd_status_reader if status_reader is None else status_reader
    read_items: ItemReader = bd_items_reader if item_reader is None else item_reader
    cwd = Path.cwd()
    plan_dir = cwd / _PLAN_DIR_NAME
    if not plan_dir.is_dir():
        return 0
    tenant_id_re = _tenant_id_re(tenant_prefix=_store_prefix(cwd=cwd))
    active_statuses = _handoff_statuses(
        paths=_active_handoffs(plan_dir=plan_dir),
        tenant_id_re=tenant_id_re,
        reader=reader,
        repo=cwd,
    )
    archived_statuses = _handoff_statuses(
        paths=_archived_handoffs(plan_dir=plan_dir),
        tenant_id_re=tenant_id_re,
        reader=reader,
        repo=cwd,
    )
    offenders = _offenders(statuses=active_statuses, violates=_is_closed_status)
    archived_offenders = _offenders(
        statuses=archived_statuses,
        violates=_is_not_closed_status,
    )
    incomplete_descendants = descendant_offenders(
        statuses=archived_statuses,
        item_reader=read_items,
        tenant_id_re=tenant_id_re,
        repo=cwd,
    )
    for path, anchor, status in offenders:
        log.error(
            "active plan thread points at a done/closed ledger epic",
            file=str(path.relative_to(cwd)),
            epic=anchor,
            epic_status=status,
            remediation=_REMEDIATION,
        )
    for path, anchor, status in archived_offenders:
        log.error(
            "archived plan thread points at an open or unreadable ledger epic",
            file=str(path.relative_to(cwd)),
            epic=anchor,
            epic_status=status,
            remediation=_ARCHIVED_REMEDIATION,
        )
    for path, anchor, descendant in incomplete_descendants:
        log.error(
            "archived plan thread anchor has an incomplete replacement descendant",
            file=str(path.relative_to(cwd)),
            epic=anchor,
            descendant=descendant,
            remediation=_DESCENDANT_REMEDIATION,
        )
    return 1 if offenders or archived_offenders or incomplete_descendants else 0


_parse_status = parse_status


if __name__ == "__main__":
    raise SystemExit(main())
