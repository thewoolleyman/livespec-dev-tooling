"""Currency failures must reconcile, and CLI timings must retain every outcome."""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest
from returns.io import IOFailure, IOSuccess

from livespec_dev_tooling.fleet import ensure_plugins
from livespec_dev_tooling.fleet._ensure_plugin_commands import PluginCommandResult
from livespec_dev_tooling.fleet._invocation_failure import BINARY_ABSENT, InvocationNotPerformed
from livespec_dev_tooling.fleet._plugin_startup import (
    _logged_runner,
    _remote_commit,
    _startup_currency,
)

_SHA = "a" * 40
_SOURCE = {"source": "github", "repo": "acme/alpha", "ref": "release"}


def _fixture(tmp_path: Path):
    marketplace = tmp_path / "marketplace"
    marketplace.mkdir()
    settings = {
        "enabledPlugins": {"one@alpha": True, "disabled@alpha": False},
        "extraKnownMarketplaces": {"alpha": {"source": dict(_SOURCE)}},
    }
    registry = {
        "plugins": {
            "one@alpha": [{"scope": "project", "projectPath": "/repo", "gitCommitSha": _SHA}]
        }
    }
    known = {"alpha": {"source": dict(_SOURCE), "installLocation": str(marketplace)}}
    return settings, registry, known


@pytest.mark.parametrize(
    "change",
    [
        "current",
        "sha",
        "scope",
        "project",
        "no-record",
        "ref",
        "missing-directory",
        "unknown-ref",
        "legacy-list",
    ],
)
def test_only_exact_project_and_source_commits_are_current(tmp_path: Path, change: str):
    settings, registry, known = _fixture(tmp_path)
    record = registry["plugins"]["one@alpha"][0]
    if change == "sha":
        record["gitCommitSha"] = "b" * 40
    if change == "scope":
        record["scope"] = "user"
    if change == "project":
        record["projectPath"] = "/different"
    if change == "no-record":
        registry["plugins"]["one@alpha"] = None
    if change == "ref":
        known["alpha"]["source"]["ref"] = "other"
    if change == "missing-directory":
        known["alpha"]["installLocation"] = str(tmp_path / "absent")
    if change == "legacy-list":
        settings["enabledPlugins"] = ["one@alpha", 8]
    current, registered = _startup_currency(
        settings_text=json.dumps(settings),
        registry_text=json.dumps(registry),
        marketplaces_text=json.dumps(known),
        project_root="/repo",
        resolve_ref=lambda **_: None if change == "unknown-ref" else _SHA,
    )
    assert current == (
        frozenset({"one@alpha"}) if change in {"current", "legacy-list"} else frozenset()
    )
    assert registered == (
        frozenset() if change in {"ref", "missing-directory"} else frozenset({"acme/alpha@release"})
    )


@pytest.mark.parametrize("value", [None, "{", "[]", "{}"])
def test_unreadable_or_missing_metadata_never_certifies_current(tmp_path: Path, value):
    settings, _, known = _fixture(tmp_path)
    current, _ = _startup_currency(
        settings_text=json.dumps(settings),
        registry_text=value,
        marketplaces_text=json.dumps(known),
        project_root="/repo",
        resolve_ref=lambda **_: _SHA,
    )
    assert current == frozenset()
    assert _startup_currency(
        settings_text=json.dumps(settings),
        registry_text="{}",
        marketplaces_text=value,
        project_root="/repo",
    ) == (frozenset(), frozenset())


@pytest.mark.parametrize(
    "source",
    [
        None,
        {},
        {"source": "directory"},
        {"source": "github", "repo": 8, "ref": "release"},
        {"source": "github", "repo": "acme/alpha", "ref": 8},
    ],
)
def test_unrecognized_registrations_require_the_cli(tmp_path: Path, source):
    settings, registry, known = _fixture(tmp_path)
    settings["extraKnownMarketplaces"]["alpha"]["source"] = source
    assert _startup_currency(
        settings_text=json.dumps(settings),
        registry_text=json.dumps(registry),
        marketplaces_text=json.dumps(known),
        project_root="/repo",
    ) == (frozenset(), frozenset())


@pytest.mark.parametrize(
    ("output", "expected"),
    [
        (f"{_SHA}\trefs/heads/release\n", _SHA),
        (f"{_SHA}\trefs/tags/release\n", _SHA),
        (f'{"b" * 40}\trefs/tags/release\n{_SHA}\trefs/tags/release^{{}}\n', _SHA),
        ("not-a-sha\trefs/heads/release\n", None),
        ("malformed\n", None),
        ("", None),
    ],
)
def test_ref_probe_handles_branches_and_tags_and_rejects_unknown_answers(
    monkeypatch, output, expected
):
    def run(args, **kwargs):
        assert args[:2] == ["git", "ls-remote"]
        assert kwargs["timeout"] == 5
        assert kwargs["env"]["GIT_TERMINAL_PROMPT"] == "0"
        return subprocess.CompletedProcess(args, 0, stdout=output)

    monkeypatch.setattr(subprocess, "run", run)
    assert _remote_commit(source=dict(_SOURCE)) == expected


@pytest.mark.parametrize("error", [OSError("cannot spawn"), subprocess.TimeoutExpired("git", 5)])
def test_probe_failure_withholds_currency(monkeypatch, error):
    def run(*_args, **_kwargs):
        raise error

    monkeypatch.setattr(subprocess, "run", run)
    assert _remote_commit(source=dict(_SOURCE)) is None


def test_git_refusal_withholds_currency(monkeypatch):
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **_kw: subprocess.CompletedProcess(a, 128, stdout="")
    )
    assert _remote_commit(source=dict(_SOURCE)) is None


@pytest.mark.parametrize(
    "source",
    [
        {},
        {"repo": 8, "ref": "release"},
        {"repo": "acme/alpha", "ref": ""},
        {"repo": "../alpha", "ref": "release"},
        {"repo": "https://elsewhere/repo", "ref": "release"},
    ],
)
def test_unsupported_sources_cannot_trigger_a_freshness_probe(monkeypatch, source):
    def run(*_args, **_kwargs):  # pragma: no cover
        pytest.fail("unexpected network call")

    monkeypatch.setattr(subprocess, "run", run)
    assert _remote_commit(source=source) is None


def test_immutable_commit_pin_needs_no_network(monkeypatch):
    def run(*_args, **_kwargs):  # pragma: no cover
        pytest.fail("immutable identity must not fetch")

    monkeypatch.setattr(subprocess, "run", run)
    assert _remote_commit(source={**_SOURCE, "ref": "A" * 40}) == _SHA


@pytest.mark.parametrize("invoked", [True, False])
def test_timing_log_preserves_refusals_and_non_invocations(
    *, tmp_path: Path, monkeypatch, invoked: bool
):
    monkeypatch.setenv("HOME", str(tmp_path))
    args = ("claude", "plugin", "update", "one@alpha", "-s", "project")
    result = (
        IOSuccess(PluginCommandResult(returncode=17))
        if invoked
        else IOFailure(InvocationNotPerformed(argv=args, kind=BINARY_ABSENT, detail="missing"))
    )
    assert _logged_runner(args=args, runner=lambda **_kw: result) is result
    path = tmp_path / ".local/state/livespec-dev-tooling/plugin-commands.jsonl"
    records = [json.loads(line) for line in path.read_text().splitlines()]
    assert [r["event"] for r in records] == ["command-start", "command-end"]
    assert records[1]["returncode"] == (17 if invoked else None)
    assert records[1]["invoked"] is invoked
    assert records[1]["elapsed_seconds"] >= 0
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert all(set(r).isdisjoint({"stdout", "stderr", "env"}) for r in records)


def test_logging_failure_does_not_change_the_command_outcome(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".local").write_text("not a directory")
    result = IOSuccess(PluginCommandResult(returncode=17))
    assert _logged_runner(args=("claude",), runner=lambda **_kw: result) is result
    assert "timing log unavailable" in capsys.readouterr().err


@pytest.mark.integration
@pytest.mark.parametrize("broken", [False, True])
def test_shipped_cli_skips_current_commands_and_still_repairs_broken_cache(
    *, tmp_path: Path, broken: bool, monkeypatch: pytest.MonkeyPatch
):
    home, project, bin_dir = (tmp_path / name for name in ["home", "project", "bin"])
    plugins = home / ".claude/plugins"
    cache = plugins / "cache/alpha/one/1.0.0"
    marketplace = plugins / "marketplaces/alpha"
    for p in [cache, marketplace, project / ".claude", bin_dir]:
        p.mkdir(parents=True)
    if not broken:
        (cache / "plugin.json").write_text("{}")
    settings = {
        "enabledPlugins": {"one@alpha": True},
        "extraKnownMarketplaces": {"alpha": {"source": _SOURCE}},
    }
    (project / ".claude/settings.json").write_text(json.dumps(settings))
    (plugins / "known_marketplaces.json").write_text(
        json.dumps({"alpha": {"source": _SOURCE, "installLocation": str(marketplace)}})
    )
    (plugins / "installed_plugins.json").write_text(
        json.dumps(
            {
                "plugins": {
                    "one@alpha": [
                        {
                            "projectPath": str(project),
                            "scope": "project",
                            "gitCommitSha": _SHA,
                            "installPath": str(cache),
                        }
                    ]
                }
            }
        )
    )
    git = bin_dir / "git"
    git.write_text(f'#!/bin/sh\nprintf "%s\\trefs/heads/release\\n" {_SHA}\n')
    cli = bin_dir / "claude"
    cli.write_text(
        f"#!{sys.executable}\nimport pathlib,sys\np=pathlib.Path({str(cache)!r})\n"
        'if sys.argv[2] == "install":\n p.mkdir(parents=True,exist_ok=True)\n (p/"plugin.json").write_text("{}")\n'
    )
    git.chmod(0o755)
    cli.chmod(0o755)
    monkeypatch.chdir(project)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("PATH", str(bin_dir) + os.pathsep + os.environ["PATH"])
    assert ensure_plugins.main() == 0
    log = home / ".local/state/livespec-dev-tooling/plugin-commands.jsonl"
    assert (cache / "plugin.json").is_file()
    assert (len(log.read_text().splitlines()) if log.exists() else 0) == (6 if broken else 0)
