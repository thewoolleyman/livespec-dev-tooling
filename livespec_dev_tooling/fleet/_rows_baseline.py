"""Baseline `harnesses`-declaration obligation row for the fleet contract.

The Conformance Pattern's cross-harness plugin-resolution concern
(concern #2) requires every governed repo to DECLARE its agent-runtime
harnesses in `.livespec.jsonc` under a top-level `harnesses` object —
each harness marked `supported` (with a `canonical_command`) or `exempt`
(with a `reason`). The per-repo `check-plugin-resolution` Verifier reads
that declaration at commit time; this fleet-time row reports, from the
central vantage point, whether a member carries the declaration at all,
so an un-backfilled member is surfaced across the whole fleet.

Reports at WARNING severity by contract: while the fleet backfill is in
flight an absent declaration must log without failing the
fleet-conformance sweep / the release fan-out preflight (both gate on
error-severity findings only). The required-key flip — absent declaration
to error severity, once every governed repo declares `harnesses` — is the
M6-g milestone, not this row.

Per the fleet contract's can't-read-is-not-absent discipline, a member
whose `.livespec.jsonc` is unreadable, unparseable, or not a JSON object
yields a skip rather than a false finding. `.livespec.jsonc` is parsed
with the vendored `jsoncomment`, mirroring `_rows_beads` and `contract`.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import cast

from livespec_dev_tooling.fleet._context import (
    FleetContext,
    FleetMember,
    RowFinding,
    RowOutcome,
    RowPass,
    RowSkip,
)

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import jsoncomment  # noqa: E402  — vendor-path-aware import after sys.path insert.

__all__: list[str] = [
    "LIVESPEC_JSONC_PATH",
    "assert_baseline_harnesses",
]


LIVESPEC_JSONC_PATH = ".livespec.jsonc"


def assert_baseline_harnesses(*, ctx: FleetContext, member: FleetMember) -> RowOutcome:
    """The member declares a non-empty `harnesses` object in `.livespec.jsonc`.

    Skips a member whose `.livespec.jsonc` is unreadable, unparseable, or
    not a JSON object (can't-read is not absent). A readable document
    carrying a non-empty top-level `harnesses` object passes; one missing
    it yields a WARNING-severity finding (the backfill is in flight; the
    M6-g flip raises it to error once every governed repo declares it).
    """
    text = ctx.file_text(repo=member.repo, path=LIVESPEC_JSONC_PATH)
    if text is None:
        return RowSkip(reason=f"{member.repo}: {LIVESPEC_JSONC_PATH} unreadable or absent")
    try:
        raw = cast("object", jsoncomment.loads(text))
    except ValueError:
        return RowSkip(reason=f"{member.repo}: {LIVESPEC_JSONC_PATH} is not valid JSONC")
    if not isinstance(raw, dict):
        return RowSkip(reason=f"{member.repo}: {LIVESPEC_JSONC_PATH} root is not a JSON object")
    harnesses = cast("dict[str, object]", raw).get("harnesses")
    if isinstance(harnesses, dict) and harnesses:
        return RowPass()
    return RowFinding(
        message=(
            f"{member.repo}: {LIVESPEC_JSONC_PATH} declares no `harnesses` object "
            "(Conformance Pattern concern #2 baseline backfill; zs22.7.7 M6)"
        ),
        severity="warning",
    )
