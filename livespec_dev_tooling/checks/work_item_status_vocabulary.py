"""work_item_status_vocabulary — a live work item must sit in a lane something reads.

`bd create` leaves a new record at BEADS status `open`. The orchestrator runtime
declares a NARROWER lane vocabulary of its own — `livespec_runtime`'s
`WorkItemStatus` Literal, whose seven values are `backlog`, `pending-approval`,
`ready`, `active`, `acceptance`, `blocked`, `done` — and `open` is not one of
them. The two vocabularies disagree and NOTHING RECONCILES THEM: `lane_of`
special-cases only `blocked` and the `ready`-with-open-dependency case, then
returns `Lane(name=item.status)` verbatim, without ever testing the stored status
against the Literal it declares; `is_item_ready` is `lane_of(...).name ==
"ready"`. An item at `open` is therefore never ranked by `next`, and it is
equally not parked in `backlog` for decomposition, not held at `blocked` for a
human, and not waiting at `pending-approval` for admission.

**It is not queued, not blocked, and not refused. It is simply not anywhere** —
and no surface says so, which is what makes the state silent rather than merely
wrong. Measured 2026-08-21: seven live items across the fleet sat there, one of
them a P1. The count was already visible in a status histogram an hour before the
defect was filed and nobody drew anything from it; a bare number is not a finding.

WHY THE VOCABULARY AND NOT THE FOUR INTAKE VERDICTS. The intake
Definition-of-Ready gate produces exactly four verdicts (`pending-approval`,
`ready`, `backlog`, `blocked`), so the obvious check reports anything outside
those four. That check would flag every legitimately in-flight item: `active` and
`acceptance` are lanes the runtime moves items THROUGH, not lanes nothing reads.
Testing the DECLARED VOCABULARY instead is both quieter and strictly more
durable — a future beads value, a status written by a raw tool, or a plain typo
lands in the same dead lane, and a check that merely widened the set of
recognised statuses would catch none of them.

RE-TRIAGING TODAY'S OFFENDERS IS NOT THE REMEDY. The next raw `bd create` puts an
item straight back into the gap; only a mechanism that makes the state VISIBLE
survives the next filing. This check is that mechanism, and it deliberately does
NOT mutate the ledger: moving someone else's item to a verdict lane means
answering six Definition-of-Ready gates about work the mover has not read.

WHAT THIS IS NOT. The `intake:triaged` LABEL is missing on most live records
fleet-wide and that number is NOT this finding — dispatch reads the STATUS, never
the label, so the label is an observability marker rather than an admission gate.
Reporting on it would convert a precise, small population into a fleet-wide panic.

POPULATION: live (non-closed) records only, exactly as the sibling ledger sweep
scopes itself. A closed item is never ranked by design, so no status can strand
it; `done` is in the vocabulary and is also closed, so it leaves the population
on the earlier test either way.

VOCABULARY DRIFT. The seven values below MIRROR the runtime's Literal — this
library does not depend on the orchestrator runtime, so the tuple cannot be
imported from it. A value added there and not here reports as off-vocabulary,
which is a loud, correct-shaped failure (a new lane arriving unannounced is worth
a look) rather than a silent miss.

ARMED-ONLY: self-skips unless `LIVESPEC_RUN_WORK_ITEM_STATUS_VOCABULARY` is
truthy and `BEADS_DOLT_PASSWORD` is present, because it reads ledger state. An
EMPTY ledger read while armed is a FAILURE, not a clean sweep: an armed check
inspecting nothing is a misconfiguration, and reading it as a pass would be the
fail-open this check exists to remove.

Output discipline: per spec, `print` (T20) and `sys.stderr.write`
(`check-no-write-direct`) are banned in dev-tooling/**. Diagnostics flow through
structlog (JSON to stderr); the vendored copy under
`livespec_dev_tooling/_vendor/structlog` is added to `sys.path` at import time.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

from livespec_dev_tooling.checks._plan_ledger import (  # noqa: E402
    ItemReader,
    bd_items_reader,
    record_id,
)

__all__: list[str] = []


_RUN_LEVER = "LIVESPEC_RUN_WORK_ITEM_STATUS_VOCABULARY"
_CRED_ENV = "BEADS_DOLT_PASSWORD"
_CLOSED_STATUSES = frozenset({"closed", "done"})

# The runtime's declared lane vocabulary, mirrored (see "VOCABULARY DRIFT"). A
# live record at any other status renders into a lane name nothing consumes.
_LANE_VOCABULARY = (
    "backlog",
    "pending-approval",
    "ready",
    "active",
    "acceptance",
    "blocked",
    "done",
)

# The four verdicts the intake Definition-of-Ready gate produces — reported
# alongside each finding so the operator reads the admissible landing lanes off
# the finding itself rather than off this source.
_DOR_VERDICTS = (
    "pending-approval",
    "ready",
    "backlog",
    "blocked",
)

# What a finding prints when the record carries no readable status at all. A
# missing status is off-vocabulary for the same reason a wrong one is.
_UNSET_STATUS = "<unset>"

_REMEDIATION = (
    "this item is ranked by nothing: dispatch admits stored status `ready` alone, "
    "and an unrecognised status is passed straight through as a lane name no "
    "surface consumes. Run the intake Definition-of-Ready gate over the item so it "
    "lands on one of its four verdicts, or move it there deliberately. Triage is "
    "the OWNER's call — answering the DoR gates for work you have not read is how "
    "a silent item becomes a wrongly-ranked one."
)
_EMPTY_LEDGER_REMEDIATION = (
    "the armed check read zero ledger records, so it inspected nothing and could "
    "only ever pass. Supply the tenant credential through the installed wrapper "
    "and re-run; a silent empty read is the fail-open this check exists to remove."
)


def _is_armed() -> bool:
    """True iff the RUN lever is truthy AND the beads credential is present."""
    return bool(os.environ.get(_RUN_LEVER)) and bool(os.environ.get(_CRED_ENV))


def _configure_logging() -> structlog.stdlib.BoundLogger:
    """Configure structlog for JSON-to-stderr diagnostics and return the logger."""
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    return structlog.get_logger("work_item_status_vocabulary")


def _status_of(*, record: dict[str, object]) -> str | None:
    """Return a record's stored status, or None when it carries no readable one."""
    value = record.get("status")
    return value if isinstance(value, str) else None


def _is_live(*, status: str | None) -> bool:
    """True while a record can still be ranked — closed items leave the population."""
    return status not in _CLOSED_STATUSES


def _optional_text(*, key: str, record: dict[str, object]) -> str:
    """Return one identifying field rendered as text, or empty when absent."""
    value = record.get(key)
    return "" if value is None else str(value)


def main(*, item_reader: ItemReader | None = None) -> int:
    """Run the armed ledger-backed status-vocabulary sweep."""
    log = _configure_logging()
    if not _is_armed():
        log.info(
            "skipped — set LIVESPEC_RUN_WORK_ITEM_STATUS_VOCABULARY and provide "
            "BEADS_DOLT_PASSWORD to arm",
            run_lever=_RUN_LEVER,
            credential=_CRED_ENV,
        )
        return 0
    cwd = Path.cwd()
    read_items: ItemReader = bd_items_reader if item_reader is None else item_reader
    records = read_items(repo=cwd)
    if not records:
        log.error(
            "armed work-item status-vocabulary sweep read zero ledger records",
            repo=str(cwd),
            remediation=_EMPTY_LEDGER_REMEDIATION,
        )
        return 1
    findings = 0
    for record in records:
        item_id = record_id(record=record)
        status = _status_of(record=record)
        if item_id is None or not _is_live(status=status) or status in _LANE_VOCABULARY:
            continue
        findings += 1
        log.error(
            "live work item sits at a status outside the declared lane vocabulary",
            work_item=item_id,
            status=status if status is not None else _UNSET_STATUS,
            priority=_optional_text(key="priority", record=record),
            title=_optional_text(key="title", record=record),
            lane_vocabulary=list(_LANE_VOCABULARY),
            intake_dor_verdicts=list(_DOR_VERDICTS),
            verdict="off-vocabulary-status",
            remediation=_REMEDIATION,
        )
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
