"""plan_thread_epic_parity — active plan threads must not point at a done/closed epic.

The ledger-state PARITY half of plan-lifecycle enforcement. For each ACTIVE plan
handoff (`plan/*/handoff.md`, excluding `plan/archive/`), reads the ledger status
of its `**Ledger anchor:**` epic and FAILS when an active thread points at a
`done`/`closed` epic — the exact drift that leaves a completed plan thread
un-archived. Only same-tenant `livespec-dev-tooling-*` ids are parity-checked;
cross-tenant prose refs (e.g. `livespec-…`) are ignored (decisions 41/44/45).

ARMED-ONLY: self-skips (structured info, exit 0) UNLESS BOTH the RUN lever
`LIVESPEC_RUN_PLAN_EPIC_PARITY` is truthy AND the beads credential
`BEADS_DOLT_PASSWORD` is present. This keeps the check out of the default blocking
`just check` in credential-less CI and in un-armed local runs — mirroring
`check_mutation` (`LIVESPEC_RUN_MUTATION`) / `fleet_conformance`
(`LIVESPEC_RUN_FLEET_CONFORMANCE`) for the RUN lever, and `master_ci_green` for
the credential-absent skip. So it never self-gates a `just check`.

The ledger read is an injected seam (`status_reader`) so tests exercise the armed
path without a live ledger; the default reads `bd -C <cwd> show <id> --json`.

Output discipline: per spec, `print` (T20) and `sys.stderr.write`
(`check-no-write-direct`) are banned in dev-tooling/**. Diagnostics flow through
structlog (JSON to stderr); the vendored copy under
`livespec_dev_tooling/_vendor/structlog` is added to `sys.path` at import time.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Protocol, cast

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

__all__: list[str] = []


_PLAN_DIR_NAME = "plan"
_ARCHIVE_DIR_NAME = "archive"
_HANDOFF_GLOB = "*/handoff.md"
_RUN_LEVER = "LIVESPEC_RUN_PLAN_EPIC_PARITY"
_CRED_ENV = "BEADS_DOLT_PASSWORD"
_CLOSED_STATUSES = frozenset({"closed", "done"})

_ANCHOR_RE = re.compile(r"\*\*Ledger anchor:\*\*\s*(?:epic\s*)?`?([^`\n)]*?)`?(?:\s|$|\))")
_TENANT_ID_RE = re.compile(r"^livespec-dev-tooling-[a-z0-9]+$")

_REMEDIATION = (
    "the plan thread is complete — archive it with "
    "`git mv plan/<topic> plan/archive/<topic>`; an active thread pointing at a "
    "done/closed epic is the un-archived-thread drift this check prevents."
)


class StatusReader(Protocol):
    """Resolve a ledger epic id to its status string (or None when unresolvable)."""

    def __call__(self, *, epic_id: str, repo: Path) -> str | None:
        """Return the ledger status of `epic_id` under `repo`."""
        ...


def _active_handoffs(*, plan_dir: Path) -> list[Path]:
    """Return active `plan/<topic>/handoff.md` paths, excluding `plan/archive/`."""
    return sorted(
        path for path in plan_dir.glob(_HANDOFF_GLOB) if path.parent.name != _ARCHIVE_DIR_NAME
    )


def _same_tenant_anchor(*, text: str) -> str | None:
    """Return the handoff's same-tenant `livespec-dev-tooling-*` anchor id, else None."""
    match = _ANCHOR_RE.search(text)
    if match is None:
        return None
    token = match.group(1).strip().strip("`").strip()
    return token if _TENANT_ID_RE.match(token) is not None else None


def _parse_status(*, text: str) -> str | None:
    """Extract the `status` field from `bd show --json` output, tolerating a preamble."""
    starts = [pos for pos in (text.find("{"), text.find("[")) if pos >= 0]
    if not starts:
        return None
    parsed = json.loads(text[min(starts) :])
    if isinstance(parsed, list):
        parsed_list = cast("list[object]", parsed)
        record: object = parsed_list[0] if parsed_list else {}
    else:
        record = parsed
    if not isinstance(record, dict):
        return None
    status = cast("dict[str, object]", record).get("status")
    return status if isinstance(status, str) else None


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
    return _parse_status(text=completed.stdout)


def _is_armed() -> bool:
    """True iff the RUN lever is truthy AND the beads credential is present."""
    return bool(os.environ.get(_RUN_LEVER)) and bool(os.environ.get(_CRED_ENV))


def main(*, status_reader: StatusReader | None = None) -> int:
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
    cwd = Path.cwd()
    plan_dir = cwd / _PLAN_DIR_NAME
    if not plan_dir.is_dir():
        return 0
    offenders: list[tuple[Path, str, str]] = []
    for path in _active_handoffs(plan_dir=plan_dir):
        anchor = _same_tenant_anchor(text=path.read_text(encoding="utf-8"))
        if anchor is None:
            continue
        status = reader(epic_id=anchor, repo=cwd)
        if status in _CLOSED_STATUSES:
            offenders.append((path, anchor, status))
    for path, anchor, status in offenders:
        log.error(
            "active plan thread points at a done/closed ledger epic",
            file=str(path.relative_to(cwd)),
            epic=anchor,
            epic_status=status,
            remediation=_REMEDIATION,
        )
    return 1 if offenders else 0


if __name__ == "__main__":
    raise SystemExit(main())
