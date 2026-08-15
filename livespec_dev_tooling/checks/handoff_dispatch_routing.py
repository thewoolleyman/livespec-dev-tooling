"""handoff_dispatch_routing — retired git-handoff routing scanner.

Disposition: RETIRED against the ratified Planning Lane contract
(`livespec` SPECIFICATION/history/v197; orchestrator realization v059).

The old invariant scanned active `plan/*/handoff.md` files for
colon-qualified in-session implementation invocations. Ratified Planning Lane
handoffs are ledger-held timeline entries, and the `plan` operation never
authors git `handoff.md` files. Keeping this scanner would continue governing a
carrier the new contract removed from the live protocol; re-scoping the routing
rule requires a ledger-timeline verifier, not a filesystem handoff grep.

The module remains executable until the sibling S3 slug cleanup removes or
renames retired checks.
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
    log = structlog.get_logger("handoff_dispatch_routing")
    log.info(
        "retired git-handoff routing scanner; handoff entries are ledger-held now",
        check_id="handoff_dispatch_routing",
        disposition="retired",
        replacement="ledger-held handoff timeline verifier",
        reason="ratified Planning Lane stores handoffs in the ledger timeline, not git files",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
