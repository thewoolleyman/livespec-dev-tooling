"""_pin_walk_failure — render the pin walk's two failure arms.

Split out of `_rows_pin_currency` to keep that file under the 250-LLOC
hard ceiling — the same private-sibling split as `_ci_matrix_parse` and
`_heading_coverage_tier_resolution`. The leading underscore marks it a
private sibling: it is neither a canonical check slug nor a
mirror-paired module, and its behavior is covered through its caller.
"""

from __future__ import annotations

import sys
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from livespec_dev_tooling.cross_repo.pin_autodiscovery import (  # noqa: E402
    PinFileUnparseable,
    PinWalkFailure,
)
from livespec_dev_tooling.fleet._context import (  # noqa: E402
    FleetContext,
    FleetMember,
    RowFinding,
    RowOutcome,
    RowSkip,
)

__all__: list[str] = ["walk_failure_outcome"]


def walk_failure_outcome(
    *,
    ctx: FleetContext,
    member: FleetMember,
    pin_format: str,
    failure: PinWalkFailure,
) -> RowOutcome:
    """Render the walk's two failure arms, which do NOT render the same way.

    Per `SPECIFICATION/contracts.md` section "Pin-currency severity policy" (v039):

    - A can't-READ SKIPS rather than passing or failing — "a can't-read is
      not a violation" (livespec-dev-tooling-6ge). It may be environmental
      and may not reproduce. The skip is not free: if every applicable
      member skips, the row is BLIND, which this repo already treats as
      error severity.
    - A can't-PARSE is a FINDING and NEVER a pass. It is a definitive,
      reproducible property of the member's committed bytes, so the
      per-member remedy is "fix your file" and the fan-out should exclude
      that member BY NAME rather than dispatch to it blindly. Context
      scoping is identical to the staleness classes — error only where a
      per-member remedy can be applied.

    Before this conversion an unparseable pin file did not reach here at
    all: it arrived as an in-band record with `pin_format="unrecognized"`,
    `_records_for`'s filter dropped it, zero records reached the staleness
    comparison, and "no stale pins" rendered as `RowPass()`
    (livespec-dev-tooling-2j2l).
    """
    if isinstance(failure, PinFileUnparseable):
        return RowFinding(
            message=(
                f"{member.repo}: {pin_format} pin file could not be PARSED "
                f"(a definitive property of committed bytes, not a transient read failure): "
                f"{failure.file_path} ({failure.detail})"
            ),
            severity="error" if ctx.filter_consuming_preflight else "warning",
        )
    return RowSkip(
        reason=(
            f"{pin_format} pins unreadable in {member.repo}: "
            f"{failure.file_path} ({failure.detail})"
        )
    )
