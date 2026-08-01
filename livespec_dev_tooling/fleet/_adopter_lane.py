"""The posture-gated adopter currency leg of the fleet-conformance sweep.

livespec `non-functional-requirements.md` §"Plugin currency and the
release train": "the fleet-conformance sweep iterates fleet members plus
opt-in adopters, and does NOT hold to currency any repo whose `posture`
is not `released`". This module is the manifest `adopters` array's
consumer — previously the array was parsed into typed records that
nothing read, so `posture` was inert (livespec-dev-tooling-453).

Scope is deliberately NARROW, per the same spec's Adopters rule:
adopters carry NO per-class obligations (the Obligations-per-repo-class
rule binds the `fleet` array only), so the leg runs exactly ONE row —
`claude-plugin-currency` — and reads neither `profile` nor anything the
obligation table derives from a repo class.

The leg's vantage is ADMIN (the world-gate lane,
`check-fleet-conformance-admin`): every automated central-lane context
holds a fleet GitHub App installation token, and the fleet App's
installation MUST be restricted to fleet repos only (livespec
non-functional-requirements.md), so a private released adopter is
structurally unreadable there — a central-lane leg could only ever
skip, reading as coverage while enforcing nothing. The central lane
instead reports the leg out-of-vantage naming the owning recipe,
exactly as it reports the two admin-scoped member rows.

Three adopter outcome categories, extending the `_lanes` split:

- **Evaluated** — a `released` adopter the lane could read. Findings
  are error-severity with no warning demotion path on this leg
  (maintainer decision 2026-07-20: adopter findings fail loud).
- **Blind** — every released adopter was unreadable in the lane that
  OWNS the leg. `blind_rows` is 1 only when NO released adopter
  answered: a run that read even one treats the remainder as ordinary
  skips, the same rule `_lanes._report_blind_rows` applies to a member
  row ("applied to at least one member and answered for none of them").
  ⛔ IT MOVES THE EXIT CODE, and an earlier revision of this docstring
  said the opposite. Both supervisors sum this count with the member
  sweep's (`result.blind_rows + adopters.blind_rows`) and fail the run
  on the total; `test_admin_lane_fails_when_a_released_adopter_is_unreadable`
  pins that at exit 4. The b02 signal is the SAME as member rows here —
  blind fails rather than passing vacuously. ⚠️ What actually diverges
  from member rows is the LOG record: this leg emits `BLIND_ROW_EVENT`
  at warning severity while `_lanes` emits it at error, so an
  identically-fatal outcome is recorded one level quieter here. The two
  halves of the retracted claim were swapped — the exit-code effect is
  what matches, the severity is what differs.
- **Posture-excluded** — a declared non-`released` posture, honored by
  never reading the repo at all (the spec's "never 'helpfully'
  updated"). Reported at info severity as its own labeled category,
  mirroring out-of-vantage reporting: neither evaluated nor blind, and
  never silently invisible.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from livespec_dev_tooling.config import assert_never
from livespec_dev_tooling.fleet._context import FleetMember, RowFinding, RowPass, RowSkip
from livespec_dev_tooling.fleet._contract_rows import ADMIN_VANTAGE, CENTRAL_VANTAGE
from livespec_dev_tooling.fleet._lanes import (
    BLIND_ROW_EVENT,
    LANE_RECIPES,
    OUT_OF_VANTAGE_EVENT,
)
from livespec_dev_tooling.fleet._rows_claude_plugin import assert_claude_plugin_currency

if TYPE_CHECKING:
    import structlog.stdlib

    from livespec_dev_tooling.fleet._context import Adopter, FleetContext
    from livespec_dev_tooling.fleet.contract import Manifest

__all__: list[str] = [
    "ADOPTER_CURRENCY_ROW_ID",
    "POSTURE_EXCLUDED_EVENT",
    "RELEASED_POSTURE",
    "AdopterRowsResult",
    "run_adopter_rows",
]


# The one row the adopter leg runs, labeled distinctly from the member
# `claude-plugin-currency` row so the two never share blind or
# out-of-vantage accounting: the member row is CENTRAL-vantage while
# this leg is ADMIN-vantage, and a tally keyed on one id would let a
# skipping adopter hide behind an answering member (or vice versa).
ADOPTER_CURRENCY_ROW_ID = "adopter-claude-plugin-currency"
# The only posture the leg holds to currency. Every other posture is a
# declared choice the sweep honors by not reading the repo at all.
RELEASED_POSTURE = "released"
POSTURE_EXCLUDED_EVENT = "adopter excluded by posture (declared choice honored, not evaluated)"

_ADOPTER_CURRENCY_HINT = (
    "END-USER work in the adopter repo (livespec .ai/adding-an-adopter.md): wire "
    ".claude/settings.json SessionStart to `mise exec -- just ensure-plugins`, or "
    "declare livespecPluginCurrencySuccessor with mechanism + documentedIn"
)


@dataclass(frozen=True, kw_only=True)
class AdopterRowsResult:
    """What the adopter currency leg found across its outcome categories.

    `error_findings` alone may move an exit code. `blind_rows` is 1 when
    the owning lane could read NO released adopter and 0 otherwise (the
    leg is a single row, mirroring the member sweep's per-row blind
    tally). `out_of_vantage_rows` is 1 in a lane that does not own the
    leg while released adopters exist. `evaluated` counts the released
    adopters that answered. `posture_excluded` NAMES the adopters
    honored by exclusion, so a green run states its exclusions instead
    of implying them.
    """

    error_findings: int
    blind_rows: int
    out_of_vantage_rows: int
    evaluated: int
    posture_excluded: tuple[str, ...]


def _currency_member(*, adopter: Adopter) -> FleetMember:
    """Adapt an `Adopter` to the row-function seam.

    Row functions take a `FleetMember`; `assert_claude_plugin_currency`
    reads only `.repo`. The adapted value is built at this one call site
    and never enters `rows_for`, so the placeholder class string selects
    no obligation row anywhere — adopters have no repo class by design.
    """
    return FleetMember(repo=adopter.repo, repo_class="adopter")


def run_adopter_rows(
    *,
    ctx: FleetContext,
    manifest: Manifest,
    log: structlog.stdlib.BoundLogger,
    vantage: str = CENTRAL_VANTAGE,
) -> AdopterRowsResult:
    """Assert the currency row over `manifest.adopters`, honoring posture.

    Posture gates the iteration itself: a non-`released` adopter is
    never read — exclusion is the honored behavior, not a tolerated
    skip. In a lane other than the leg's own ADMIN vantage the leg costs
    zero API reads and reports itself out-of-vantage naming the owning
    recipe; the posture partition is likewise reported only by the
    owning lane, whose report carries the leg's full accounting.
    """
    released = tuple(a for a in manifest.adopters if a.posture == RELEASED_POSTURE)
    excluded = tuple(a for a in manifest.adopters if a.posture != RELEASED_POSTURE)
    excluded_names = tuple(adopter.repo for adopter in excluded)
    if vantage != ADMIN_VANTAGE:
        if released:
            log.info(
                OUT_OF_VANTAGE_EVENT,
                row=ADOPTER_CURRENCY_ROW_ID,
                applicable=len(released),
                vantage=ADMIN_VANTAGE,
                owned_by=LANE_RECIPES[ADMIN_VANTAGE],
            )
        return AdopterRowsResult(
            error_findings=0,
            blind_rows=0,
            out_of_vantage_rows=1 if released else 0,
            evaluated=0,
            posture_excluded=excluded_names,
        )
    for adopter in excluded:
        log.info(
            POSTURE_EXCLUDED_EVENT,
            row=ADOPTER_CURRENCY_ROW_ID,
            adopter=adopter.repo,
            posture=adopter.posture,
        )
    errors = 0
    evaluated = 0
    skip_reasons: list[str] = []
    for adopter in released:
        outcome = assert_claude_plugin_currency(ctx=ctx, member=_currency_member(adopter=adopter))
        match outcome:
            case RowSkip():
                skip_reasons.append(outcome.reason.removeprefix(f"{adopter.repo}: "))
                log.info(
                    "fleet obligation not evaluable (can't-read is not absent)",
                    row=ADOPTER_CURRENCY_ROW_ID,
                    member=adopter.repo,
                    reason=outcome.reason,
                )
            case RowPass():
                evaluated += 1
            case RowFinding():
                evaluated += 1
                errors += 1
                log.error(
                    "fleet obligation violated",
                    row=ADOPTER_CURRENCY_ROW_ID,
                    member=adopter.repo,
                    detail=outcome.message,
                    hint=_ADOPTER_CURRENCY_HINT,
                )
            case _:
                assert_never(outcome)
    blind = 0
    if skip_reasons and not evaluated:
        blind = 1
        log.warning(
            BLIND_ROW_EVENT,
            row=ADOPTER_CURRENCY_ROW_ID,
            applicable=len(skip_reasons),
            skipped=len(skip_reasons),
            reasons=tuple(dict.fromkeys(skip_reasons)),
        )
    return AdopterRowsResult(
        error_findings=errors,
        blind_rows=blind,
        out_of_vantage_rows=0,
        evaluated=evaluated,
        posture_excluded=excluded_names,
    )
