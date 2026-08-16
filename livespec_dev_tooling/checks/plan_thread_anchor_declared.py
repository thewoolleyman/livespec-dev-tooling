"""plan_thread_anchor_declared — retired filesystem plan-anchor invariant.

Disposition: RETIRED against the ratified Planning Lane contract
(`livespec` SPECIFICATION/history/v197; orchestrator realization v059).

The old invariant required active git handoff documents to declare a concrete
`**Ledger anchor:**` line. That carrier is no longer conforming: v197 forbids
live git `handoff.md` / `supervisor-handoff.md` files in the plan protocol, and
v059 anchors a plan by ledger epic metadata (`plan_slug`) rather than by a git
anchor document. Re-scoping this module to require `epic.md` or a handoff anchor
would recreate an outlawed filesystem metadata file. The ledger-backed parity
invariant that can still be checked with credentials lives in
`plan_thread_epic_parity`.

The module intentionally remains importable and executable until the sibling S3
slug cleanup decides which retired checks leave the canonical set.
"""

from __future__ import annotations

import sys
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

__all__: list[str] = []


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
    log.info(
        "retired filesystem plan-anchor invariant; plan anchors are ledger-held now",
        check_id="plan_thread_anchor_declared",
        disposition="retired",
        replacement="plan_thread_epic_parity",
        reason="ratified Planning Lane uses ledger-held plan epic metadata, not git anchor files",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
