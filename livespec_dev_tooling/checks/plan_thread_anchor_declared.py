"""plan_thread_anchor_declared — active plan handoffs must declare a concrete Ledger anchor.

Scans ACTIVE plan-thread documents (`plan/*/handoff.md` legacy lane and
`plan/*/epic.md` migrated lane, EXCLUDING everything under `plan/archive/`) and
FAILS when a document does not declare a concrete Ledger epic id. Legacy
handoffs declare `**Ledger anchor:**`; migrated epics declare a
`# Ledger epic anchor` heading followed by the id. The legacy anchor may sit
MID-LINE after a `·` separator, so the whole file is searched for the FIRST
`**Ledger anchor:**` occurrence (first-match: a handoff that merely documents the
anchor format in prose still passes on its concrete header). A missing, empty,
or placeholder anchor (`<epic-id>`, `<...>`, `TBD`, a bare `epic` with no id)
fails. A repo with no `plan/` directory passes trivially.

Rationale: a completed plan thread was once treated as done after its
implementation PR merged while the plan lifecycle was left incomplete. Requiring
every active handoff to declare a concrete ledger anchor is the static,
credential-free half of the plan-lifecycle enforcement — it runs everywhere,
including credential-less consumer CI. The ledger-state PARITY half (an active
thread must not point at a done/closed epic) needs ledger credentials and lives
in `plan_thread_epic_parity`.

Output discipline: per spec, `print` (T20) and `sys.stderr.write`
(`check-no-write-direct`) are banned in dev-tooling/**. Diagnostics flow through
structlog (JSON to stderr); the vendored copy under
`livespec_dev_tooling/_vendor/structlog` is added to `sys.path` at import time.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

from livespec_dev_tooling.config import (  # noqa: E402
    ConfigParseError,
    load_plan_lifecycle_anchor,
)

__all__: list[str] = []


_PLAN_DIR_NAME = "plan"
_ARCHIVE_DIR_NAME = "archive"
_HANDOFF_GLOB = "*/handoff.md"
_EPIC_GLOB = "*/epic.md"
_CONFIG_KEY = "plan_lifecycle_anchor"

# The anchor may sit mid-line after a `·` separator, so the whole file is searched
# for the FIRST `**Ledger anchor:**` occurrence. The captured token is the epic id
# (optionally after the word `epic`, optionally backtick- or bold-wrapped).
_ANCHOR_RE = re.compile(
    r"\*\*Ledger anchor:\*\*\s*"
    r"(?:epic\s*)?"
    r"(?:\*\*)?"
    r"`?([a-z][a-z0-9]*(?:-[a-z0-9]+)+)`?"
    r"(?:\*\*)?"
    r"(?=[\s),.;]|$)"
)
_EPIC_ANCHOR_RE = re.compile(
    r"(?mi)^#\s+Ledger epic anchor\s*$\s*^`?([a-z][a-z0-9]*(?:-[a-z0-9]+)+)`?\s*$"
)

_REMEDIATION = (
    "add a concrete `**Ledger anchor:**` line naming this thread's ledger epic "
    "(e.g. `**Ledger anchor:** epic <tenant>-<id>`); a missing, empty, or "
    "placeholder anchor leaves the plan thread untraceable to its ledger record. "
    "use `**Ledger anchor:**`, not `**Epic anchor:**`; `**Epic anchor:**` is a "
    "repo-side label deviation, not an accepted alias."
)


def _active_handoffs(*, plan_dir: Path) -> list[Path]:
    """Return active legacy `plan/<topic>/handoff.md` paths."""
    return sorted(
        path for path in plan_dir.glob(_HANDOFF_GLOB) if path.parent.name != _ARCHIVE_DIR_NAME
    )


def _active_epics(*, plan_dir: Path) -> list[Path]:
    """Return active migrated `plan/<topic>/epic.md` paths."""
    return sorted(
        path for path in plan_dir.glob(_EPIC_GLOB) if path.parent.name != _ARCHIVE_DIR_NAME
    )


def _active_plan_documents(*, plan_dir: Path) -> list[Path]:
    """Return active legacy and migrated plan-lane documents."""
    return sorted([*_active_handoffs(plan_dir=plan_dir), *_active_epics(plan_dir=plan_dir)])


def _declared_anchor(*, text: str) -> str | None:
    """Return the first concrete ledger-anchor id, or None when missing/placeholder."""
    match = _ANCHOR_RE.search(text)
    if match is not None:
        return match.group(1)
    epic_match = _EPIC_ANCHOR_RE.search(text)
    if epic_match is not None:
        return epic_match.group(1)
    return None


def main() -> int:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    log = structlog.get_logger("plan_thread_anchor_declared")
    cwd = Path.cwd()
    try:
        enabled = load_plan_lifecycle_anchor(repo_root=cwd)
    except ConfigParseError as exc:
        log.exception(
            "configuration error",
            check_id="plan_thread_anchor_declared",
            key=_CONFIG_KEY,
            error=str(exc),
        )
        return 1
    if enabled is not True:
        log.info(
            "plan-lifecycle anchor convention not declared by this consumer; check self-skips",
            check_id="plan_thread_anchor_declared",
            key=_CONFIG_KEY,
            value=enabled,
        )
        return 0
    plan_dir = cwd / _PLAN_DIR_NAME
    if not plan_dir.is_dir():
        return 0
    offenders = [
        path
        for path in _active_plan_documents(plan_dir=plan_dir)
        if _declared_anchor(text=path.read_text(encoding="utf-8")) is None
    ]
    for path in offenders:
        log.error(
            "active plan handoff does not declare a concrete Ledger anchor",
            file=str(path.relative_to(cwd)),
            remediation=_REMEDIATION,
        )
    return 1 if offenders else 0


if __name__ == "__main__":
    raise SystemExit(main())
