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

THE ROW ALSO CARRIES ONE CONTENT PREDICATE, and the headings are otherwise
asserted only as headings. The `## Repository mutation protocol` section must
name `just worktree-create` — the recipe that adds the worktree under the
per-user root AND provisions the gitignored worktree-discipline pack into it
AND runs the hydrate hook. Surveyed 2026-09-06, seventeen `AGENTS.md` /
`CLAUDE.md` files across ten repos prescribed a raw `git worktree add -b` and
NONE named the recipe: the guidance is hand-ported per repo, so it drifted the
way hand-ported guidance always does. With heal-at-gate the raw form is merely
WORSE rather than unsafe, so the predicate's job is "prefer the recipe" — which
is why it is one phrase and not a prose judgment.

IT SHIPS AT WARNING SEVERITY, DELIBERATELY. At authoring time the offender
count was TEN of ten; an error-severity finding would have redded the central
sweep fleet-wide the moment it merged. That is the `46c5dab` shape —
`plan/rop-railway-enforcement/` carries the standing constraint "Do not arm the
check anywhere" because arming the Railway decoupling ahead of adoption turned
five repos red and had to be reverted in `f4247110`. Adoption first, then
arming: flipping this leg to error severity is a separate, later commit, taken
once the offender count has been re-measured at zero, exactly as the sibling
`_rows_decision_authority` row was armed.

`WORKTREE_CREATE_SENTENCE` is the fleet-universal core text members port, and
it lives HERE beside the predicate that demands it. The finding quotes it, the
manual hint `wire_fleet_member` prints quotes it, and the row's own test
fixture is BUILT from it — one string rather than four copies free to drift.
"""

from __future__ import annotations

import posixpath

from livespec_dev_tooling.checks._ai_references import (
    AGENTS_FILENAME,
    is_excluded_agents_path,
    iter_ai_references,
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
    "AGENTS_PATH",
    "AGENT_INSTRUCTION_SURFACE_HINT",
    "MUTATION_PROTOCOL_HEADING",
    "REQUIRED_AGENTS_HEADINGS",
    "SETTINGS_PATH",
    "WORKTREE_CREATE_COMMAND",
    "WORKTREE_CREATE_SENTENCE",
    "assert_agent_ai_references_resolve",
    "assert_agent_instruction_surface",
    "mutation_protocol_section",
]

AGENTS_PATH = "AGENTS.md"
SETTINGS_PATH = ".claude/settings.json"
_GUARD_MARKER = "beads-access-guard"

MUTATION_PROTOCOL_HEADING = "## Repository mutation protocol"

# The fleet-universal agent-instruction core H2 headings every impl-plugin
# member's AGENTS.md must carry (substring-matched, so a heading with a
# trailing suffix still satisfies its bare prefix).
REQUIRED_AGENTS_HEADINGS: tuple[str, ...] = (
    MUTATION_PROTOCOL_HEADING,
    "## Agent prerequisites for plugin work",
    "## Beads runtime prerequisites",
    "## Daily commands",
    "## Revise co-edit discipline",
)

# The ONE phrase the mutation-protocol section must name. A phrase rather than
# the whole sentence below: the predicate judges no prose, only that a session
# reading the section it follows to create a worktree MEETS the recipe there.
WORKTREE_CREATE_COMMAND = "just worktree-create"

# The fleet-universal core text members port, homed beside the predicate that
# demands it. BUILT FROM `WORKTREE_CREATE_COMMAND` rather than restating it, so
# the sentence the row quotes always satisfies the phrase the row greps for —
# the row's own fixture is built from this same constant for the same reason.
WORKTREE_CREATE_SENTENCE = (
    "Create it with the worktree-discipline pack's recipe, which adds the worktree "
    "under that root, provisions the gitignored pack into it, and runs the hydrate "
    f"hook (run it from the primary checkout): `mise exec -- {WORKTREE_CREATE_COMMAND} <branch>`."
)

# `wire_fleet_member`'s operator hint for this row. It QUOTES the sentence
# rather than describing it, so an operator reading the hint has the text to
# paste and never has to go find the canonical wording.
AGENT_INSTRUCTION_SURFACE_HINT = (
    "bring AGENTS.md up to the fleet-universal agent-instruction core and register the "
    "beads-access guard hook (.claude/hooks/beads-access-guard.sh) in .claude/settings.json, "
    "in a repo-local commit; the mutation-protocol section must name the worktree recipe — "
    f"{WORKTREE_CREATE_SENTENCE}"
)

_H2_PREFIX = "## "


def mutation_protocol_section(*, agents_text: str) -> str:
    """The body of `agents_text`'s `## Repository mutation protocol` section.

    Empty when the heading is absent, and empty when the section carries no
    body — the two are not distinguished because the caller treats them
    identically. The slice runs from the heading to the next H2, or to end of
    file when the section is last.

    SCOPING TO THE SECTION IS THE POINT. A member that names the worktree
    recipe under `## Daily commands` has put it somewhere a session creating a
    worktree does not read; guidance is only guidance where it is met.

    The heading is matched by PREFIX, mirroring how `REQUIRED_AGENTS_HEADINGS`
    is substring-matched, so a member that suffixes the heading still carries
    the section.
    """
    body: list[str] = []
    inside = False
    for line in agents_text.splitlines():
        if line.startswith(_H2_PREFIX):
            if inside:
                break
            inside = line.startswith(MUTATION_PROTOCOL_HEADING)
            continue
        if inside:
            body.append(line)
    return "\n".join(body)


def assert_agent_instruction_surface(*, ctx: FleetContext, member: FleetMember) -> RowOutcome:
    """The member carries the universal agent-instruction core + beads-access guard.

    Skips a member whose `AGENTS.md` or `.claude/settings.json` is
    unreadable (can't-read is not absent). A finding names every missing
    universal-core heading and, when the beads-access guard is not
    registered in `.claude/settings.json`, the missing guard.

    A member whose surface is structurally complete is then checked for the
    ONE content predicate: its mutation-protocol section must name the
    worktree-creation recipe. That leg is reported at WARNING severity and
    reported SECOND — a structurally absent section is the more serious
    defect, and reporting the recipe first would downgrade it to a warning.
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
    if WORKTREE_CREATE_COMMAND not in mutation_protocol_section(agents_text=agents):
        return RowFinding(
            message=(
                f"{member.repo}: {AGENTS_PATH} {MUTATION_PROTOCOL_HEADING} does not name "
                f"`{WORKTREE_CREATE_COMMAND}` — port the fleet-universal sentence verbatim: "
                f"{WORKTREE_CREATE_SENTENCE}"
            ),
            severity="warning",
        )
    return RowPass()


def assert_agent_ai_references_resolve(*, ctx: FleetContext, member: FleetMember) -> RowOutcome:
    """Every `.ai/<topic>.md` an `AGENTS.md` references resolves to a tree file.

    Reads the member's recursive canonical-ref tree, enumerates every
    `AGENTS.md` at any directory level (excluding vendored/generated/
    archival trees via `is_excluded_agents_path`), and resolves each
    concrete `.ai/<topic>.md` reference relative to that file's own
    directory against the tree's path set. A reference that resolves to
    no tree path is a finding (instruction-surface drift is un-mergeable).

    Per the fleet's can't-read-is-not-absent discipline: an unreadable
    or truncated tree skips (a truncated tree cannot prove a `.ai/`
    target absent), and an `AGENTS.md` whose content is unreadable is
    itself skipped — never a false finding.
    """
    tree = ctx.tree(repo=member.repo)
    if not tree.readable:
        ref = ctx.canonical_ref(repo=member.repo)
        return RowSkip(reason=f"{member.repo}: {ref} tree unreadable")
    if tree.truncated:
        return RowSkip(
            reason=f"{member.repo}: tree truncated; .ai/ reference absence not definitive"
        )
    agents_paths = sorted(
        p
        for p in tree.paths
        if p.rsplit("/", 1)[-1] == AGENTS_FILENAME
        and not is_excluded_agents_path(segments=tuple(p.split("/")))
    )
    for ap in agents_paths:
        text = ctx.file_text(repo=member.repo, path=ap)
        if text is None:
            continue
        dir_prefix = ap.rsplit("/", 1)[0] if "/" in ap else ""
        for line, ref in iter_ai_references(text=text):
            resolved = posixpath.normpath(posixpath.join(dir_prefix, ref))
            if resolved not in tree.paths:
                return RowFinding(
                    message=(
                        f"{member.repo}: {ap}:{line} references {ref} which does not "
                        f"resolve to an existing file (expected {resolved})"
                    )
                )
    return RowPass()
