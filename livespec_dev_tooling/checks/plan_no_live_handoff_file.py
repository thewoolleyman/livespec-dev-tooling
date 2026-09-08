"""plan_no_live_handoff_file — no commit or push may add or modify a live plan handoff file.

Disposition: KEPT, and CONFORMANCE rather than new policy. The ratified Planning
Lane contract (`livespec` SPECIFICATION/spec.md section "Contract + reference
implementations architecture"; SPECIFICATION/history v197, orchestrator
realization v059) already forbids the live git carrier: a plan's handoff is a
LEDGER-HELD timeline entry on the plan epic, and the `plan` operation never
authors a handoff document. `plan_anchor_declared` and `handoff_dispatch_routing`
were RETIRED for exactly that reason — each governed a carrier the contract had
removed. Nothing, until this module, refused the carrier ITSELF, so an agent fed
a stale instruction could still land one as a commit. That is not hypothetical:
in the archive-safe-respawn session one began opening a worktree and a PR to
commit `plan/archive-safe-respawn/handoff.md`, and what stopped it was a human
noticing rather than a gate.

THE GATE IS SCOPED TO THE CHANGE, NOT TO THE TREE, and that is the whole design
rather than an implementation convenience. A tree-scoped scan would fail every
checkout that merely CONTAINS a live handoff file — seven of them across six
sibling repos when this was measured — so the day it shipped it would redden
repos for a file nobody touched, which is this fleet's recorded "arming a check
ahead of adoption" defect. Scoped to the change, an existing file is FROZEN
rather than fatal: it may be read, and it may be DELETED (both reads exclude
deletions, so the migration off the carrier is never blocked by the gate that
bans it), and it may not be added to or edited. Migration becomes a repo's own
next commit instead of a fleet-wide emergency, and the outlawed pattern still
cannot land.

TWO READS, BECAUSE A COMMIT AND A PUSH SEE DIFFERENT THINGS. At the pre-commit
gate the offending file is in the INDEX and not yet in `HEAD`, so only
`git diff --cached` can see it; at the pre-push gate and in CI it is in `HEAD`
and only the `origin/master...HEAD` range can. Taking one read would silently
leave half of "commit or push" ungated, and the missing half would look exactly
like a pass.

A READ THAT DID NOT HAPPEN IS NOT AN EMPTY CHANGED SET. Both reads ride
`_branch_diff`'s `IOResult` railway, and an `IOFailure` — an unfetched
`origin/master`, a shallow clone, a `git` that will not run — FAILS this check
naming the read it could not take. Reporting it as "nothing changed" is the
vacuous green `check_coverage_incremental` already paid for once.

THE SANCTIONED LOCATIONS ARE AN ALLOW-LIST, so a location nobody anticipated is
refused rather than admitted: `plan/archive/**` (the plan has been archived) and
any `research/` directory inside a plan (the plan's own evidence tree) are the
two places these filenames may live. Every other path under `plan/` carrying one
of them is the live carrier.

Output discipline: per spec, `print` (T20) and `sys.stderr.write`
(`check-no-write-direct`) are banned in this package. Diagnostics flow through
structlog (JSON to stderr); the vendored copy under
`livespec_dev_tooling/_vendor/structlog` is added to `sys.path` at import time.
"""

from __future__ import annotations

import sys
from pathlib import Path, PurePosixPath

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.
from returns.io import IOFailure, IOResult, IOSuccess  # noqa: E402  — vendor-path-aware import.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware import.

from livespec_dev_tooling.checks._branch_diff import (  # noqa: E402
    DiffUnavailable,
    name_only_diff,
    staged_name_only,
)

__all__: list[str] = []


_PLAN_DIR_NAME = "plan"
_ARCHIVE_SEGMENT = "archive"
_RESEARCH_SEGMENT = "research"
_HANDOFF_FILENAMES = (
    "handoff.md",
    "supervisor-handoff.md",
)
# `plan/handoff.md` is the shortest path the ban can reach: a plan-tree handoff
# document sitting in no sanctioned location at all.
_MIN_PLAN_PATH_PARTS = 2
# The same range `check_coverage_incremental` derives its gated set from, named
# once so the refusal diagnostic and the range it could not read cannot disagree.
_DIFF_RANGE = "origin/master...HEAD"

_AUTHORITY = (
    "livespec SPECIFICATION/spec.md section 'Contract + reference implementations"
    " architecture' — the ratified Planning Lane (history v197; orchestrator"
    " realization v059)"
)
_REMEDIATION = (
    "A plan's handoff is LEDGER-HELD, not a committed file. Write it as a timeline"
    " entry on the plan's ledger epic through the orchestrator plugin's plan"
    " operation — `livespec-orchestrator-beads-fabro:plan <plan-slug>` — whose"
    " supervise-plan skill prose carries the ledger-held handoff discipline and the"
    " shape of an entry. Then drop this file; a DELETION is not blocked by this"
    " gate, so migrating off the carrier is always available. Historical evidence"
    " keeps two sanctioned homes, both unaffected: `plan/archive/<topic>/` once the"
    " plan is archived, and `plan/<topic>/research/` while it is live."
)
_EVENT = (
    "live plan handoff file added or modified; the plan handoff carrier is the"
    " ledger, not a file in the plan tree"
)
_UNREADABLE_EVENT = (
    "could not take the changed-path diff; the changed set is UNKNOWN, which is not"
    " the same as empty — refusing rather than passing on a read that never happened"
)


def _is_live_handoff_path(*, path: str) -> bool:
    """Whether `path` is a plan handoff document OUTSIDE the two sanctioned locations."""
    parts = PurePosixPath(path).parts
    if len(parts) < _MIN_PLAN_PATH_PARTS or parts[0] != _PLAN_DIR_NAME:
        return False
    if parts[-1] not in _HANDOFF_FILENAMES:
        return False
    interior = parts[1:-1]
    return interior[:1] != (_ARCHIVE_SEGMENT,) and _RESEARCH_SEGMENT not in interior


def _offending_paths(*, diff_output: str) -> list[str]:
    """Every live-handoff path in a `git diff --name-only` blob, de-duplicated and sorted.

    De-duplicated because the two reads OVERLAP: a path can be both staged and
    already committed on the branch, and reporting it twice would read as two
    separate violations of the same file.
    """
    found: set[str] = set()
    for line in diff_output.splitlines():
        path = line.strip()
        if path and _is_live_handoff_path(path=path):
            found.add(path)
    return sorted(found)


def _changed_paths(*, cwd: Path) -> IOResult[str, DiffUnavailable]:
    """The UNION of the staged and branch-range name-only diffs, as one blob.

    EITHER read failing fails the whole answer. A partial union is not a smaller
    changed set, it is an unknown one, and the two are told apart here rather
    than downstream where an empty string is indistinguishable from "clean".
    """
    staged = staged_name_only(cwd=cwd)
    if isinstance(staged, IOFailure):
        return IOFailure(unsafe_perform_io(staged.failure()))
    ranged = name_only_diff(diff_range=_DIFF_RANGE, cwd=cwd)
    if isinstance(ranged, IOFailure):
        return IOFailure(unsafe_perform_io(ranged.failure()))
    return IOSuccess(f"{unsafe_perform_io(staged.unwrap())}\n{unsafe_perform_io(ranged.unwrap())}")


def main() -> int:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    log = structlog.get_logger("plan_no_live_handoff_file")
    read = _changed_paths(cwd=Path.cwd())
    if isinstance(read, IOFailure):
        unavailable = unsafe_perform_io(read.failure())
        log.error(
            _UNREADABLE_EVENT,
            check_id="plan_no_live_handoff_file",
            diff_range=_DIFF_RANGE,
            reason=unavailable.reason,
            detail=unavailable.detail,
        )
        return 1
    offenders = _offending_paths(diff_output=unsafe_perform_io(read.unwrap()))
    for path in offenders:
        log.error(
            _EVENT,
            check_id="plan_no_live_handoff_file",
            path=path,
            disposition="kept",
            authority=_AUTHORITY,
            remediation=_REMEDIATION,
        )
    return 1 if offenders else 0


if __name__ == "__main__":
    raise SystemExit(main())
