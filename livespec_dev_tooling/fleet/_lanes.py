"""The vantage-lane member-row sweep shared by both fleet-conformance entry points.

Extracted from `fleet_conformance.py` (the `_ci_job_names` / `_ci_matrix_parse`
precedent) so the central lane and the admin world-gate lane run ONE sweep
implementation rather than two that can drift.

THREE outcomes, not two. A row that answers is *evaluated*. A row that does
not answer splits in two, and conflating the halves is what this module
exists to prevent:

- **Blind** — the running lane holds credentials that SHOULD have answered
  this row, and every applicable member still came back unreadable. That is
  the b02 signal: the run enforced nothing while claiming coverage. It is
  ERROR severity and fails the run — the escalation b02 recorded as the
  intended end state, shipped once the vantage model left no row
  structurally blind in any healthy context. There is no lever, env var,
  exemption list, or opt-out: a lane that owns a row it could not read
  exits non-zero, always.
- **Out-of-vantage** — no credential this lane holds could ever answer the
  row, by design, and a DIFFERENT named context owns it. Expected, so it is
  reported at info severity with the owning context attached.

Before the split, the two admin-scoped rows (`branch-protection`,
`secret-names`) were blind in every automated run — a warning no operator
could ever clear, which is precisely how a real signal gets tuned out; the
`app-installation` row was likewise blind in every LOCAL central run until
the `central-app` vantage completed the model. Filtering by vantage happens
BEFORE `assert_member` is called, so an out-of-vantage row also costs the
lane zero API reads.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

from livespec_dev_tooling.config import assert_never
from livespec_dev_tooling.fleet._context import RowFinding, RowPass, RowSkip
from livespec_dev_tooling.fleet._contract_rows import (
    ADMIN_VANTAGE,
    CENTRAL_APP_VANTAGE,
    CENTRAL_VANTAGE,
    rows_for,
)

if TYPE_CHECKING:
    import structlog.stdlib

    from livespec_dev_tooling.fleet._context import FleetContext, RowOutcome
    from livespec_dev_tooling.fleet._contract_model import ObligationRow
    from livespec_dev_tooling.fleet.contract import Manifest

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

__all__: list[str] = [
    "BLIND_ROW_EVENT",
    "LANE_RECIPES",
    "OUT_OF_VANTAGE_EVENT",
    "MemberRowsResult",
    "MemberVerdict",
    "configure_lane_logging",
    "run_member_rows",
]


BLIND_ROW_EVENT = "obligation row enforced NOTHING this run (skipped for every applicable member)"
OUT_OF_VANTAGE_EVENT = "obligation row is outside this lane's vantage (another lane owns it)"
_EXCLUDED_NOTE_PREFIX = "excluded-with-reason: "

# The invocation context that OWNS each vantage. An out-of-vantage report is
# only actionable if it names where the row does get enforced, so this map is
# the reporting half of the vantage split — keep it in step with the recipes
# and the App-token workflow contexts.
LANE_RECIPES: dict[str, str] = {
    CENTRAL_VANTAGE: "check-fleet-conformance",
    CENTRAL_APP_VANTAGE: (
        "check-fleet-conformance under the fleet GitHub App installation token "
        "(the per-PR CI job, the scheduled fleet-conformance.yml, and the "
        "release fan-out preflight)"
    ),
    ADMIN_VANTAGE: "check-fleet-conformance-admin",
}


@dataclass(frozen=True, kw_only=True)
class MemberVerdict:
    """Machine-readable conformance result for one manifest member.

    A verdict covers only the rows the RUNNING lane evaluated: a member
    `conformant` in the central lane may still fail an admin-vantage row
    in the admin lane, and vice versa — each lane reports its own vantage.
    """

    member: str
    failing_rows: tuple[str, ...]


@dataclass(frozen=True, kw_only=True)
class MemberRowsResult:
    """What one lane's member-row sweep found across the three row outcomes.

    The three counts are deliberately SEPARATE. `error_findings` and
    `blind_rows` BOTH fail the run (blind is error severity — an owned row
    that enforced nothing), but stay distinct so a violated obligation reads
    differently from an unreadable one; `out_of_vantage_rows` accounts for
    the rows this lane never attempted, so the zeroes cannot be confused for
    each other. `member_verdicts` re-cuts the SAME error-severity per-member
    findings for workflow consumers; it introduces no fourth outcome.
    """

    error_findings: int
    blind_rows: int
    out_of_vantage_rows: int
    member_verdicts: tuple[MemberVerdict, ...]


def configure_lane_logging() -> None:
    """Configure structlog for a lane CLI: JSON records to stderr."""
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )


def run_member_rows(
    *,
    ctx: FleetContext,
    manifest: Manifest,
    log: structlog.stdlib.BoundLogger,
    vantages: frozenset[str] = frozenset({CENTRAL_VANTAGE}),
) -> MemberRowsResult:
    """Assert every member's applicable rows answerable from `vantages`.

    `vantages` is the set of credential-class vantages the RUNNING lane
    holds: a local central sweep holds `central` alone, an automated one
    adds `central-app` (the fleet App installation token), and the admin
    lane holds `admin`. Rows are selected PER MEMBER via `rows_for`, so
    different rows apply to different numbers of members; the tallies below
    therefore count only the members a row actually applied to, never the
    whole membership.
    """
    # THE ROSTER JOIN. `FleetContext.members` defaults to `()` — the
    # fail-closed spelling — and every construction site builds the context
    # BEFORE the manifest resolves, on a frozen dataclass. This is the one
    # function holding both, so joining them here is what makes a FLEET-vantage
    # row (one asking "does any OTHER member do X?") answerable at all; before
    # it, such a row saw an empty roster, skipped for every member, and tripped
    # the blind-row error. `replace` rather than a fresh construction because
    # the memo caches are mutable dicts carried BY REFERENCE, so the manifest
    # resolution's API reads survive into the rows that follow.
    ctx = replace(ctx, members=tuple(manifest.members))
    errors = 0
    evaluated: dict[str, int] = {}
    skips: dict[str, list[str]] = {}
    out_of_vantage: dict[tuple[str, str], int] = {}
    failing_rows_by_member: dict[str, list[str]] = {}
    for member in manifest.members:
        failing_rows_by_member[member.repo] = []
        for row in rows_for(repo_class=member.repo_class):
            if row.vantage not in vantages:
                key = (row.row_id, row.vantage)
                out_of_vantage[key] = out_of_vantage.get(key, 0) + 1
                continue
            errors += _fold_member_outcome(
                outcome=row.assert_member(ctx=ctx, member=member),
                row=row,
                member_repo=member.repo,
                tallies=_LaneTallies(
                    evaluated=evaluated,
                    skips=skips,
                    failing_rows=failing_rows_by_member[member.repo],
                ),
                log=log,
            )
    return MemberRowsResult(
        error_findings=errors,
        blind_rows=_report_blind_rows(evaluated=evaluated, skips=skips, log=log),
        out_of_vantage_rows=_report_out_of_vantage_rows(counts=out_of_vantage, log=log),
        member_verdicts=tuple(
            MemberVerdict(member=member, failing_rows=tuple(failing_rows))
            for member, failing_rows in failing_rows_by_member.items()
        ),
    )


@dataclass(frozen=True, kw_only=True)
class _LaneTallies:
    """The three mutable accumulators one member-row fold writes into.

    Bundled because passing them individually pushed `_fold_member_outcome`
    past PLR0913's six-argument cap. The containers are mutated in place;
    `frozen` binds the dataclass fields, not the dicts and list they name.
    """

    evaluated: dict[str, int]
    skips: dict[str, list[str]]
    failing_rows: list[str]


def _fold_member_outcome(
    *,
    outcome: RowOutcome,
    row: ObligationRow,
    member_repo: str,
    tallies: _LaneTallies,
    log: structlog.stdlib.BoundLogger,
) -> int:
    """Fold ONE row outcome into the lane's tallies; return the error delta.

    Extracted when the exhaustive `match` pushed `run_member_rows` past
    PLR0915's thirty-statement cap — the cap was paid rather than routed
    around, and the extraction earns its keep: this is now the ONE place the
    central lane discriminates a `RowOutcome`, so the union's three meanings
    are read in a single function instead of three chained `isinstance`
    tests spread through a nested loop.

    ⛔ The `case _: assert_never(outcome)` terminator is the POINT, not
    ceremony. `RowOutcome` is a closed union, and a fourth variant added
    later must not fall silently through a consumer — which is exactly what
    an `isinstance` chain would let it do, because
    `check-assert-never-exhaustiveness` polices `match` statements and
    cannot see a chain at all.
    """
    match outcome:
        case RowSkip():
            # Row functions prefix their reason with the member repo; the
            # blind-row warning reports the underlying CAUSES, and the
            # member is already implied by "every applicable member".
            tallies.skips.setdefault(row.row_id, []).append(
                outcome.reason.removeprefix(f"{member_repo}: ")
            )
            log.info(
                "fleet obligation not evaluable (can't-read is not absent)",
                row=row.row_id,
                member=member_repo,
                reason=outcome.reason,
            )
            return 0
        case RowPass():
            tallies.evaluated[row.row_id] = tallies.evaluated.get(row.row_id, 0) + 1
            if outcome.note.startswith(_EXCLUDED_NOTE_PREFIX):
                log.info(
                    "fleet obligation excluded with reason",
                    row=row.row_id,
                    member=member_repo,
                    reason=outcome.note.removeprefix(_EXCLUDED_NOTE_PREFIX),
                )
            return 0
        case RowFinding():
            tallies.evaluated[row.row_id] = tallies.evaluated.get(row.row_id, 0) + 1
            if outcome.severity == "warning":
                log.warning(
                    "fleet obligation warning",
                    row=row.row_id,
                    member=member_repo,
                    detail=outcome.message,
                )
                return 0
            tallies.failing_rows.append(row.row_id)
            log.error(
                "fleet obligation violated",
                row=row.row_id,
                member=member_repo,
                detail=outcome.message,
                hint=row.manual_hint or "run wire-fleet-member to reconcile",
            )
            return 1
        case _:
            assert_never(outcome)


def _report_blind_rows(
    *,
    evaluated: dict[str, int],
    skips: dict[str, list[str]],
    log: structlog.stdlib.BoundLogger,
) -> int:
    """Report an ERROR for each row evaluable on NO applicable member; count them.

    A row present in `skips` but absent from `evaluated` applied to at least
    one member and answered for none of them, so it enforced nothing this
    run — the lane owns the row and could not read its source, which fails
    the run rather than passing vacuously. `applicable` equals the skip
    count by construction — zero members were evaluated — and both are
    reported so the reader need not infer it.
    """
    blind = 0
    for row_id, reasons in skips.items():
        if evaluated.get(row_id, 0):
            continue
        blind += 1
        log.error(
            BLIND_ROW_EVENT,
            row=row_id,
            applicable=len(reasons),
            skipped=len(reasons),
            reasons=tuple(dict.fromkeys(reasons)),
        )
    return blind


def _report_out_of_vantage_rows(
    *,
    counts: dict[tuple[str, str], int],
    log: structlog.stdlib.BoundLogger,
) -> int:
    """Report each row this lane structurally cannot answer; return how many.

    Info severity, not warning: this is the DESIGNED partition, not a defect.
    `owned_by` names the lane that does enforce the row, so the reader can
    verify coverage rather than assume it. An unregistered vantage is named
    rather than silently dropped — a row whose lane nobody runs is exactly
    the zero-enforcement hole this split was built to close.
    """
    for (row_id, row_vantage), applicable in counts.items():
        log.info(
            OUT_OF_VANTAGE_EVENT,
            row=row_id,
            applicable=applicable,
            vantage=row_vantage,
            owned_by=LANE_RECIPES.get(row_vantage, "(no lane runs this vantage)"),
        )
    return len(counts)
