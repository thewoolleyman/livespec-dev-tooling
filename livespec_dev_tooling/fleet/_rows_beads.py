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

from livespec_dev_tooling.fleet._connection import (
    BEADS_CONFIG_PATH,
    CONNECTION_FIELD_PAIRS,
    LIVESPEC_JSONC_PATH,
    connection_block,
    mismatched_keys,
    parse_beads_config,
)
from livespec_dev_tooling.fleet._context import (
    FleetContext,
    FleetMember,
    RowFinding,
    RowOutcome,
    RowPass,
    RowSkip,
)

__all__: list[str] = [
    "BEADS_CONFIG_PATH",
    "CONNECTION_FIELD_PAIRS",
    "LIVESPEC_JSONC_PATH",
    "assert_tenant_connection_consistency",
]


def assert_tenant_connection_consistency(*, ctx: FleetContext, member: FleetMember) -> RowOutcome:
    """The member's `.beads/config.yaml` and `.livespec.jsonc` connection agree.

    Skips a member lacking either file, lacking a `.livespec.jsonc`
    connection block, or whose `.beads/config.yaml` carries none of the
    `dolt.*` connection keys (not beads-backed / can't-read is not
    absent). Findings name every mismatched key.
    """
    beads_text = ctx.file_text(repo=member.repo, path=BEADS_CONFIG_PATH)
    if beads_text is None:
        return RowSkip(reason=f"{member.repo}: {BEADS_CONFIG_PATH} unreadable or absent")
    jsonc_text = ctx.file_text(repo=member.repo, path=LIVESPEC_JSONC_PATH)
    if jsonc_text is None:
        return RowSkip(reason=f"{member.repo}: {LIVESPEC_JSONC_PATH} unreadable or absent")
    beads = parse_beads_config(text=beads_text)
    if not any(beads_key in beads for beads_key, _ in CONNECTION_FIELD_PAIRS):
        return RowSkip(
            reason=f"{member.repo}: {BEADS_CONFIG_PATH} carries no dolt.* connection keys"
        )
    connection = connection_block(text=jsonc_text)
    if connection is None:
        return RowSkip(
            reason=f"{member.repo}: {LIVESPEC_JSONC_PATH} carries no impl-plugin connection block"
        )
    mismatched = mismatched_keys(beads=beads, connection=connection)
    if mismatched:
        return RowFinding(
            message=(
                f"{member.repo}: tenant connection drift between {BEADS_CONFIG_PATH} and "
                f"{LIVESPEC_JSONC_PATH} on key(s): {', '.join(mismatched)}"
            )
        )
    return RowPass()
