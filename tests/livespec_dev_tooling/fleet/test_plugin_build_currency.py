"""Tests for `livespec_dev_tooling.fleet.plugin_build_currency` and its pure core.

The load-bearing assertions here are the NEGATIVE ones. A currency probe whose
failure mode is silence needs its absence paths pinned harder than its happy
path: every missing, malformed, or unreadable input must land on
`CURRENCY_UNDETERMINABLE` and NEVER on `CURRENCY_CURRENT`, and the record
selection must be keyed on `projectPath` rather than on list order — the `e01t`
defect, which is invisible in a passing run because the wrong record is
perfectly well-formed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Final

import pytest
from returns.io import IOFailure, IOSuccess

from livespec_dev_tooling.fleet._invocation_failure import BINARY_ABSENT, InvocationNotPerformed
from livespec_dev_tooling.fleet._local_context import CommandOutcome, CommandResult, CommandRunner
from livespec_dev_tooling.fleet._plugin_build_currency_core import (
    build_currency,
    resolved_build,
    unresolved_build,
)
from livespec_dev_tooling.fleet._plugin_build_currency_reads import (
    PinnedSource,
    governed_pins,
    served_build_identifier,
)
from livespec_dev_tooling.fleet.plugin_build_currency import (
    CURRENCY_CURRENT,
    CURRENCY_STALE,
    CURRENCY_UNDETERMINABLE,
    currency_exit_code,
    expected_build_identifier,
    main,
    plugin_currencies,
)

__all__: list[str] = []

_PLUGIN: Final = "alpha@alpha"
_MARKETPLACE: Final = "alpha"
_ROOT: Final = "/repo"
_BUILD_A: Final = "1234567890abcdef1234567890abcdef12345678"
_BUILD_B: Final = "fedcba0987654321fedcba0987654321fedcba09"


def _pin(*, ref: str = "release", unresolved: str = "") -> PinnedSource:
    """A pin naming the `alpha` marketplace, resolved unless told otherwise."""
    return PinnedSource(
        plugin=_PLUGIN,
        marketplace=_MARKETPLACE,
        repo="acme/alpha",
        ref=ref,
        unresolved=unresolved,
    )


def _recording_runner(
    *, returncode: int = 0, stdout: str = "", stderr: str = "", never_ran: bool = False
) -> tuple[CommandRunner, list[list[str]]]:
    """A `CommandRunner` fake plus the argv list it recorded, for no-network proof."""
    calls: list[list[str]] = []

    def run(*, args: list[str], cwd: Path | None = None) -> CommandOutcome:
        del cwd
        calls.append(args)
        if never_ran:
            return IOFailure(
                InvocationNotPerformed(
                    argv=tuple(args), kind=BINARY_ABSENT, detail="git not on PATH"
                )
            )
        return IOSuccess(CommandResult(returncode=returncode, stdout=stdout, stderr=stderr))

    return (run, calls)


def _settings_text(*, ref: str = "release") -> str:
    """A governed settings file enabling one plugin from one pinned marketplace."""
    return json.dumps(
        {
            "enabledPlugins": {_PLUGIN: True},
            "extraKnownMarketplaces": {
                _MARKETPLACE: {"source": {"source": "github", "repo": "acme/alpha", "ref": ref}}
            },
        }
    )


def _registry_text(*, records: list[object]) -> str:
    """A v2 installed-plugins registry listing `records` under the enabled plugin."""
    return json.dumps({"version": 2, "plugins": {_PLUGIN: records}})


def test_a_matching_pair_is_current() -> None:
    """Equal full shas on both sides is the ONE shape that reports health."""
    currency = build_currency(
        plugin=_PLUGIN, served=resolved_build(sha=_BUILD_A), expected=resolved_build(sha=_BUILD_A)
    )

    assert currency.verdict == CURRENCY_CURRENT
    assert currency.served == _BUILD_A
    assert currency.expected == _BUILD_A


def test_a_differing_pair_is_stale() -> None:
    """Two readable builds that disagree is a verdict about the BUILD, not the probe."""
    currency = build_currency(
        plugin=_PLUGIN, served=resolved_build(sha=_BUILD_A), expected=resolved_build(sha=_BUILD_B)
    )

    assert currency.verdict == CURRENCY_STALE
    assert currency.served == _BUILD_A
    assert currency.expected == _BUILD_B


def test_an_unresolved_served_side_is_undeterminable_and_never_current() -> None:
    """No install record is the absence that must not be reported as health."""
    currency = build_currency(
        plugin=_PLUGIN,
        served=unresolved_build(detail="no install record"),
        expected=resolved_build(sha=_BUILD_A),
    )

    assert currency.verdict == CURRENCY_UNDETERMINABLE
    assert currency.verdict != CURRENCY_CURRENT
    assert "served build unresolved: no install record" in currency.detail


def test_an_unresolved_expected_side_is_undeterminable_and_never_current() -> None:
    """A source clone that answered nothing is undeterminable, NOT stale."""
    currency = build_currency(
        plugin=_PLUGIN,
        served=resolved_build(sha=_BUILD_A),
        expected=unresolved_build(detail="no source clone"),
    )

    assert currency.verdict == CURRENCY_UNDETERMINABLE
    assert currency.verdict != CURRENCY_STALE
    assert "expected build unresolved: no source clone" in currency.detail


def test_an_abbreviated_served_sha_is_undeterminable_rather_than_stale() -> None:
    """A 12-hex id cannot decide an exact match, so it refuses instead of guessing."""
    currency = build_currency(
        plugin=_PLUGIN,
        served=resolved_build(sha=_BUILD_A[:12]),
        expected=resolved_build(sha=_BUILD_A),
    )

    assert currency.verdict == CURRENCY_UNDETERMINABLE
    assert "not a full commit sha" in currency.detail


def test_resolved_build_normalizes_case_and_surrounding_whitespace() -> None:
    """`git rev-parse` output arrives with a trailing newline; that is not a mismatch."""
    currency = build_currency(
        plugin=_PLUGIN,
        served=resolved_build(sha=_BUILD_A.upper()),
        expected=resolved_build(sha=f"{_BUILD_A}\n"),
    )

    assert currency.verdict == CURRENCY_CURRENT


def test_the_report_line_names_the_plugin_the_verdict_and_both_sides() -> None:
    """A verdict word alone is unactionable; the line carries what was compared."""
    line = build_currency(
        plugin=_PLUGIN, served=resolved_build(sha=_BUILD_A), expected=resolved_build(sha=_BUILD_B)
    ).line

    assert line.startswith(f"{_PLUGIN} {CURRENCY_STALE}:")
    assert f"served={_BUILD_A}" in line
    assert f"expected={_BUILD_B}" in line


def test_the_report_line_marks_a_side_that_produced_no_identifier() -> None:
    """An empty sha renders as `<unresolved>` rather than as a blank a reader skips."""
    line = build_currency(
        plugin=_PLUGIN,
        served=unresolved_build(detail="no install record"),
        expected=unresolved_build(detail="no install record"),
    ).line

    assert "served=<unresolved>" in line
    assert "expected=<unresolved>" in line


def test_served_build_is_unresolved_without_a_registry() -> None:
    """An absent registry file is an absence, and absence never resolves a build."""
    served = served_build_identifier(registry_text=None, plugin=_PLUGIN, project_root=_ROOT)

    assert served.sha == ""
    assert served.unresolved == "no installed-plugins registry to read"


def test_served_build_is_unresolved_when_the_registry_is_not_json() -> None:
    """Truncated registry bytes are reported, not swallowed as an empty answer."""
    served = served_build_identifier(registry_text="{", plugin=_PLUGIN, project_root=_ROOT)

    assert served.sha == ""
    assert "is not JSON" in served.unresolved


def test_served_build_is_unresolved_when_the_registry_is_not_an_object() -> None:
    """A JSON array where an object belongs carries no plugin map to read."""
    served = served_build_identifier(registry_text="[]", plugin=_PLUGIN, project_root=_ROOT)

    assert served.unresolved == f"no install record has projectPath {_ROOT}"


def test_served_build_is_unresolved_when_the_plugins_map_is_not_an_object() -> None:
    """A `plugins` value of the wrong shape yields no records for any plugin."""
    served = served_build_identifier(
        registry_text=json.dumps({"plugins": 5}), plugin=_PLUGIN, project_root=_ROOT
    )

    assert served.unresolved == f"no install record has projectPath {_ROOT}"


def test_served_build_is_unresolved_when_the_plugin_entries_are_not_a_list() -> None:
    """The per-plugin value is a LIST of install records; anything else is unreadable."""
    served = served_build_identifier(
        registry_text=json.dumps({"plugins": {_PLUGIN: 5}}), plugin=_PLUGIN, project_root=_ROOT
    )

    assert served.unresolved == f"no install record has projectPath {_ROOT}"


def test_served_build_ignores_records_for_another_project_and_non_records() -> None:
    """A record for a DIFFERENT checkout answers nothing about this one."""
    served = served_build_identifier(
        registry_text=_registry_text(
            records=[5, {"projectPath": "/elsewhere", "gitCommitSha": _BUILD_B}]
        ),
        plugin=_PLUGIN,
        project_root=_ROOT,
    )

    assert served.sha == ""
    assert served.unresolved == f"no install record has projectPath {_ROOT}"


def test_served_build_reads_the_record_for_the_governed_root_not_the_first_entry() -> None:
    """The `e01t` regression: entry order must not decide whose build is reported."""
    served = served_build_identifier(
        registry_text=_registry_text(
            records=[
                {"projectPath": "/elsewhere", "gitCommitSha": _BUILD_B},
                {"projectPath": _ROOT, "gitCommitSha": _BUILD_A},
            ]
        ),
        plugin=_PLUGIN,
        project_root=_ROOT,
    )

    assert served.sha == _BUILD_A
    assert served.unresolved == ""


def test_served_build_is_unresolved_when_the_matching_record_names_no_build() -> None:
    """An install that landed and recorded no build id is its own distinct answer."""
    served = served_build_identifier(
        registry_text=_registry_text(
            records=[{"projectPath": _ROOT}, {"projectPath": _ROOT, "gitCommitSha": "  "}]
        ),
        plugin=_PLUGIN,
        project_root=_ROOT,
    )

    assert served.sha == ""
    assert served.unresolved == (f"the install record for projectPath {_ROOT} has no gitCommitSha")


def test_served_build_is_unresolved_when_matching_records_disagree() -> None:
    """Two builds served to one project root is a state no single verdict describes."""
    served = served_build_identifier(
        registry_text=_registry_text(
            records=[
                {"projectPath": _ROOT, "gitCommitSha": _BUILD_A},
                {"projectPath": _ROOT, "gitCommitSha": _BUILD_B},
            ]
        ),
        plugin=_PLUGIN,
        project_root=_ROOT,
    )

    assert "disagree on gitCommitSha" in served.unresolved


def test_served_build_accepts_agreeing_duplicate_records() -> None:
    """Duplicate records naming the SAME build are one answer, not a disagreement."""
    served = served_build_identifier(
        registry_text=_registry_text(
            records=[
                {"projectPath": _ROOT, "gitCommitSha": _BUILD_A.upper()},
                {"projectPath": _ROOT, "gitCommitSha": _BUILD_A},
            ]
        ),
        plugin=_PLUGIN,
        project_root=_ROOT,
    )

    assert served.sha == _BUILD_A


def test_governed_pins_reports_a_settings_file_that_is_not_json() -> None:
    """The unreadable reason belongs to the FILE, so it is carried once."""
    pins = governed_pins(settings_text="{")

    assert pins.sources == ()
    assert "is not JSON" in pins.unreadable


def test_governed_pins_reports_a_settings_file_that_is_not_an_object() -> None:
    """A settings array declares no marketplaces and enables no plugins."""
    pins = governed_pins(settings_text="[]")

    assert pins.unreadable == ".claude/settings.json must contain a JSON object"


def test_governed_pins_reports_an_unreadable_enablement_shape() -> None:
    """The enablement shape finding comes from the reader both provisioners share."""
    pins = governed_pins(settings_text=json.dumps({"enabledPlugins": 5}))

    assert pins.sources == ()
    assert pins.unreadable != ""


def test_governed_pins_reports_an_enabled_plugin_with_no_declared_marketplace() -> None:
    """An enablement whose marketplace is undeclared has no ref to resolve."""
    pins = governed_pins(settings_text=json.dumps({"enabledPlugins": {_PLUGIN: True}}))

    assert pins.unreadable == ""
    assert len(pins.sources) == 1
    assert "declares no source for marketplace" in pins.sources[0].unresolved


def test_governed_pins_reports_a_marketplace_declaring_no_source() -> None:
    """A marketplace entry without a `source` object pins nothing."""
    pins = governed_pins(
        settings_text=json.dumps(
            {"enabledPlugins": {_PLUGIN: True}, "extraKnownMarketplaces": {_MARKETPLACE: {}}}
        )
    )

    assert "declares no source for marketplace" in pins.sources[0].unresolved


def test_governed_pins_reports_a_source_missing_its_repo_and_ref_pair() -> None:
    """Both halves are required: a ref with no repo names no clone to resolve in."""
    pins = governed_pins(
        settings_text=json.dumps(
            {
                "enabledPlugins": {_PLUGIN: True},
                "extraKnownMarketplaces": {_MARKETPLACE: {"source": {"ref": "release"}}},
            }
        )
    )

    assert pins.sources[0].unresolved == "marketplace 'alpha' declares no repo and ref pair"


def test_governed_pins_pairs_each_enabled_plugin_with_its_pin() -> None:
    """The happy path: one pin per enabled plugin, carrying marketplace, repo and ref."""
    pins = governed_pins(settings_text=_settings_text())

    assert pins.unreadable == ""
    assert pins.sources == (
        PinnedSource(
            plugin=_PLUGIN,
            marketplace=_MARKETPLACE,
            repo="acme/alpha",
            ref="release",
            unresolved="",
        ),
    )


def test_expected_build_forwards_an_unresolved_pin_without_invoking_git(*, tmp_path: Path) -> None:
    """A pin nobody could read is not a question git can be asked."""
    run, calls = _recording_runner()

    expected = expected_build_identifier(
        marketplaces_root=tmp_path, pin=_pin(unresolved="no pin"), run=run
    )

    assert expected.unresolved == "no pin"
    assert calls == []


def test_expected_build_is_unresolved_when_git_never_ran(*, tmp_path: Path) -> None:
    """A host without git is a host problem, and it decides nothing about the build."""
    run, _calls = _recording_runner(never_ran=True)

    expected = expected_build_identifier(marketplaces_root=tmp_path, pin=_pin(), run=run)

    assert expected.sha == ""
    assert BINARY_ABSENT in expected.unresolved


def test_expected_build_is_unresolved_when_rev_parse_refuses(*, tmp_path: Path) -> None:
    """An absent clone or an unfetched ref exits non-zero and reports its own reason."""
    run, _calls = _recording_runner(returncode=128, stderr="fatal: bad revision\n")

    expected = expected_build_identifier(marketplaces_root=tmp_path, pin=_pin(), run=run)

    assert expected.sha == ""
    assert "exited 128: fatal: bad revision" in expected.unresolved
    assert "acme/alpha" in expected.unresolved


def test_expected_build_resolves_the_pinned_ref_locally_with_no_network_call(
    *, tmp_path: Path
) -> None:
    """`rev-parse origin/<ref>` reads an on-disk ref; nothing reaches GitHub."""
    run, calls = _recording_runner(stdout=f"{_BUILD_A}\n")

    expected = expected_build_identifier(marketplaces_root=tmp_path, pin=_pin(), run=run)

    assert expected.sha == _BUILD_A
    assert calls == [
        [
            "git",
            "-C",
            str(tmp_path / _MARKETPLACE),
            "rev-parse",
            "--verify",
            "origin/release",
        ]
    ]


def test_plugin_currencies_compares_served_bytes_against_the_resolved_expected_build(
    *, tmp_path: Path
) -> None:
    """The end-to-end pure path: registry sha versus locally resolved ref."""
    run, _calls = _recording_runner(stdout=_BUILD_A)

    currencies = plugin_currencies(
        settings_text=_settings_text(),
        project_root=_ROOT,
        registry_text=_registry_text(records=[{"projectPath": _ROOT, "gitCommitSha": _BUILD_A}]),
        marketplaces_root=tmp_path,
        run=run,
    )

    assert [(c.plugin, c.verdict) for c in currencies] == [(_PLUGIN, CURRENCY_CURRENT)]


def test_plugin_currencies_reports_a_stale_served_build(*, tmp_path: Path) -> None:
    """A served build the pinned ref has moved past is the staleness this probe adds."""
    run, _calls = _recording_runner(stdout=_BUILD_A)

    currencies = plugin_currencies(
        settings_text=_settings_text(),
        project_root=_ROOT,
        registry_text=_registry_text(records=[{"projectPath": _ROOT, "gitCommitSha": _BUILD_B}]),
        marketplaces_root=tmp_path,
        run=run,
    )

    assert [c.verdict for c in currencies] == [CURRENCY_STALE]


def test_plugin_currencies_reports_an_unreadable_settings_file_as_one_verdict(
    *, tmp_path: Path
) -> None:
    """An unreadable settings file yields a verdict, never the empty tuple."""
    run, _calls = _recording_runner()

    currencies = plugin_currencies(
        settings_text="{",
        project_root=_ROOT,
        registry_text=None,
        marketplaces_root=tmp_path,
        run=run,
    )

    assert [(c.plugin, c.verdict) for c in currencies] == [
        (".claude/settings.json", CURRENCY_UNDETERMINABLE)
    ]


def test_currency_exit_code_is_zero_only_when_every_plugin_measured_current() -> None:
    """One undeterminable plugin moves the exit code exactly as a stale one does."""
    current = build_currency(
        plugin=_PLUGIN, served=resolved_build(sha=_BUILD_A), expected=resolved_build(sha=_BUILD_A)
    )
    undeterminable = build_currency(
        plugin="beta@beta",
        served=unresolved_build(detail="no install record"),
        expected=resolved_build(sha=_BUILD_A),
    )

    assert currency_exit_code(currencies=(current,)) == 0
    assert currency_exit_code(currencies=(current, undeterminable)) == 4


def test_currency_exit_code_refuses_a_run_that_measured_nothing() -> None:
    """Nothing measured is not nothing wrong; the empty tuple is not a pass."""
    assert currency_exit_code(currencies=()) == 4


def test_main_reports_a_precondition_failure_for_a_vacuous_settings_file(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A settings file that enables nothing cannot support a comparison at all."""
    project = tmp_path / "repo"
    (project / ".claude").mkdir(parents=True)
    (project / ".claude" / "settings.json").write_text(
        json.dumps({"extraKnownMarketplaces": {_MARKETPLACE: {}}}), encoding="utf-8"
    )
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.chdir(project)

    assert main() == 3
    assert "no plugin is enabled" in capsys.readouterr().err


def test_main_reports_undeterminable_when_the_host_has_no_registry(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A host that never recorded an install is reported, never passed."""
    project = tmp_path / "repo"
    (project / ".claude").mkdir(parents=True)
    (project / ".claude" / "settings.json").write_text(_settings_text(), encoding="utf-8")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.chdir(project)

    exit_code = main()

    assert exit_code == 4
    err = capsys.readouterr().err
    assert CURRENCY_UNDETERMINABLE in err
    assert "no installed-plugins registry to read" in err


def test_main_reads_the_install_record_for_the_current_project_root(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """With a registry present the served sha reaches the report, keyed on this root."""
    project = tmp_path / "repo"
    (project / ".claude").mkdir(parents=True)
    (project / ".claude" / "settings.json").write_text(_settings_text(), encoding="utf-8")
    home = tmp_path / "home"
    (home / ".claude" / "plugins").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(project)
    root = Path.cwd()
    (home / ".claude" / "plugins" / "installed_plugins.json").write_text(
        _registry_text(records=[{"projectPath": str(root), "gitCommitSha": _BUILD_A}]),
        encoding="utf-8",
    )

    exit_code = main()

    err = capsys.readouterr().err
    assert exit_code == 4
    assert f"served={_BUILD_A}" in err
