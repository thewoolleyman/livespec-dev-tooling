"""plan_no_tombstone — live and archived plan topics must not both exist.

Disposition: KEPT against the ratified Planning Lane contract (`livespec`
SPECIFICATION/history/v197; orchestrator realization v059).

A tombstone is a stub left at `plan/<topic>/` after the real plan thread has
moved to `plan/archive/<topic>/`. The banned condition is structural: the same
topic directory exists in BOTH places at once. This check detects that directory
pair directly and never reads or greps handoff text. The carrier migration from
git handoff files to ledger-held plan metadata does not retire or re-scope this
invariant: active and archived plan directories remain mutually exclusive
locations for one plan record.

The ban is universal and fail-closed: there is no consumer opt-in lever and no
credential requirement. A repo with no `plan/` directory, only a live topic, or
only an archived topic passes.

Output discipline: per spec, `print` (T20) and `sys.stderr.write`
(`check-no-write-direct`) are banned in dev-tooling/**. Diagnostics flow through
structlog (JSON to stderr); the vendored copy under
`livespec_dev_tooling/_vendor/structlog` is added to `sys.path` at import time.
"""

from __future__ import annotations

import sys
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

__all__: list[str] = []


_PLAN_DIR_NAME = "plan"
_ARCHIVE_DIR_NAME = "archive"

_REMEDIATION = (
    "remove one side of the tombstone pair: either keep the thread live at "
    "`plan/<topic>/` until blockers are resolved, or archive it with a clean "
    "`git mv plan/<topic> plan/archive/<topic>` that leaves nothing at the live path."
)


def _child_dir_names(*, parent: Path) -> set[str]:
    """Return direct child directory names under `parent`, or an empty set when absent."""
    if not parent.is_dir():
        return set()
    return {path.name for path in parent.iterdir() if path.is_dir()}


def _tombstone_topics(*, plan_dir: Path) -> list[str]:
    """Return topics present at both `plan/<topic>/` and `plan/archive/<topic>/`."""
    live_topics = _child_dir_names(parent=plan_dir) - {_ARCHIVE_DIR_NAME}
    archived_topics = _child_dir_names(parent=plan_dir / _ARCHIVE_DIR_NAME)
    return sorted(live_topics & archived_topics)


def main() -> int:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    log = structlog.get_logger("plan_no_tombstone")
    cwd = Path.cwd()
    plan_dir = cwd / _PLAN_DIR_NAME
    offenders = _tombstone_topics(plan_dir=plan_dir)
    for topic in offenders:
        log.error(
            "plan thread tombstone detected: topic exists at live and archived paths",
            topic=topic,
            live_dir=str(Path(_PLAN_DIR_NAME) / topic),
            archived_dir=str(Path(_PLAN_DIR_NAME) / _ARCHIVE_DIR_NAME / topic),
            disposition="kept",
            remediation=_REMEDIATION,
        )
    return 1 if offenders else 0


if __name__ == "__main__":
    raise SystemExit(main())
