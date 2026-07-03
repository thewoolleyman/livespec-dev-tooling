"""Tests for `livespec_dev_tooling.fleet.ensure_plugins` and its fleet row."""

from __future__ import annotations

import json
from pathlib import Path

from livespec_dev_tooling.fleet._context import (
    FleetContext,
    FleetMember,
    GhResult,
    GhRunner,
    RowFinding,
    RowPass,
    RowSkip,
)
from livespec_dev_tooling.fleet._rows_files import (
    CLAUDE_SETTINGS,
    assert_claude_plugin_currency,
)
from livespec_dev_tooling.fleet.contract import OBLIGATION_ROWS, REPO_CLASSES
from livespec_dev_tooling.fleet.ensure_plugins import (
    CommandResult,
    planned_commands,
    run_from_settings,
)

__all__: list[str] = []


def _settings_text() -> str:
    """A minimal committed Claude settings payload with marketplaces and plugins."""
    return json.dumps(
        {
            "enabledPlugins": {
                "livespec@livespec": True,
                "livespec@livespec-driver-claude": True,
                "disabled@plugin": False,
            },
            "extraKnownMarketplaces": {
                "livespec": {
                    "source": {
                        "source": "github",
                        "repo": "thewoolleyman/livespec",
                        "ref": "release",
                    }
                },
                "driver": {
                    "source": {
                        "source": "github",
                        "repo": "thewoolleyman/livespec-driver-claude",
                        "ref": "v1.2.3",
                    }
                },
            },
        }
    )


def test_planned_commands_are_derived_from_settings_json() -> None:
    commands = planned_commands(settings_text=_settings_text())
    assert commands == (
        (
            "claude",
            "plugin",
            "marketplace",
            "add",
            "thewoolleyman/livespec@release",
        ),
        (
            "claude",
            "plugin",
            "marketplace",
            "add",
            "thewoolleyman/livespec-driver-claude@v1.2.3",
        ),
        ("claude", "plugin", "install", "livespec@livespec", "-s", "project"),
        ("claude", "plugin", "update", "livespec@livespec", "-s", "project"),
        ("claude", "plugin", "install", "livespec@livespec-driver-claude", "-s", "project"),
        ("claude", "plugin", "update", "livespec@livespec-driver-claude", "-s", "project"),
    )


def test_run_from_settings_executes_commands_in_order(*, tmp_path: Path) -> None:
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir()
    settings.write_text(_settings_text(), encoding="utf-8")
    seen: list[tuple[str, ...]] = []

    def runner(*, args: tuple[str, ...]) -> CommandResult:
        seen.append(args)
        return CommandResult(returncode=0)

    assert run_from_settings(settings_path=settings, runner=runner) == 0
    assert seen == list(planned_commands(settings_text=_settings_text()))


def test_run_from_settings_stops_at_first_failed_command(*, tmp_path: Path) -> None:
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir()
    settings.write_text(_settings_text(), encoding="utf-8")
    seen: list[tuple[str, ...]] = []

    def runner(*, args: tuple[str, ...]) -> CommandResult:
        seen.append(args)
        return CommandResult(returncode=17 if len(seen) == 2 else 0)

    assert run_from_settings(settings_path=settings, runner=runner) == 17
    assert seen == list(planned_commands(settings_text=_settings_text()))[:2]


_MEMBER = FleetMember(repo="widget", repo_class="impl-plugin")
_TREE_ARGS: tuple[str, ...] = ("api", "repos/acme/widget/git/trees/master?recursive=1")
_SETTINGS_ARGS: tuple[str, ...] = (
    "api",
    "repos/acme/widget/contents/.claude/settings.json?ref=master",
    "-H",
    "Accept: application/vnd.github.raw",
)
_JUSTFILE_ARGS: tuple[str, ...] = (
    "api",
    "repos/acme/widget/contents/justfile?ref=master",
    "-H",
    "Accept: application/vnd.github.raw",
)
_PLUGIN_SETTINGS = json.dumps(
    {
        "hooks": {
            "SessionStart": [
                {
                    "matcher": "",
                    "hooks": [{"type": "command", "command": "mise exec -- just ensure-plugins"}],
                }
            ]
        },
        "enabledPlugins": {"livespec@livespec": True},
        "extraKnownMarketplaces": {},
    }
)
_STANDARD_WRAPPER_JUSTFILE = (
    "ensure-plugins:\n"
    "    mise exec -- uv run --no-sync python -m livespec_dev_tooling.fleet.ensure_plugins\n"
)


def _make_context(*, table: dict[tuple[str, ...], GhResult]) -> FleetContext:
    """A `FleetContext` for owner `acme` over a canned-response runner."""

    def run(*, args: list[str], stdin: str | None = None) -> GhResult:
        del stdin
        return table.get(tuple(args), GhResult(returncode=1, stdout="", stderr="no canned"))

    runner: GhRunner = run
    return FleetContext(owner="acme", run_gh=runner)


def _plugin_currency_table(
    *, settings: str | None = _PLUGIN_SETTINGS, justfile: str | None = _STANDARD_WRAPPER_JUSTFILE
) -> dict[tuple[str, ...], GhResult]:
    """A canned table for the Claude plugin-currency row."""
    payload = {"tree": [{"path": CLAUDE_SETTINGS}, {"path": "justfile"}], "truncated": False}
    table = {_TREE_ARGS: GhResult(returncode=0, stdout=json.dumps(payload), stderr="")}
    if settings is not None:
        table[_SETTINGS_ARGS] = GhResult(returncode=0, stdout=settings, stderr="")
    if justfile is not None:
        table[_JUSTFILE_ARGS] = GhResult(returncode=0, stdout=justfile, stderr="")
    return table


def test_claude_plugin_currency_passes_for_hook_and_standard_wrapper() -> None:
    ctx = _make_context(table=_plugin_currency_table())
    assert assert_claude_plugin_currency(ctx=ctx, member=_MEMBER) == RowPass()


def test_claude_plugin_currency_fails_loudly_when_hook_missing() -> None:
    settings = json.dumps({"hooks": {}, "enabledPlugins": {"livespec@livespec": True}})
    ctx = _make_context(table=_plugin_currency_table(settings=settings))
    outcome = assert_claude_plugin_currency(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowFinding)
    assert outcome.severity == "error"
    assert "widget" in outcome.message
    assert "SessionStart" in outcome.message


def test_claude_plugin_currency_fails_loudly_when_wrapper_is_not_standard() -> None:
    drifted = "ensure-plugins:\n    claude plugin install livespec@livespec -s project\n"
    ctx = _make_context(table=_plugin_currency_table(justfile=drifted))
    outcome = assert_claude_plugin_currency(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowFinding)
    assert "standard wrapper" in outcome.message


def test_claude_plugin_currency_allows_explicit_documented_successor() -> None:
    settings = json.dumps(
        {
            "hooks": {},
            "livespecPluginCurrencySuccessor": {
                "mechanism": "core-bootstrap-fail-loud-currency-gate",
                "documentedIn": "livespec/SPECIFICATION/contracts.md#plugin-currency",
            },
        }
    )
    ctx = _make_context(table=_plugin_currency_table(settings=settings, justfile=""))
    assert assert_claude_plugin_currency(ctx=ctx, member=_MEMBER) == RowPass()


def test_claude_plugin_currency_skips_when_files_are_unreadable() -> None:
    ctx = _make_context(table=_plugin_currency_table(settings=None))
    outcome = assert_claude_plugin_currency(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowSkip)
    assert CLAUDE_SETTINGS in outcome.reason


def test_claude_plugin_currency_row_is_wired_for_every_class() -> None:
    row = next((r for r in OBLIGATION_ROWS if r.row_id == "claude-plugin-currency"), None)
    assert row is not None
    assert row.obligation_type == "committed-file"
    assert row.applies_to == frozenset(REPO_CLASSES)
    assert row.assert_member is assert_claude_plugin_currency
    assert row.reconcile is None
    assert row.manual_hint
