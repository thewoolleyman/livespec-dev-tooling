"""Tests for `livespec_dev_tooling.fleet.ensure_plugins` and its fleet row."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Final

import pytest
from _gh_railway import lift_gh
from returns.io import IOFailure, IOResult, IOSuccess
from returns.unsafe import unsafe_perform_io

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
from livespec_dev_tooling.fleet._ensure_plugin_artifacts import (
    MANIFEST_UNDECODABLE,
    MANIFEST_UNPARSEABLE,
    ArtifactUnreadable,
    artifact_record_findings,
    artifact_record_repair_paths,
)
from livespec_dev_tooling.fleet._rows_claude_plugin import (
    CLAUDE_SETTINGS,
    assert_claude_plugin_currency,
)
from livespec_dev_tooling.fleet.ensure_plugins import (
    PluginCommandOutcome,
    PluginCommandResult,
    ensure,
    planned_commands,
    plugin_artifact_findings,
    registry_findings,
    remove_plugin_cache_dir,
    run_from_settings,
    settings_findings,
)

__all__: list[str] = []

# The two names `checks/public_api_result_typed` accepts as railway-typed, and
# the terminal-name reduction it applies before comparing. Restated here rather
# than imported so this file pins the PROPERTY the shipped detector reads,
# independently of that module continuing to exist in its current shape.
_RAILWAY_RETURN_NAMES = frozenset({"Result", "IOResult"})


def _terminal_return_name(*, rendered: str) -> str:
    """`IOResult[tuple[str, ...], ArtifactUnreadable]` → `IOResult`.

    Mirrors `public_api_result_typed._annotation_head_name`: drop the
    subscript, then drop any dotted qualifier.
    """
    return rendered.split("[", maxsplit=1)[0].rsplit(".", maxsplit=1)[-1]


def _ran(*, returncode: int) -> PluginCommandOutcome:
    """Lift a canned exit code onto the plugin seam's success track.

    Every canned runner in this file answers as a `claude` that RAN — which
    is what the provisioning behaviour under test is about — so lifting them
    wholesale preserves each existing assertion. The failure track ("the
    invocation never happened") is exercised at the seam and at the caller
    that used to misread it, in `test_plugin_command_invocation_railway`,
    rather than by threading a failure through nine canned runners and
    hoping one of them was set to fail. `_gh_railway.lift_gh` is the same
    move for the `gh` seam.
    """
    return IOSuccess(PluginCommandResult(returncode=returncode))


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

    def runner(*, args: tuple[str, ...]) -> PluginCommandOutcome:
        seen.append(args)
        return _ran(returncode=0)

    assert run_from_settings(settings_path=settings, runner=runner) == IOSuccess(0)
    assert seen == list(planned_commands(settings_text=_settings_text()))


def test_run_from_settings_stops_at_first_failed_command(*, tmp_path: Path) -> None:
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir()
    settings.write_text(_settings_text(), encoding="utf-8")
    seen: list[tuple[str, ...]] = []

    def runner(*, args: tuple[str, ...]) -> PluginCommandOutcome:
        seen.append(args)
        return _ran(returncode=17 if len(seen) == 2 else 0)

    assert run_from_settings(settings_path=settings, runner=runner) == IOSuccess(17)
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


def _registry(*, entries: dict[str, list[dict[str, object]]]) -> str:
    return json.dumps({"plugins": entries})


def _plugin_dir(*, tmp_path: Path, name: str) -> Path:
    path = tmp_path / name
    path.mkdir()
    (path / "plugin.json").write_text("{}", encoding="utf-8")
    return path


def _cache_plugin_dir(*, home: Path, name: str) -> Path:
    path = home / ".claude" / "plugins" / "cache" / name
    path.mkdir(parents=True)
    (path / "plugin.json").write_text("{}", encoding="utf-8")
    return path


def _write_cache_manifest(*, plugin: Path, required_paths: list[str]) -> None:
    (plugin / "cache-manifest.json").write_text(
        json.dumps({"required_paths": required_paths}),
        encoding="utf-8",
    )


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


def test_registry_findings_pass_when_project_path_matches(*, tmp_path: Path) -> None:
    one = _plugin_dir(tmp_path=tmp_path, name="one")
    two = _plugin_dir(tmp_path=tmp_path, name="two")
    registry = _registry(
        entries={
            "one@alpha": [{"projectPath": "/repo", "installPath": str(one)}],
            "two@beta": [{"projectPath": "/repo", "installPath": str(two)}],
        }
    )
    assert registry_findings(settings_text=_M3, project_root="/repo", registry_text=registry) == ()


def test_registry_findings_reject_record_for_a_different_project(*, tmp_path: Path) -> None:
    plugin = _plugin_dir(tmp_path=tmp_path, name="plugin")
    registry = _registry(
        entries={
            "one@alpha": [{"projectPath": "/elsewhere", "installPath": str(plugin)}],
            "two@beta": [{"projectPath": "/repo", "installPath": str(plugin)}],
        }
    )
    findings = registry_findings(settings_text=_M3, project_root="/repo", registry_text=registry)
    assert any("one@alpha" in f for f in findings)


def test_registry_findings_reject_absent_registry() -> None:
    findings = registry_findings(settings_text=_M3, project_root="/repo", registry_text=None)
    assert findings != ()


def test_registry_findings_ignore_disabled_plugins(*, tmp_path: Path) -> None:
    settings = _settings(enabled={"one@alpha": True, "two@beta": False})
    plugin = _plugin_dir(tmp_path=tmp_path, name="plugin")
    registry = _registry(
        entries={"one@alpha": [{"projectPath": "/repo", "installPath": str(plugin)}]}
    )
    assert (
        registry_findings(settings_text=settings, project_root="/repo", registry_text=registry)
        == ()
    )


def test_registry_findings_reject_missing_install_path_directory(*, tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    registry = _registry(
        entries={
            "one@alpha": [{"projectPath": "/repo", "installPath": str(missing)}],
            "two@beta": [
                {
                    "projectPath": "/repo",
                    "installPath": str(_plugin_dir(tmp_path=tmp_path, name="two")),
                }
            ],
        }
    )

    findings = registry_findings(settings_text=_M3, project_root="/repo", registry_text=registry)

    assert any("one@alpha" in finding and "does not exist" in finding for finding in findings)


def test_registry_findings_reject_empty_install_path_directory(*, tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    registry = _registry(
        entries={
            "one@alpha": [{"projectPath": "/repo", "installPath": str(empty)}],
            "two@beta": [
                {
                    "projectPath": "/repo",
                    "installPath": str(_plugin_dir(tmp_path=tmp_path, name="two")),
                }
            ],
        }
    )

    findings = registry_findings(settings_text=_M3, project_root="/repo", registry_text=registry)

    assert any("one@alpha" in finding and "plugin.json" in finding for finding in findings)


def test_registry_findings_accept_plugin_json_in_install_path(*, tmp_path: Path) -> None:
    registry = _registry(
        entries={
            "one@alpha": [
                {
                    "projectPath": "/repo",
                    "installPath": str(_plugin_dir(tmp_path=tmp_path, name="one")),
                }
            ],
            "two@beta": [
                {
                    "projectPath": "/repo",
                    "installPath": str(_plugin_dir(tmp_path=tmp_path, name="two")),
                }
            ],
        }
    )

    assert registry_findings(settings_text=_M3, project_root="/repo", registry_text=registry) == ()


def _answered(*, outcome: IOResult[tuple[str, ...], ArtifactUnreadable]) -> tuple[str, ...]:
    """The findings of an artifact probe that reached a verdict.

    Asserting the SUCCESS track before reading it is what keeps every
    behavioural assertion below honest: an `IOFailure` unwrapped blindly would
    raise, but one silently treated as "no findings" is exactly the confusion
    the conversion removes, so the track is checked rather than assumed.
    """
    assert not isinstance(outcome, IOFailure), f"expected an answered probe, got {outcome}"
    return unsafe_perform_io(outcome.unwrap())


def _unanswered(*, install_path: str) -> IOResult[tuple[str, ...], ArtifactUnreadable]:
    """A probe that could not decide, as an injected reader would produce one."""
    return IOFailure(
        ArtifactUnreadable(
            install_path=install_path, reason=MANIFEST_UNPARSEABLE, detail="canned non-answer"
        )
    )


def test_every_artifact_public_answer_is_railway_typed() -> None:
    """THE CONVERSION ITSELF: no public answer here may be a bare value.

    `checks/public_api_result_typed` reads a function as on the railway when
    its return annotation's terminal name is `Result` or `IOResult`. That check
    is a NO-OP in this repository — `pure_trees` is declared `not_applicable` —
    so nothing else here would notice a regression to the bare
    `tuple[str, ...]` these four used to return, in which "the build is
    usable", "the build is broken" and "I refused to delete it" were one type.
    This is the arming that stands in for it until the scan universe is.
    """
    for func in (
        plugin_artifact_findings,
        remove_plugin_cache_dir,
        artifact_record_findings,
        artifact_record_repair_paths,
    ):
        rendered = str(func.__annotations__["return"])
        assert _terminal_return_name(rendered=rendered) in _RAILWAY_RETURN_NAMES, (
            f"{func.__name__} must return a Result/IOResult so its failure track is "
            f"expressible; got the bare annotation {rendered!r}"
        )


def test_plugin_artifact_findings_keep_current_behavior_without_cache_manifest(
    *, tmp_path: Path
) -> None:
    plugin = _plugin_dir(tmp_path=tmp_path, name="plugin")

    assert _answered(outcome=plugin_artifact_findings(install_path=str(plugin))) == ()


def test_plugin_artifact_findings_accept_satisfied_cache_manifest(*, tmp_path: Path) -> None:
    plugin = _plugin_dir(tmp_path=tmp_path, name="plugin")
    (plugin / "scripts" / "bin").mkdir(parents=True)
    _write_cache_manifest(plugin=plugin, required_paths=["scripts/bin"])

    assert _answered(outcome=plugin_artifact_findings(install_path=str(plugin))) == ()


def test_plugin_artifact_findings_report_missing_manifest_required_path(*, tmp_path: Path) -> None:
    plugin = _plugin_dir(tmp_path=tmp_path, name="plugin")
    _write_cache_manifest(plugin=plugin, required_paths=["scripts/bin"])

    findings = _answered(outcome=plugin_artifact_findings(install_path=str(plugin)))

    assert any("scripts/bin" in finding for finding in findings)


def test_plugin_artifact_findings_report_invalid_manifest_shape(*, tmp_path: Path) -> None:
    plugin = _plugin_dir(tmp_path=tmp_path, name="plugin")
    (plugin / "cache-manifest.json").write_text(
        json.dumps({"required_paths": ["", "/absolute", "../escape", 3]}),
        encoding="utf-8",
    )

    findings = _answered(outcome=plugin_artifact_findings(install_path=str(plugin)))

    assert len(findings) == 4


def test_plugin_artifact_findings_report_an_undecodable_cache_manifest(*, tmp_path: Path) -> None:
    """Bytes that are not UTF-8 leave the required-path set unknown, not empty."""
    plugin = _plugin_dir(tmp_path=tmp_path, name="plugin")
    (plugin / "cache-manifest.json").write_bytes(b"\xff\xfe\x00 not utf-8")

    outcome = plugin_artifact_findings(install_path=str(plugin))

    assert isinstance(outcome, IOFailure)
    assert unsafe_perform_io(outcome.failure()).reason == MANIFEST_UNDECODABLE


def test_plugin_artifact_findings_report_an_unparseable_cache_manifest(*, tmp_path: Path) -> None:
    """Text that is not JSON used to escape as a traceback out of the whole run."""
    plugin = _plugin_dir(tmp_path=tmp_path, name="plugin")
    (plugin / "cache-manifest.json").write_text("{ not json", encoding="utf-8")

    outcome = plugin_artifact_findings(install_path=str(plugin))

    assert isinstance(outcome, IOFailure)
    unreadable = unsafe_perform_io(outcome.failure())
    assert unreadable.reason == MANIFEST_UNPARSEABLE
    assert str(plugin) in unreadable.finding


def test_the_two_manifest_non_answers_stay_told_apart() -> None:
    """Truncated bytes and non-JSON text call for the same repair, not the same word."""
    assert MANIFEST_UNDECODABLE != MANIFEST_UNPARSEABLE


def test_remove_plugin_cache_dir_reports_the_path_it_removed(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A removal that HAPPENED carries its path, not the empty tuple a refusal did."""
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    doomed = _cache_plugin_dir(home=home, name="doomed")

    outcome = remove_plugin_cache_dir(install_path=str(doomed))

    assert not isinstance(outcome, IOFailure)
    assert unsafe_perform_io(outcome.unwrap()) == str(doomed.resolve())
    assert not doomed.exists()


def test_remove_plugin_cache_dir_refuses_a_path_outside_the_cache(*, tmp_path: Path) -> None:
    """The refusal is this seam's own error, not a finding about any plugin."""
    outside = _plugin_dir(tmp_path=tmp_path, name="outside")

    outcome = remove_plugin_cache_dir(install_path=str(outside))

    assert isinstance(outcome, IOFailure)
    assert "refusing to delete" in unsafe_perform_io(outcome.failure()).finding
    assert outside.exists()


def test_artifact_record_findings_forward_a_probe_that_did_not_answer() -> None:
    """The reader's failure travels unchanged: this function adds no failure of its own."""
    outcome = artifact_record_findings(
        plugin="one@alpha",
        records=({"installPath": "/cache/one"},),
        read_artifact=_unanswered,
    )

    assert isinstance(outcome, IOFailure)
    assert unsafe_perform_io(outcome.failure()).install_path == "/cache/one"


def test_artifact_record_repair_paths_withhold_every_path_when_a_probe_did_not_answer() -> None:
    """Whatever this returns gets DELETED, so an unanswered probe returns nothing at all."""
    outcome = artifact_record_repair_paths(
        records=({"installPath": "/cache/one"},),
        read_artifact=_unanswered,
    )

    assert isinstance(outcome, IOFailure)


def test_ensure_returns_no_findings_when_provisioning_succeeds(*, tmp_path: Path) -> None:
    registry = _registry(
        entries={
            "one@alpha": [
                {
                    "projectPath": "/repo",
                    "installPath": str(_plugin_dir(tmp_path=tmp_path, name="one")),
                }
            ],
            "two@beta": [
                {
                    "projectPath": "/repo",
                    "installPath": str(_plugin_dir(tmp_path=tmp_path, name="two")),
                }
            ],
        }
    )
    ran: list[tuple[str, ...]] = []

    def runner(*, args: tuple[str, ...]) -> PluginCommandOutcome:
        ran.append(args)
        return _ran(returncode=0)

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

    def runner(*, args: tuple[str, ...]) -> PluginCommandOutcome:  # pragma: no cover
        ran.append(args)
        return _ran(returncode=0)

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

    def runner(*, args: tuple[str, ...]) -> PluginCommandOutcome:
        ran.append(args)
        return _ran(returncode=0)

    findings = ensure(
        settings_text=_M3,
        project_root="/repo",
        runner=runner,
        read_registry=lambda: _registry(entries={}),
    )
    assert findings != ()
    assert any("one@alpha" in f for f in findings)


def test_ensure_reports_when_record_names_empty_artifact(*, tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    registry = _registry(
        entries={
            "one@alpha": [{"projectPath": "/repo", "installPath": str(empty)}],
            "two@beta": [
                {
                    "projectPath": "/repo",
                    "installPath": str(_plugin_dir(tmp_path=tmp_path, name="two")),
                }
            ],
        }
    )
    ran: list[tuple[str, ...]] = []

    def runner(*, args: tuple[str, ...]) -> PluginCommandOutcome:
        ran.append(args)
        return _ran(returncode=0)

    findings = ensure(
        settings_text=_M3,
        project_root="/repo",
        runner=runner,
        read_registry=lambda: registry,
    )

    assert findings != ()
    assert ran == list(planned_commands(settings_text=_M3))


def test_ensure_repairs_incomplete_cache_once(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    broken = _cache_plugin_dir(home=home, name="broken")
    _write_cache_manifest(plugin=broken, required_paths=["scripts/bin"])
    fixed_one = _cache_plugin_dir(home=home, name="fixed-one")
    fixed_two = _cache_plugin_dir(home=home, name="fixed-two")
    registries = [
        _registry(
            entries={
                "one@alpha": [{"projectPath": "/repo", "installPath": str(broken)}],
                "two@beta": [{"projectPath": "/repo", "installPath": str(fixed_two)}],
            }
        ),
        _registry(
            entries={
                "one@alpha": [{"projectPath": "/repo", "installPath": str(fixed_one)}],
                "two@beta": [{"projectPath": "/repo", "installPath": str(fixed_two)}],
            }
        ),
    ]
    ran: list[tuple[str, ...]] = []

    def runner(*, args: tuple[str, ...]) -> PluginCommandOutcome:
        ran.append(args)
        return _ran(returncode=0)

    findings = ensure(
        settings_text=_M3,
        project_root="/repo",
        runner=runner,
        read_registry=lambda: registries.pop(0),
    )

    assert findings == ()
    assert ran == list(planned_commands(settings_text=_M3)) * 2
    assert not broken.exists()


def test_ensure_returns_second_findings_when_repair_still_fails(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    broken = _cache_plugin_dir(home=home, name="broken")
    _write_cache_manifest(plugin=broken, required_paths=["scripts/bin"])
    valid = _cache_plugin_dir(home=home, name="valid")
    registry = _registry(
        entries={
            "one@alpha": [{"projectPath": "/repo", "installPath": str(broken)}],
            "two@beta": [{"projectPath": "/repo", "installPath": str(valid)}],
        }
    )
    ran: list[tuple[str, ...]] = []

    def runner(*, args: tuple[str, ...]) -> PluginCommandOutcome:
        ran.append(args)
        return _ran(returncode=0)

    findings = ensure(
        settings_text=_M3,
        project_root="/repo",
        runner=runner,
        read_registry=lambda: registry,
    )

    assert any("one@alpha" in finding and "does not exist" in finding for finding in findings)
    assert ran == list(planned_commands(settings_text=_M3)) * 2


def test_ensure_refuses_to_delete_install_path_outside_cache(*, tmp_path: Path) -> None:
    outside = _plugin_dir(tmp_path=tmp_path, name="outside")
    _write_cache_manifest(plugin=outside, required_paths=["scripts/bin"])
    valid = _plugin_dir(tmp_path=tmp_path, name="valid")
    registry = _registry(
        entries={
            "one@alpha": [{"projectPath": "/repo", "installPath": str(outside)}],
            "two@beta": [{"projectPath": "/repo", "installPath": str(valid)}],
        }
    )
    ran: list[tuple[str, ...]] = []

    def runner(*, args: tuple[str, ...]) -> PluginCommandOutcome:
        ran.append(args)
        return _ran(returncode=0)

    findings = ensure(
        settings_text=_M3,
        project_root="/repo",
        runner=runner,
        read_registry=lambda: registry,
    )

    assert any("refusing to delete" in finding for finding in findings)
    assert ran == list(planned_commands(settings_text=_M3))
    assert outside.exists()


def test_registry_findings_report_a_probe_that_did_not_answer(*, tmp_path: Path) -> None:
    """An unanswered probe is REPORTED, never dropped into the empty finding set."""
    registry = _registry(
        entries={
            "one@alpha": [{"projectPath": "/repo", "installPath": "/cache/one"}],
            "two@beta": [
                {
                    "projectPath": "/repo",
                    "installPath": str(_plugin_dir(tmp_path=tmp_path, name="two")),
                }
            ],
        }
    )

    findings = registry_findings(
        settings_text=_M3,
        project_root="/repo",
        registry_text=registry,
        read_artifact=_unanswered,
    )

    assert any(
        "one@alpha" in finding and "could not be inspected" in finding for finding in findings
    )


def test_ensure_deletes_nothing_when_a_probe_did_not_answer(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """THE POINT OF THE FAILURE TRACK: a probe with no verdict authorizes no delete.

    The cache directory below is inside the cache root and would be removed on
    the strength of any non-empty finding set, which is exactly what an
    unanswered probe used to be indistinguishable from.
    """
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    survivor = _cache_plugin_dir(home=home, name="survivor")
    registry = _registry(
        entries={
            "one@alpha": [{"projectPath": "/repo", "installPath": str(survivor)}],
            "two@beta": [{"projectPath": "/repo", "installPath": str(survivor)}],
        }
    )
    ran: list[tuple[str, ...]] = []

    def runner(*, args: tuple[str, ...]) -> PluginCommandOutcome:
        ran.append(args)
        return _ran(returncode=0)

    findings = ensure(
        settings_text=_M3,
        project_root="/repo",
        runner=runner,
        read_registry=lambda: registry,
        read_artifact=_unanswered,
    )

    assert any("could not be inspected" in finding for finding in findings)
    assert survivor.exists()


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

    def runner(*, args: tuple[str, ...]) -> PluginCommandOutcome:
        ran.append(args)
        return _ran(returncode=9)

    findings = ensure(
        settings_text=_M3,
        project_root="/repo",
        runner=runner,
        read_registry=lambda: None,
    )
    assert any("exit 9" in f for f in findings)
    assert len(ran) == 1
