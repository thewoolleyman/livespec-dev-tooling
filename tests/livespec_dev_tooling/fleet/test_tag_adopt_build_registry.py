"""Registry read-back cases for the throwaway tag-adopt builder."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from returns.io import IOSuccess

from livespec_dev_tooling.fleet._local_context import CommandOutcome, CommandResult
from livespec_dev_tooling.fleet._orchestrator_hold import ORCHESTRATOR_PLUGIN
from livespec_dev_tooling.fleet._tag_adopt_build import BuiltPlugin, build_plugin

_TAG = "v0.311.0"
_COMMIT = "e" * 40


def _build_with_record(*, tmp_path: Path, record: dict[str, object]) -> BuiltPlugin:
    """Run the builder with its private registry populated at install time."""
    home = tmp_path / "builder"

    def run(*, args: list[str], cwd: Path, env: Mapping[str, str]) -> CommandOutcome:
        _ = (cwd, env)
        if args[:3] == ["claude", "plugin", "install"]:
            registry = home / ".claude" / "plugins" / "installed_plugins.json"
            registry.parent.mkdir(parents=True)
            _ = registry.write_text(
                json.dumps({"version": 2, "plugins": {ORCHESTRATOR_PLUGIN: [record]}}),
                encoding="utf-8",
            )
        return IOSuccess(CommandResult(returncode=0, stdout="", stderr=""))

    return build_plugin(home=home, tag=_TAG, tag_commit=_COMMIT, base_env={}, run=run)


def test_build_plugin_accepts_commit_named_path_without_git_commit_sha(*, tmp_path: Path) -> None:
    """A legacy registry record falls back to the tag-named install directory."""
    install_path = (
        Path("/private/var/tmp/builder/.claude/plugins/cache/orchestrator") / _COMMIT[:12]
    )

    built = _build_with_record(
        tmp_path=tmp_path,
        record={
            "scope": "project",
            "projectPath": "/private/var/tmp/builder/project",
            "installPath": str(install_path),
        },
    )

    assert built == BuiltPlugin(install_path=install_path, failure="")


def test_build_plugin_refuses_a_builder_record_at_another_commit(*, tmp_path: Path) -> None:
    """A successful builder command cannot move a record for the wrong release."""
    installed_commit = "d" * 40

    built = _build_with_record(
        tmp_path=tmp_path,
        record={
            "scope": "project",
            "projectPath": "/private/var/tmp/builder/project",
            "installPath": f"/private/var/tmp/builder/.claude/plugins/cache/orchestrator/{installed_commit[:12]}",
            "gitCommitSha": installed_commit,
        },
    )

    assert built.install_path == tmp_path / "builder"
    assert installed_commit in built.failure
    assert _COMMIT in built.failure
    assert "nothing was moved" in built.failure


def test_build_plugin_refuses_a_legacy_record_without_a_string_install_path(
    *, tmp_path: Path
) -> None:
    """A malformed legacy registry record cannot stand in for the tagged build."""
    built = _build_with_record(
        tmp_path=tmp_path,
        record={
            "scope": "project",
            "projectPath": "/private/var/tmp/builder/project",
            "installPath": 42,
        },
    )

    assert built.install_path == tmp_path / "builder"
    assert "no install record names the tag's commit" in built.failure
    assert _COMMIT in built.failure
    assert "nothing was moved" in built.failure
