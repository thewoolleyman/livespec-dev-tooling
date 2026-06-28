"""Canned-context tests for the agent-instruction fleet rows.

Exercises `assert_agent_instruction_surface` and
`assert_agent_ai_references_resolve` against a canned-response
`FleetContext` (no network, no real `gh`), mirroring the sibling
`test_rows_beads` / `test_rows_files` patterns.
"""

from __future__ import annotations

import json

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

_FULL_AGENTS = "\n".join(
    (
        "# Agent instructions",
        "## Repository mutation protocol",
        "## Agent prerequisites for plugin work",
        "## Beads runtime prerequisites",
        "## Daily commands",
        "## Revise co-edit discipline — `tests/heading-coverage.json`",
        "## Red-Green-Replay commit protocol",
    )
)
_SETTINGS_WITH_GUARD = (
    '{"hooks": {"PreToolUse": [{"command": '
    '"$CLAUDE_PROJECT_DIR/.claude/hooks/beads-access-guard.sh"}]}}'
)
_SETTINGS_NO_GUARD = '{"hooks": {"PreToolUse": []}}'


def make_context(*, table: dict[tuple[str, ...], GhResult]) -> FleetContext:
    """A `FleetContext` for owner `acme` over a canned-response runner."""

    def run(*, args: list[str], stdin: str | None = None) -> GhResult:
        del stdin
        return table.get(tuple(args), GhResult(returncode=1, stdout="", stderr="no canned"))

    runner: GhRunner = run
    return FleetContext(owner="acme", run_gh=runner)


def _ok(*, stdout: str) -> GhResult:
    return GhResult(returncode=0, stdout=stdout, stderr="")


def test_complete_surface_passes() -> None:
    ctx = make_context(
        table={
            _AGENTS_ARGS: _ok(stdout=_FULL_AGENTS),
            _SETTINGS_ARGS: _ok(stdout=_SETTINGS_WITH_GUARD),
        }
    )
    assert assert_agent_instruction_surface(ctx=ctx, member=_MEMBER) == RowPass()


def test_missing_heading_is_finding() -> None:
    partial = _FULL_AGENTS.replace("## Beads runtime prerequisites\n", "")
    ctx = make_context(
        table={
            _AGENTS_ARGS: _ok(stdout=partial),
            _SETTINGS_ARGS: _ok(stdout=_SETTINGS_WITH_GUARD),
        }
    )
    outcome = assert_agent_instruction_surface(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowFinding)
    assert "Beads runtime prerequisites" in outcome.message


def test_missing_guard_is_finding() -> None:
    ctx = make_context(
        table={
            _AGENTS_ARGS: _ok(stdout=_FULL_AGENTS),
            _SETTINGS_ARGS: _ok(stdout=_SETTINGS_NO_GUARD),
        }
    )
    outcome = assert_agent_instruction_surface(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowFinding)
    assert "beads-access-guard" in outcome.message


def test_unreadable_agents_skips() -> None:
    ctx = make_context(table={_SETTINGS_ARGS: _ok(stdout=_SETTINGS_WITH_GUARD)})
    assert isinstance(assert_agent_instruction_surface(ctx=ctx, member=_MEMBER), RowSkip)


def test_unreadable_settings_skips() -> None:
    ctx = make_context(table={_AGENTS_ARGS: _ok(stdout=_FULL_AGENTS)})
    assert isinstance(assert_agent_instruction_surface(ctx=ctx, member=_MEMBER), RowSkip)


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


def test_ai_references_truncated_tree_skips() -> None:
    table = _tree_table(paths=["AGENTS.md"], truncated=True)
    table[_contents_args(path="AGENTS.md")] = _ok(stdout="See `.ai/missing.md`.\n")
    ctx = make_context(table=table)
    outcome = assert_agent_ai_references_resolve(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowSkip)
    assert "truncated" in outcome.reason
