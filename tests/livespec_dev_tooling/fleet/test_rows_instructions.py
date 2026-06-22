"""Canned-context tests for the agent-instruction-surface fleet row.

Exercises `assert_agent_instruction_surface` against a canned-response
`FleetContext` (no network, no real `gh`), mirroring the sibling
`test_rows_beads` pattern.
"""

from __future__ import annotations

from livespec_dev_tooling.fleet._context import (
    FleetContext,
    FleetMember,
    GhResult,
    GhRunner,
    RowFinding,
    RowPass,
    RowSkip,
)
from livespec_dev_tooling.fleet._rows_instructions import assert_agent_instruction_surface

__all__: list[str] = []

_MEMBER = FleetMember(repo="widget", repo_class="impl-plugin")
_AGENTS_ARGS: tuple[str, ...] = (
    "api",
    "repos/acme/widget/contents/AGENTS.md",
    "-H",
    "Accept: application/vnd.github.raw",
)
_SETTINGS_ARGS: tuple[str, ...] = (
    "api",
    "repos/acme/widget/contents/.claude/settings.json",
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
