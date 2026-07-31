"""Tests for `livespec_dev_tooling.fleet.ensure_plugins` and its fleet row."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Final

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
from livespec_dev_tooling.fleet._contract_rows import OBLIGATION_ROWS, REPO_CLASSES
from livespec_dev_tooling.fleet._rows_claude_plugin import (
    CLAUDE_SETTINGS,
    assert_claude_plugin_currency,
)
from livespec_dev_tooling.fleet.ensure_plugins import (
    CommandResult,
    ensure,
    planned_commands,
    registry_findings,
    run_from_settings,
    settings_findings,
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
    return FleetContext(owner="acme", run_gh=lift_gh(runner))


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


_M3: Final[str] = json.dumps(
    {
        "extraKnownMarketplaces": {
            "alpha": {"source": {"source": "github", "repo": "acme/alpha", "ref": "release"}},
            "beta": {"source": {"source": "github", "repo": "acme/beta", "ref": "release"}},
        },
        "enabledPlugins": {"one@alpha": True, "two@beta": True},
    }
)


def _settings(*, enabled: object) -> str:
    return json.dumps(
        {
            "extraKnownMarketplaces": {
                "alpha": {"source": {"source": "github", "repo": "acme/alpha", "ref": "release"}},
                "beta": {"source": {"source": "github", "repo": "acme/beta", "ref": "release"}},
            },
            "enabledPlugins": enabled,
        }
    )


def _registry(*, entries: dict[str, list[dict[str, str]]]) -> str:
    return json.dumps({"plugins": entries})


def test_settings_findings_pass_when_every_marketplace_is_covered() -> None:
    assert settings_findings(settings_text=_M3) == ()


def test_settings_findings_reject_empty_enablement() -> None:
    findings = settings_findings(settings_text=_settings(enabled={}))
    assert findings != ()
    assert any("no plugin is enabled" in f for f in findings)


def test_settings_findings_reject_all_false_enablement() -> None:
    findings = settings_findings(
        settings_text=_settings(enabled={"one@alpha": False, "two@beta": False})
    )
    assert findings != ()
    assert any("no plugin is enabled" in f for f in findings)


def test_settings_findings_reject_partially_stripped_enablement() -> None:
    findings = settings_findings(settings_text=_settings(enabled={"one@alpha": True}))
    assert findings != ()
    assert any("beta" in f for f in findings)


def test_settings_findings_distinguish_disabled_from_stripped() -> None:
    disabled = settings_findings(
        settings_text=_settings(enabled={"one@alpha": True, "two@beta": False})
    )
    stripped = settings_findings(settings_text=_settings(enabled={"one@alpha": True}))
    assert any("disabled" in f for f in disabled)
    assert not any("disabled" in f for f in stripped)


def test_settings_findings_reject_non_boolean_values() -> None:
    findings = settings_findings(settings_text=_settings(enabled={"one@alpha": "true"}))
    assert findings != ()
    assert any("boolean" in f for f in findings)


def test_registry_findings_pass_when_project_path_matches() -> None:
    registry = _registry(
        entries={
            "one@alpha": [{"projectPath": "/repo"}],
            "two@beta": [{"projectPath": "/repo"}],
        }
    )
    assert registry_findings(settings_text=_M3, project_root="/repo", registry_text=registry) == ()


def test_registry_findings_reject_record_for_a_different_project() -> None:
    registry = _registry(
        entries={
            "one@alpha": [{"projectPath": "/elsewhere"}],
            "two@beta": [{"projectPath": "/repo"}],
        }
    )
    findings = registry_findings(settings_text=_M3, project_root="/repo", registry_text=registry)
    assert any("one@alpha" in f for f in findings)


def test_registry_findings_reject_absent_registry() -> None:
    findings = registry_findings(settings_text=_M3, project_root="/repo", registry_text=None)
    assert findings != ()


def test_registry_findings_ignore_disabled_plugins() -> None:
    settings = _settings(enabled={"one@alpha": True, "two@beta": False})
    registry = _registry(entries={"one@alpha": [{"projectPath": "/repo"}]})
    assert (
        registry_findings(settings_text=settings, project_root="/repo", registry_text=registry)
        == ()
    )


def test_ensure_returns_no_findings_when_provisioning_succeeds() -> None:
    registry = _registry(
        entries={
            "one@alpha": [{"projectPath": "/repo"}],
            "two@beta": [{"projectPath": "/repo"}],
        }
    )
    ran: list[tuple[str, ...]] = []

    def runner(*, args: tuple[str, ...]) -> CommandResult:
        ran.append(args)
        return CommandResult(returncode=0)

    findings = ensure(
        settings_text=_M3,
        project_root="/repo",
        runner=runner,
        read_registry=lambda: registry,
    )
    assert findings == ()
    assert ran != []


def test_ensure_refuses_to_run_commands_when_settings_are_vacuous() -> None:
    ran: list[tuple[str, ...]] = []

    def runner(*, args: tuple[str, ...]) -> CommandResult:  # pragma: no cover
        ran.append(args)
        return CommandResult(returncode=0)

    findings = ensure(
        settings_text=_settings(enabled={}),
        project_root="/repo",
        runner=runner,
        read_registry=lambda: None,
    )
    assert findings != ()
    assert ran == []


def test_ensure_reports_when_commands_succeed_but_no_record_lands() -> None:
    """The exit-status trap: every command exits 0, yet nothing was provisioned."""
    ran: list[tuple[str, ...]] = []

    def runner(*, args: tuple[str, ...]) -> CommandResult:
        ran.append(args)
        return CommandResult(returncode=0)

    findings = ensure(
        settings_text=_M3,
        project_root="/repo",
        runner=runner,
        read_registry=lambda: _registry(entries={}),
    )
    assert findings != ()
    assert any("one@alpha" in f for f in findings)


def test_settings_findings_reject_non_object_document() -> None:
    assert settings_findings(settings_text=json.dumps([1, 2])) != ()


def test_settings_findings_reject_non_object_marketplaces() -> None:
    text = json.dumps({"extraKnownMarketplaces": ["alpha"], "enabledPlugins": {}})
    assert settings_findings(settings_text=text) != ()


def test_settings_findings_reject_non_object_enablement() -> None:
    text = json.dumps({"extraKnownMarketplaces": {}, "enabledPlugins": 7})
    assert settings_findings(settings_text=text) != ()


def test_settings_findings_reject_list_enablement_with_non_string_entry() -> None:
    assert settings_findings(settings_text=_settings(enabled=[1])) != ()


def test_settings_findings_accept_legacy_list_enablement() -> None:
    assert settings_findings(settings_text=_settings(enabled=["one@alpha", "two@beta"])) == ()


def test_settings_findings_pass_when_no_marketplace_is_declared() -> None:
    assert settings_findings(settings_text=json.dumps({"enabledPlugins": {}})) == ()


def test_registry_findings_reject_non_object_document() -> None:
    assert (
        registry_findings(settings_text=json.dumps([1]), project_root="/repo", registry_text=None)
        != ()
    )


def test_registry_findings_surface_enablement_shape_errors() -> None:
    assert (
        registry_findings(
            settings_text=_settings(enabled={"one@alpha": "yes"}),
            project_root="/repo",
            registry_text=None,
        )
        != ()
    )


def test_registry_findings_treat_non_object_registry_as_empty() -> None:
    assert (
        registry_findings(settings_text=_M3, project_root="/repo", registry_text=json.dumps([1]))
        != ()
    )


def test_registry_findings_treat_non_object_plugins_map_as_empty() -> None:
    assert (
        registry_findings(
            settings_text=_M3, project_root="/repo", registry_text=json.dumps({"plugins": []})
        )
        != ()
    )


def test_registry_findings_treat_non_list_entries_as_empty() -> None:
    text = json.dumps({"plugins": {"one@alpha": {"projectPath": "/repo"}}})
    assert registry_findings(settings_text=_M3, project_root="/repo", registry_text=text) != ()


def test_registry_findings_ignore_non_object_entries() -> None:
    text = json.dumps({"plugins": {"one@alpha": ["nope"], "two@beta": [{"projectPath": "/repo"}]}})
    findings = registry_findings(settings_text=_M3, project_root="/repo", registry_text=text)
    assert any("one@alpha" in f for f in findings)


def test_ensure_reports_a_failing_command_and_stops() -> None:
    ran: list[tuple[str, ...]] = []

    def runner(*, args: tuple[str, ...]) -> CommandResult:
        ran.append(args)
        return CommandResult(returncode=9)

    findings = ensure(
        settings_text=_M3,
        project_root="/repo",
        runner=runner,
        read_registry=lambda: None,
    )
    assert any("exit 9" in f for f in findings)
    assert len(ran) == 1
