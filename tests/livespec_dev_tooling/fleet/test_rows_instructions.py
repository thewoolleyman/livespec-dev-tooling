"""Canned-context tests for the agent-instruction fleet rows.

Exercises `assert_agent_instruction_surface` and
`assert_agent_ai_references_resolve` against a canned-response
`FleetContext` (no network, no real `gh`), mirroring the sibling
`test_rows_beads` / `test_rows_files` patterns.

The conformant `AGENTS.md` fixture is BUILT FROM the row module's
`WORKTREE_CREATE_SENTENCE` rather than restating it. That is the whole
point of homing the fleet-universal core text beside the predicate: a
fixture that carried its own copy could drift from the sentence the row
demands, and the drift would present as a green suite over a check
nobody could satisfy by pasting what it quotes.

The module is imported under an alias and the constants are read INSIDE
test bodies. A top-level `from ... import WORKTREE_CREATE_SENTENCE`
would make the Red leg of this slice a collection error — proof only
that a name is missing, never that the behavior is unimplemented.
"""

from __future__ import annotations

import json

from _gh_railway import lift_gh

from livespec_dev_tooling.fleet import _rows_instructions as rows_instructions
from livespec_dev_tooling.fleet._context import (
    FleetContext,
    FleetMember,
    GhResult,
    GhRunner,
    RowFinding,
    RowPass,
    RowSkip,
)
from livespec_dev_tooling.fleet._rows_instructions import (
    assert_agent_ai_references_resolve,
    assert_agent_instruction_surface,
)

__all__: list[str] = []

_MEMBER = FleetMember(repo="widget", repo_class="impl-plugin")
_AGENTS_ARGS: tuple[str, ...] = (
    "api",
    "repos/acme/widget/contents/AGENTS.md?ref=master",
    "-H",
    "Accept: application/vnd.github.raw",
)
_SETTINGS_ARGS: tuple[str, ...] = (
    "api",
    "repos/acme/widget/contents/.claude/settings.json?ref=master",
    "-H",
    "Accept: application/vnd.github.raw",
)
# The repo-metadata read `canonical_ref` resolves the member's default
# branch from; uncanned, it falls back to `master`.
_REPO_ARGS: tuple[str, ...] = ("api", "repos/acme/widget")

# The shape the 2026-09-06 survey found in all seventeen member instruction
# files: a raw `git worktree add`, with the recipe named nowhere.
_RAW_WORKTREE_ADD_BODY = "Create it with `git worktree add -b <branch> <path> master`."

_SETTINGS_WITH_GUARD = (
    '{"hooks": {"PreToolUse": [{"command": '
    '"$CLAUDE_PROJECT_DIR/.claude/hooks/beads-access-guard.sh"}]}}'
)
_SETTINGS_NO_GUARD = '{"hooks": {"PreToolUse": []}}'


def _agents(*, protocol_body: str, trailing: tuple[str, ...] = ()) -> str:
    """A fixture `AGENTS.md` carrying every universal-core heading.

    `protocol_body` is the body of the `## Repository mutation protocol`
    section — the one region the worktree-creation predicate reads.
    `trailing` appends further lines after the last heading, so a fixture
    can put the recipe somewhere the predicate must NOT count.
    """
    return "\n".join(
        (
            "# Agent instructions",
            "## Repository mutation protocol",
            protocol_body,
            "## Agent prerequisites for plugin work",
            "## Beads runtime prerequisites",
            "## Daily commands",
            "## Revise co-edit discipline — `tests/heading-coverage.json`",
            "## Red-Green-Replay commit protocol",
            *trailing,
        )
    )


def _conformant_agents() -> str:
    """A fixture that satisfies every leg of the instruction-surface row."""
    return _agents(protocol_body=rows_instructions.WORKTREE_CREATE_SENTENCE)


def make_context(*, table: dict[tuple[str, ...], GhResult]) -> FleetContext:
    """A `FleetContext` for owner `acme` over a canned-response runner."""

    def run(*, args: list[str], stdin: str | None = None) -> GhResult:
        del stdin
        return table.get(tuple(args), GhResult(returncode=1, stdout="", stderr="no canned"))

    runner: GhRunner = run
    return FleetContext(owner="acme", run_gh=lift_gh(runner))


def _ok(*, stdout: str) -> GhResult:
    return GhResult(returncode=0, stdout=stdout, stderr="")


def _surface_context(*, agents: str, settings: str = _SETTINGS_WITH_GUARD) -> FleetContext:
    return make_context(
        table={_AGENTS_ARGS: _ok(stdout=agents), _SETTINGS_ARGS: _ok(stdout=settings)}
    )


def test_complete_surface_passes() -> None:
    ctx = _surface_context(agents=_conformant_agents())
    assert assert_agent_instruction_surface(ctx=ctx, member=_MEMBER) == RowPass()


def test_missing_heading_is_finding() -> None:
    partial = _conformant_agents().replace("## Beads runtime prerequisites\n", "")
    outcome = assert_agent_instruction_surface(ctx=_surface_context(agents=partial), member=_MEMBER)
    assert isinstance(outcome, RowFinding)
    assert "Beads runtime prerequisites" in outcome.message


def test_missing_guard_is_finding() -> None:
    ctx = _surface_context(agents=_conformant_agents(), settings=_SETTINGS_NO_GUARD)
    outcome = assert_agent_instruction_surface(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowFinding)
    assert "beads-access-guard" in outcome.message


def test_unreadable_agents_skips() -> None:
    ctx = make_context(table={_SETTINGS_ARGS: _ok(stdout=_SETTINGS_WITH_GUARD)})
    assert isinstance(assert_agent_instruction_surface(ctx=ctx, member=_MEMBER), RowSkip)


def test_unreadable_settings_skips() -> None:
    ctx = make_context(table={_AGENTS_ARGS: _ok(stdout=_conformant_agents())})
    assert isinstance(assert_agent_instruction_surface(ctx=ctx, member=_MEMBER), RowSkip)


def test_mutation_protocol_without_the_recipe_is_a_finding() -> None:
    """A raw `git worktree add` mutation protocol yields a finding.

    The FIRST assertion is the behavioral one on purpose: before the
    predicate exists this fixture is a complete surface and the row
    passes, so the Red leg fails on a genuine assertion rather than on a
    missing name.
    """
    ctx = _surface_context(agents=_agents(protocol_body=_RAW_WORKTREE_ADD_BODY))
    outcome = assert_agent_instruction_surface(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowFinding)
    assert rows_instructions.WORKTREE_CREATE_COMMAND in outcome.message


def test_the_finding_quotes_the_required_sentence_verbatim() -> None:
    """The finding is paste-able: it carries the exact sentence to port."""
    ctx = _surface_context(agents=_agents(protocol_body=_RAW_WORKTREE_ADD_BODY))
    outcome = assert_agent_instruction_surface(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowFinding)
    assert rows_instructions.WORKTREE_CREATE_SENTENCE in outcome.message


def test_the_recipe_finding_is_a_warning_pending_fleet_adoption() -> None:
    """The predicate ships DISARMED at warning severity.

    Measured 2026-09-06, no governed member names the recipe. An
    error-severity finding here would red the central sweep for the whole
    fleet the moment it merged — the 46c5dab shape `plan/rop-railway-
    enforcement/` carries a standing constraint against.
    """
    ctx = _surface_context(agents=_agents(protocol_body=_RAW_WORKTREE_ADD_BODY))
    outcome = assert_agent_instruction_surface(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowFinding)
    assert outcome.severity == "warning"


def test_a_missing_heading_outranks_the_recipe_warning() -> None:
    """A structurally absent section is reported as the error it is.

    Both legs are unsatisfied here; the row must not downgrade a missing
    universal-core heading to a warning by reporting the recipe first.
    """
    agents = _agents(protocol_body=_RAW_WORKTREE_ADD_BODY).replace("## Daily commands\n", "")
    outcome = assert_agent_instruction_surface(ctx=_surface_context(agents=agents), member=_MEMBER)
    assert isinstance(outcome, RowFinding)
    assert outcome.severity == "error"
    assert "Daily commands" in outcome.message


def test_prose_naming_the_recipe_passes_without_matching_the_sentence() -> None:
    """The predicate is ONE phrase, not sentence equality — it judges no prose."""
    body = "Run `mise exec -- just worktree-create <branch>` from the primary checkout."
    ctx = _surface_context(agents=_agents(protocol_body=body))
    assert assert_agent_instruction_surface(ctx=ctx, member=_MEMBER) == RowPass()


def test_the_recipe_named_outside_the_mutation_protocol_does_not_count() -> None:
    """A member that names the recipe under some other H2 is still a finding.

    The section slice is the point: guidance a session does not meet where
    it creates a worktree is guidance it does not read.
    """
    agents = _agents(
        protocol_body=_RAW_WORKTREE_ADD_BODY,
        trailing=(f"Run `{rows_instructions.WORKTREE_CREATE_COMMAND} <branch>` sometimes.",),
    )
    outcome = assert_agent_instruction_surface(ctx=_surface_context(agents=agents), member=_MEMBER)
    assert isinstance(outcome, RowFinding)
    assert rows_instructions.WORKTREE_CREATE_SENTENCE in outcome.message


def test_mutation_protocol_section_reads_a_trailing_section_to_end_of_file() -> None:
    """No following H2 is not an empty section — the slice runs to EOF."""
    text = "# Title\n## Repository mutation protocol\nbody line\n"
    assert rows_instructions.mutation_protocol_section(agents_text=text) == "body line"


def test_mutation_protocol_section_is_empty_when_the_heading_is_absent() -> None:
    text = "# Title\n## Daily commands\njust check\n"
    assert rows_instructions.mutation_protocol_section(agents_text=text) == ""


def test_mutation_protocol_heading_is_matched_by_prefix() -> None:
    """A suffixed heading still carries the section, as the heading list does."""
    text = "## Repository mutation protocol — worktree first\ntext\n## Next\n"
    assert rows_instructions.mutation_protocol_section(agents_text=text) == "text"


def test_the_required_sentence_names_the_required_command() -> None:
    """The quoted sentence and the grepped phrase are ONE source, not two."""
    assert rows_instructions.WORKTREE_CREATE_COMMAND in rows_instructions.WORKTREE_CREATE_SENTENCE


def test_the_manual_hint_carries_the_required_sentence() -> None:
    """`wire_fleet_member`'s hint is paste-able, not a description of a paste."""
    assert (
        rows_instructions.WORKTREE_CREATE_SENTENCE
        in rows_instructions.AGENT_INSTRUCTION_SURFACE_HINT
    )


_TREE_ARGS: tuple[str, ...] = ("api", "repos/acme/widget/git/trees/master?recursive=1")


def _tree_table(*, paths: list[str], truncated: bool = False) -> dict[tuple[str, ...], GhResult]:
    """A canned table whose recursive-tree call yields `paths` (mode 100644)."""
    entries = [{"path": p, "mode": "100644"} for p in paths]
    payload = {"tree": entries, "truncated": truncated}
    return {_TREE_ARGS: GhResult(returncode=0, stdout=json.dumps(payload), stderr="")}


def _contents_args(*, path: str) -> tuple[str, ...]:
    return (
        "api",
        f"repos/acme/widget/contents/{path}?ref=master",
        "-H",
        "Accept: application/vnd.github.raw",
    )


def test_ai_references_resolve_pass() -> None:
    table = _tree_table(paths=["AGENTS.md", ".ai/agent-disciplines.md", "README.md"])
    table[_contents_args(path="AGENTS.md")] = _ok(
        stdout="See `.ai/agent-disciplines.md` for detail.\n"
    )
    ctx = make_context(table=table)
    assert assert_agent_ai_references_resolve(ctx=ctx, member=_MEMBER) == RowPass()


def test_ai_references_resolve_nested_pass() -> None:
    table = _tree_table(paths=["docs/AGENTS.md", "docs/.ai/x.md"])
    table[_contents_args(path="docs/AGENTS.md")] = _ok(stdout="See `.ai/x.md`.\n")
    ctx = make_context(table=table)
    assert assert_agent_ai_references_resolve(ctx=ctx, member=_MEMBER) == RowPass()


def test_ai_references_dangling_is_finding() -> None:
    table = _tree_table(paths=["AGENTS.md"])
    table[_contents_args(path="AGENTS.md")] = _ok(stdout="See `.ai/missing.md`.\n")
    ctx = make_context(table=table)
    outcome = assert_agent_ai_references_resolve(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowFinding)
    assert ".ai/missing.md" in outcome.message
    assert "AGENTS.md:1" in outcome.message


def test_ai_references_no_refs_pass() -> None:
    table = _tree_table(paths=["AGENTS.md"])
    table[_contents_args(path="AGENTS.md")] = _ok(stdout="# Agent instructions\n\nNo overflow.\n")
    ctx = make_context(table=table)
    assert assert_agent_ai_references_resolve(ctx=ctx, member=_MEMBER) == RowPass()


def test_ai_references_archive_agents_excluded_pass() -> None:
    table = _tree_table(paths=["archive/AGENTS.md"])
    table[_contents_args(path="archive/AGENTS.md")] = _ok(stdout="Old `.ai/gone.md` ref.\n")
    ctx = make_context(table=table)
    assert assert_agent_ai_references_resolve(ctx=ctx, member=_MEMBER) == RowPass()


def test_ai_references_unreadable_agents_content_skipped_pass() -> None:
    # The tree lists an AGENTS.md but its contents read fails (no canned
    # entry): can't-read is not absent, so the file is skipped rather than
    # producing a false finding — and with no other AGENTS.md, the row passes.
    ctx = make_context(table=_tree_table(paths=["AGENTS.md"]))
    assert assert_agent_ai_references_resolve(ctx=ctx, member=_MEMBER) == RowPass()


def test_ai_references_unreadable_tree_skips() -> None:
    ctx = make_context(table={})
    outcome = assert_agent_ai_references_resolve(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowSkip)
    assert "unreadable" in outcome.reason


def test_ai_references_unreadable_tree_skip_names_the_canonical_ref() -> None:
    """The skip names the ref the tree read used, never a hardcoded `master`.

    An operator debugging a `main`-default member must not be told the
    read failed on a branch that was never addressed.
    """
    table = {_REPO_ARGS: _ok(stdout=json.dumps({"default_branch": "main"}))}
    outcome = assert_agent_ai_references_resolve(ctx=make_context(table=table), member=_MEMBER)
    assert isinstance(outcome, RowSkip)
    assert outcome.reason == "widget: main tree unreadable"


def test_ai_references_truncated_tree_skips() -> None:
    table = _tree_table(paths=["AGENTS.md"], truncated=True)
    table[_contents_args(path="AGENTS.md")] = _ok(stdout="See `.ai/missing.md`.\n")
    ctx = make_context(table=table)
    outcome = assert_agent_ai_references_resolve(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowSkip)
    assert "truncated" in outcome.reason
