"""plan_record_conformance — the eleven ratified plan-record conformance verdicts.

Realizes the plan-record conformance contract in
`livespec-orchestrator-beads-fabro` `SPECIFICATION/contracts.md` (v095) for the
fleet, beside `plan_epic_parity` in the shared checks package the same contract
names as their sanctioned home.
Each verdict reports its ratified check id, the offending epic id or directory
path, and one remediation sentence:

- `plan_slug_present`, `plan_slug_unique`, `plan_slug_canonical`,
  `plan_slug_on_non_epic` (error) — the ledger-side identity family.
- `plan_anchor_present`, `plan_anchor_consistent` (error) — the
  `associated_work_item_id` pair, graded in both directions.
- `plan_lifecycle_parity` (error) — DELEGATED to `plan_epic_parity`, which the
  contract states already satisfies it. It is not re-derived here: a second
  implementation of one invariant is how two checks come to disagree about it.
- `plan_close_evidence`, `plan_next_action_typed` (error) and
  `plan_next_action_drift`, `plan_comment_rate` (warn) — the timeline family.

ERROR verdicts exit non-zero; WARN verdicts are reported and never fail. That
split is ratified, not a local severity choice: a prose marker line disagreeing
with the typed pointer breaks nothing (the metadata wins by contract) and a
fast-writing day is a smell somebody should see rather than a rule.

ARMED-ONLY, AND SHIPPED UNARMED. The check self-skips unless
`LIVESPEC_RUN_PLAN_RECORD_CONFORMANCE` is truthy and `BEADS_DOLT_PASSWORD` is
present, exactly as `plan_epic_parity` does. ⛔ DO NOT ARM IT — in this repo, in
a consumer, or in a fleet obligation — until the contract's one-shot per-tenant
migration has run there. Adoption first, then arming: a check armed before the
records it grades have been migrated writes verdicts into a tenant that cannot
satisfy them, which is the fleet's `46c5dab` incident restated.

`plan_lifecycle_parity`'s delegate reads its OWN lever
(`LIVESPEC_RUN_PLAN_EPIC_PARITY`), deliberately: this module does not reach into
another check's arming. Arming the family therefore means arming both levers, and
the run says which one governed the delegated leg rather than leaving a silent
skip to look like a pass.

Output discipline: per spec, `print` (T20) and `sys.stderr.write`
(`check-no-write-direct`) are banned here. Diagnostics flow through the vendored
`structlog` (JSON to stderr).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Protocol

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.
from returns.io import IOFailure  # noqa: E402  — vendor-path-aware import.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware import.

from livespec_dev_tooling.checks import plan_epic_parity  # noqa: E402
from livespec_dev_tooling.checks._plan_ledger import (  # noqa: E402
    CommentReader,
    ItemReader,
    bd_comments_reader,
    bd_items_reader,
    store_prefix,
    tenant_id_re,
)
from livespec_dev_tooling.checks._plan_record_anchors import anchor_findings  # noqa: E402
from livespec_dev_tooling.checks._plan_record_dirs import (  # noqa: E402
    PLAN_DIR_NAME,
    plan_directories,
)
from livespec_dev_tooling.checks._plan_record_model import (  # noqa: E402
    CHECK_IDS,
    ERROR_VERDICT,
    Finding,
)
from livespec_dev_tooling.checks._plan_record_slugs import (  # noqa: E402
    plan_epics_by_slug,
    same_tenant_epics,
    slug_findings,
)
from livespec_dev_tooling.checks._plan_record_timeline import timeline_findings  # noqa: E402

__all__: list[str] = []


_RUN_LEVER = "LIVESPEC_RUN_PLAN_RECORD_CONFORMANCE"
_CRED_ENV = "BEADS_DOLT_PASSWORD"
_DELEGATE = "plan_epic_parity"
_DELEGATE_LEVER = "LIVESPEC_RUN_PLAN_EPIC_PARITY"
_LIFECYCLE_CHECK_ID = "plan_lifecycle_parity"
_LIFECYCLE_REMEDIATION = (
    "read the delegated `plan_epic_parity` findings beside this one: an active "
    "`plan/<slug>/` must anchor an open epic and an archived record a closed "
    "one; reopen the epic or archive the record whole."
)
# Every input this family reads is on the `IOResult` railway
# (`livespec-dev-tooling-qndn.4`), and a read that DID NOT HAPPEN gets its own
# verdict rather than a silent pass: exiting 0 would report all eleven verdicts
# as satisfied over a population the check never saw. That is this module's own
# recorded incident (`livespec-dev-tooling-7b6l`) — an unread timeline arriving
# as an empty comment list, and `plan_close_evidence` convicting real epics on
# an absence nothing had established.
_UNREADABLE_VERDICT = "input-unreadable"
_UNREADABLE_REMEDIATION = (
    "the armed family never obtained one of its inputs, so it holds no opinion "
    "about any of its eleven verdicts: the named reason says which read failed "
    "and the detail carries the evidence. Repair that read — for `bd-failed`, "
    "project the tenant credential through the installed wrapper — and re-run."
)


class LifecycleRunner(Protocol):
    """The delegated lifecycle-parity check, injected so tests can drive it."""

    def __call__(self, *, item_reader: ItemReader) -> int:
        """Return the delegate's exit code."""
        ...


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
    return structlog.get_logger("plan_record_conformance")


def _lifecycle_findings(
    *,
    log: structlog.stdlib.BoundLogger,
    run_lifecycle: LifecycleRunner,
    read_items: ItemReader,
) -> list[Finding]:
    """Delegate the lifecycle invariant and report the delegate's verdict."""
    exit_code = run_lifecycle(item_reader=read_items)
    log.info(
        "plan_lifecycle_parity is delegated to the fleet plan_epic_parity check",
        check_id=_LIFECYCLE_CHECK_ID,
        delegate=_DELEGATE,
        delegate_run_lever=_DELEGATE_LEVER,
        delegate_exit_code=exit_code,
    )
    if exit_code == 0:
        return []
    return [
        Finding(
            check_id=_LIFECYCLE_CHECK_ID,
            subject=PLAN_DIR_NAME,
            verdict=ERROR_VERDICT,
            message=f"delegated {_DELEGATE} reported a plan-lifecycle violation",
            remediation=_LIFECYCLE_REMEDIATION,
        )
    ]


def _report(*, log: structlog.stdlib.BoundLogger, findings: list[Finding]) -> None:
    """Emit one structured diagnostic per finding, at its ratified severity."""
    for finding in findings:
        emit = log.error if finding.verdict == ERROR_VERDICT else log.warning
        emit(
            finding.message,
            check_id=finding.check_id,
            subject=finding.subject,
            verdict=finding.verdict,
            remediation=finding.remediation,
        )


def _refuse(*, log: structlog.stdlib.BoundLogger, reason: str, detail: str) -> int:
    """Report an input the armed family could not read, and refuse the run.

    Reached from four call sites carrying two failure types
    (`_plan_ledger.LedgerReadFailed` and `_plan_record_dirs.PlanTreeUnreadable`),
    which is why it takes the two rendered strings rather than either type: the
    operator reads the same shape whichever input went unread.
    """
    log.error(
        "armed plan-record conformance family could not read one of its inputs",
        check_ids=list(CHECK_IDS),
        verdict=_UNREADABLE_VERDICT,
        reason=reason,
        detail=detail,
        remediation=_UNREADABLE_REMEDIATION,
    )
    return 1


def main(
    *,
    item_reader: ItemReader | None = None,
    comment_reader: CommentReader | None = None,
    lifecycle_runner: LifecycleRunner | None = None,
) -> int:
    """Run the armed ledger-backed plan-record conformance family."""
    log = _configure_logging()
    if not _is_armed():
        log.info(
            "skipped — set LIVESPEC_RUN_PLAN_RECORD_CONFORMANCE and provide "
            "BEADS_DOLT_PASSWORD to arm",
            run_lever=_RUN_LEVER,
            credential=_CRED_ENV,
            check_ids=list(CHECK_IDS),
        )
        return 0
    return _armed_run(
        log=log,
        read_items=bd_items_reader if item_reader is None else item_reader,
        read_comments=bd_comments_reader if comment_reader is None else comment_reader,
        run_lifecycle=plan_epic_parity.main if lifecycle_runner is None else lifecycle_runner,
        cwd=Path.cwd(),
    )


def _armed_run(
    *,
    log: structlog.stdlib.BoundLogger,
    read_items: ItemReader,
    read_comments: CommentReader,
    run_lifecycle: LifecycleRunner,
    cwd: Path,
) -> int:
    """Grade the eleven verdicts under `cwd`, refusing on any input that did not answer.

    Split out of `main` so the arming decision and the graded run are separate
    bodies; the four read-failure arms below are what pushed one body past the
    statement budget. No behavior moved with the split.
    """
    read = read_items(repo=cwd)
    if isinstance(read, IOFailure):
        unread = unsafe_perform_io(read.failure())
        return _refuse(log=log, reason=unread.reason, detail=unread.detail)
    records = unsafe_perform_io(read.unwrap())
    prefix = store_prefix(cwd=cwd)
    if isinstance(prefix, IOFailure):
        unresolved = unsafe_perform_io(prefix.failure())
        return _refuse(log=log, reason=unresolved.reason, detail=unresolved.detail)
    same_tenant = tenant_id_re(tenant_prefix=unsafe_perform_io(prefix.unwrap()))
    epics = same_tenant_epics(records=records, tenant_re=same_tenant)
    walked = plan_directories(plan_dir=cwd / PLAN_DIR_NAME, tenant_re=same_tenant)
    if isinstance(walked, IOFailure):
        unwalkable = unsafe_perform_io(walked.failure())
        return _refuse(log=log, reason=unwalkable.reason, detail=unwalkable.detail)
    directories = unsafe_perform_io(walked.unwrap())
    timeline = timeline_findings(
        epics=epics,
        live_slugs=frozenset(directory.slug for directory in directories if not directory.archived),
        record_slugs=frozenset(directory.slug for directory in directories),
        read_comments=read_comments,
        repo=cwd,
    )
    if isinstance(timeline, IOFailure):
        unread_timeline = unsafe_perform_io(timeline.failure())
        return _refuse(log=log, reason=unread_timeline.reason, detail=unread_timeline.detail)
    findings = [
        *slug_findings(records=records, tenant_re=same_tenant),
        *anchor_findings(
            directories=directories, grouped=plan_epics_by_slug(epics=epics), records=records
        ),
        *_lifecycle_findings(log=log, run_lifecycle=run_lifecycle, read_items=read_items),
        *unsafe_perform_io(timeline.unwrap()),
    ]
    _report(log=log, findings=findings)
    return 1 if any(finding.verdict == ERROR_VERDICT for finding in findings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
