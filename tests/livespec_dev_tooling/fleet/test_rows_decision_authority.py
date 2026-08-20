"""Canned-context tests for the decision-authority AGENTS.md fleet row.

Exercises `assert_decision_authority_section` against a canned-response
`FleetContext` (no network, no real `gh`), mirroring the sibling
`test_rows_instructions` pattern.

BOTH DIRECTIONS ARE CONTROLLED HERE, and the fixtures are committed so the
control runs in CI rather than by hand: `_ADOPTED_AGENTS` is a repo that
carries the section and MUST pass, `_BARE_AGENTS` is one that does not and
MUST produce a finding naming the repo.

Two of the fixtures exist because the row was measured wrong before it was
written. A literal byte-for-byte presence test scored ALL TEN governed members
as offenders on 2026-08-20 — including `livespec-dev-tooling`, the repo that
authored the guidance — for two reasons incidental to whether the prose is
there: the canonical heading lowercases "when to ask" because the marker sits
mid-sentence after a dash, and a hard-wrapped citation splits a marker across
a newline. `_LOWERCASE_HEADING_AGENTS` and `_WRAPPED_MARKER_AGENTS` pin the
two normalizations that fix it, so a later tightening back to a literal match
fails here rather than in the fleet.
"""

from __future__ import annotations

from _gh_railway import lift_gh

from livespec_dev_tooling.fleet._context import (
    FleetContext,
    FleetMember,
    GhResult,
    GhRunner,
    RowFinding,
    RowPass,
    RowSkip,
)
from livespec_dev_tooling.fleet._rows_decision_authority import (
    assert_decision_authority_section,
    missing_decision_authority_markers,
)

__all__: list[str] = []

_MEMBER = FleetMember(repo="widget", repo_class="impl-plugin")
_AGENTS_ARGS: tuple[str, ...] = (
    "api",
    "repos/acme/widget/contents/AGENTS.md?ref=master",
    "-H",
    "Accept: application/vnd.github.raw",
)

# A member that HAS adopted the section: all three markers, in the shape the
# fleet actually landed on 2026-08-20.
_ADOPTED_AGENTS = "\n".join(
    (
        "# Agent instructions",
        "",
        "## Decision authority — when to ask, proceed, or self-resolve",
        "",
        "- **Drive authorized work to completion; do not over-ask.** Execute the",
        "  whole arc without re-confirming each already-authorized step.",
        "",
        "## Repository mutation protocol",
    )
)

# A member that has NOT adopted it: real instructions, none of the markers.
_BARE_AGENTS = "\n".join(
    (
        "# Agent instructions",
        "",
        "## Repository mutation protocol",
        "",
        "Every tracked-file change goes worktree, PR, rebase-merge.",
    )
)

# Marker 1 present only in lowercase, mid-heading after a dash — the exact
# shape of the canonical heading.
_LOWERCASE_HEADING_AGENTS = "\n".join(
    (
        "## Decision authority — when to ask, proceed, or self-resolve",
        "",
        "- **Drive authorized work to completion; do not over-ask.**",
    )
)

# Marker 1 present but hard-wrapped across a newline, which is what an
# 80-column citation of it looks like in real fleet prose.
_WRAPPED_MARKER_AGENTS = "\n".join(
    (
        "## Decision authority",
        "",
        'Ported from `livespec/AGENTS.md` ("When to ask,',
        'proceed, or self-resolve"), plus "do not over-ask".',
    )
)


def make_context(*, table: dict[tuple[str, ...], GhResult]) -> FleetContext:
    """A `FleetContext` for owner `acme` over a canned-response runner."""

    def run(*, args: list[str], stdin: str | None = None) -> GhResult:
        del stdin
        return table.get(tuple(args), GhResult(returncode=1, stdout="", stderr="no canned"))

    runner: GhRunner = run
    return FleetContext(owner="acme", run_gh=lift_gh(runner))


def _ok(*, stdout: str) -> GhResult:
    return GhResult(returncode=0, stdout=stdout, stderr="")


def test_adopted_member_passes() -> None:
    ctx = make_context(table={_AGENTS_ARGS: _ok(stdout=_ADOPTED_AGENTS)})
    assert assert_decision_authority_section(ctx=ctx, member=_MEMBER) == RowPass()


def test_member_without_the_section_is_a_finding_naming_the_repo() -> None:
    ctx = make_context(table={_AGENTS_ARGS: _ok(stdout=_BARE_AGENTS)})
    outcome = assert_decision_authority_section(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowFinding)
    assert outcome.message.startswith("widget: ")
    assert "decision-authority" in outcome.message


def test_finding_names_every_missing_marker() -> None:
    outcome = missing_decision_authority_markers(agents_text=_BARE_AGENTS)
    assert outcome == (
        "When to ask, proceed, or self-resolve",
        "do not over-ask",
        "Decision authority",
    )


def test_a_lowercase_heading_satisfies_the_markers() -> None:
    assert missing_decision_authority_markers(agents_text=_LOWERCASE_HEADING_AGENTS) == ()


def test_a_marker_wrapped_across_a_newline_still_counts_as_present() -> None:
    assert missing_decision_authority_markers(agents_text=_WRAPPED_MARKER_AGENTS) == ()


def test_unreadable_agents_md_skips_rather_than_finding() -> None:
    ctx = make_context(table={})
    outcome = assert_decision_authority_section(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowSkip)
    assert "widget" in outcome.reason
