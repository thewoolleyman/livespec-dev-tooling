"""Beads tenant-connection obligation row for the fleet-membership contract.

A beads-backed member duplicates its per-repo Dolt tenant connection in
TWO committed files: `.beads/config.yaml` (read by the `bd` CLI; flat
dotted keys `dolt.server-host`, `dolt.server-port`, `dolt.server-user`,
`dolt.database`, `dolt.prefix`) AND `.livespec.jsonc`'s impl-plugin
`connection` block (read by the plugin; keys `server_host`,
`server_port`, `server_user`, `database`, `prefix`). The two are
authored independently, so they can silently drift (they did during the
orchestrator rename). This row asserts the five pairs agree from the
central fleet vantage point, making any drift un-mergeable.

Per the fleet contract's can't-read-is-not-absent discipline: a member
that lacks either file, or whose `.livespec.jsonc` carries no
`connection` block, is not beads-backed (or not yet wired) and yields a
skip — never a false red. Only a member with BOTH connection sources
present and a definite disagreement yields a finding.

The parse/lookup/compare primitives this row shares with the LOCAL
`reconcile_livespec_jsonc_complete` row (`_rows_local_jsonc`) live in the
sibling `_connection` module as PUBLIC names — imported here directly so
neither row reaches across a module for a `_`-prefixed helper.
"""

from __future__ import annotations

import sys
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.result import Failure, Result, Success  # noqa: E402  — vendor-path-aware import.

from livespec_dev_tooling.fleet._connection import (  # noqa: E402
    BEADS_CONFIG_PATH,
    CONNECTION_FIELD_PAIRS,
    LIVESPEC_JSONC_PATH,
    connection_block,
    mismatched_keys,
    parse_beads_config,
)
from livespec_dev_tooling.fleet._context import (  # noqa: E402
    FleetContext,
    FleetMember,
    RowFinding,
    RowOutcome,
    RowPass,
    RowSkip,
    row_excluded,
)

__all__: list[str] = [
    "BEADS_CONFIG_PATH",
    "CONNECTION_FIELD_PAIRS",
    "LIVESPEC_JSONC_PATH",
    "assert_tenant_connection_consistency",
]


def _member_connection(
    *, member: FleetMember, jsonc_text: str
) -> Result[dict[str, object], RowOutcome]:
    """The member's connection block, or the outcome its defect or absence earns.

    ⛔ The failure track is `RowOutcome`, not `RowSkip`, and the widening is
    the POINT rather than a concession: the two non-success answers here are
    NOT the same kind. A document that will not PARSE is a can't-read and stays
    a skip; a document that parses and definitively carries no connection block
    is INAPPLICABLE and is an excluded pass. Annotating this `RowSkip` is what
    let the two be written as one thing.

    Split out to keep `assert_tenant_connection_consistency` at the
    six-return cap: the conversion added a branch, which is the structural
    cost every conversion in this epic pays somewhere.

    SEVERITY IS UNCHANGED — an unusable document was a skip before the
    conversion and stays one. Only the REASON changes, from "carries no
    impl-plugin connection block" (a statement about the member's config
    that the row never verified) to one naming the defect. v039's ratified
    "a can't-PARSE is NEVER a pass" is scoped to pin-currency rows
    (`contracts.md` §"Pin-currency severity policy"); generalizing it to
    this row is a ratification, not a conversion.
    """
    block = connection_block(text=jsonc_text)
    if isinstance(block, Failure):
        return Failure(
            RowSkip(
                reason=(
                    f"{member.repo}: {LIVESPEC_JSONC_PATH} is not a usable JSONC object map "
                    f"({block.failure().detail})"
                )
            )
        )
    connection = block.unwrap()
    if connection is None:
        # INAPPLICABLE, not unevaluable: the document was READ and definitively
        # carries no connection block, so this member has no obligation here.
        return Failure(
            row_excluded(
                reason=(
                    f"{member.repo}: {LIVESPEC_JSONC_PATH} carries no impl-plugin connection block"
                )
            )
        )
    return Success(connection)


def assert_tenant_connection_consistency(*, ctx: FleetContext, member: FleetMember) -> RowOutcome:
    """The member's `.beads/config.yaml` and `.livespec.jsonc` connection agree.

    TWO OUTCOMES FOR TWO DIFFERENT THINGS, and conflating them is what
    livespec-dev-tooling-8o8e.2 fixed. SKIPS only when a source could not be
    READ — an unreadable `.beads/config.yaml` or `.livespec.jsonc`, or a
    document that will not parse — which is what feeds `blind_rows`. EXCLUDES
    (a pass carrying the excluded-with-reason note) when the sources were read
    and the row simply does not APPLY: no `dolt.*` connection keys, so the
    member is not beads-backed, or no impl-plugin connection block. Findings
    name every mismatched key.
    """
    beads_text = ctx.file_text(repo=member.repo, path=BEADS_CONFIG_PATH)
    if beads_text is None:
        return RowSkip(reason=f"{member.repo}: {BEADS_CONFIG_PATH} unreadable or absent")
    jsonc_text = ctx.file_text(repo=member.repo, path=LIVESPEC_JSONC_PATH)
    if jsonc_text is None:
        return RowSkip(reason=f"{member.repo}: {LIVESPEC_JSONC_PATH} unreadable or absent")
    beads = parse_beads_config(text=beads_text)
    if not any(beads_key in beads for beads_key, _ in CONNECTION_FIELD_PAIRS):
        # INAPPLICABLE: the config was READ and names no dolt.* keys, so this
        # member is not beads-backed and owes this row nothing. A RowSkip here
        # would feed blind_rows and red master fleet-wide the moment the
        # beads-backed population reaches zero.
        return row_excluded(
            reason=f"{member.repo}: {BEADS_CONFIG_PATH} carries no dolt.* connection keys"
        )
    resolved = _member_connection(member=member, jsonc_text=jsonc_text)
    if isinstance(resolved, Failure):
        return resolved.failure()
    mismatched = mismatched_keys(beads=beads, connection=resolved.unwrap())
    if mismatched:
        return RowFinding(
            message=(
                f"{member.repo}: tenant connection drift between {BEADS_CONFIG_PATH} and "
                f"{LIVESPEC_JSONC_PATH} on key(s): {', '.join(mismatched)}"
            )
        )
    return RowPass()
