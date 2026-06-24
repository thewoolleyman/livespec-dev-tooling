"""Agent-instruction-surface obligation row for the fleet-membership contract.

Every impl-plugin fleet member MUST carry the fleet-universal
agent-instruction core in its `AGENTS.md` and register the beads-access
guard hook in `.claude/settings.json`, per `livespec`'s contract section
"Fleet agent-instruction core". This row asserts both from the central
fleet vantage point (the member's committed `AGENTS.md` and
`.claude/settings.json`), making instruction-surface drift un-mergeable —
mirroring the sibling `_rows_beads` tenant-connection consistency row.

Per the fleet's can't-read-is-not-absent discipline, a member whose
`AGENTS.md` or `.claude/settings.json` is unreadable yields a skip, never
a false finding. A finding names every missing universal-core heading and,
when absent, the unregistered beads-access guard hook.
"""

from __future__ import annotations

from livespec_dev_tooling.fleet._context import (
    FleetContext,
    FleetMember,
    RowFinding,
    RowOutcome,
    RowPass,
    RowSkip,
)

__all__: list[str] = [
    "AGENTS_PATH",
    "REQUIRED_AGENTS_HEADINGS",
    "SETTINGS_PATH",
    "assert_agent_instruction_surface",
]

AGENTS_PATH = "AGENTS.md"
SETTINGS_PATH = ".claude/settings.json"
_GUARD_MARKER = "beads-access-guard"

# The fleet-universal agent-instruction core H2 headings every impl-plugin
# member's AGENTS.md must carry (substring-matched, so a heading with a
# trailing suffix still satisfies its bare prefix).
REQUIRED_AGENTS_HEADINGS: tuple[str, ...] = (
    "## Repository mutation protocol",
    "## Agent prerequisites for plugin work",
    "## Beads runtime prerequisites",
    "## Daily commands",
    "## Revise co-edit discipline",
)


def assert_agent_instruction_surface(*, ctx: FleetContext, member: FleetMember) -> RowOutcome:
    """The member carries the universal agent-instruction core + beads-access guard.

    Skips a member whose `AGENTS.md` or `.claude/settings.json` is
    unreadable (can't-read is not absent). A finding names every missing
    universal-core heading and, when the beads-access guard is not
    registered in `.claude/settings.json`, the missing guard.
    """
    agents = ctx.file_text(repo=member.repo, path=AGENTS_PATH)
    if agents is None:
        return RowSkip(reason=f"{member.repo}: {AGENTS_PATH} unreadable or absent")
    settings = ctx.file_text(repo=member.repo, path=SETTINGS_PATH)
    if settings is None:
        return RowSkip(reason=f"{member.repo}: {SETTINGS_PATH} unreadable or absent")
    missing = [heading for heading in REQUIRED_AGENTS_HEADINGS if heading not in agents]
    if _GUARD_MARKER not in settings:
        missing.append(f"{_GUARD_MARKER} hook registration in {SETTINGS_PATH}")
    if missing:
        return RowFinding(
            message=(
                f"{member.repo}: agent-instruction surface incomplete — missing "
                f"{', '.join(missing)}"
            )
        )
    return RowPass()
