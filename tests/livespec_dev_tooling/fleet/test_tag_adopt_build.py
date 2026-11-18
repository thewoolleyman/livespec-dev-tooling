"""Tests for building an orchestrator tag in the throwaway builder home."""

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


def test_build_plugin_accepts_the_tag_commit_when_the_builder_project_path_is_realpath(
    *, tmp_path: Path
) -> None:
    """The builder registry is scoped to its throwaway home, not its lexical path."""
    home = tmp_path / "builder"
    install_path = Path("/private/var/tmp/builder/.claude/plugins/cache/orchestrator")

    def run(*, args: list[str], cwd: Path, env: Mapping[str, str]) -> CommandOutcome:
        _ = (cwd, env)
        if args[:3] == ["claude", "plugin", "install"]:
            registry = home / ".claude" / "plugins" / "installed_plugins.json"
            registry.parent.mkdir(parents=True)
            _ = registry.write_text(
                json.dumps(
                    {
                        "version": 2,
                        "plugins": {
                            ORCHESTRATOR_PLUGIN: [
                                {
                                    "scope": "project",
                                    "projectPath": "/private/var/tmp/builder/project",
                                    "installPath": str(install_path),
                                    "gitCommitSha": _COMMIT,
                                }
                            ]
                        },
                    }
                ),
                encoding="utf-8",
            )
        return IOSuccess(CommandResult(returncode=0, stdout="", stderr=""))

    built = build_plugin(home=home, tag=_TAG, tag_commit=_COMMIT, base_env={}, run=run)

    assert built == BuiltPlugin(install_path=install_path, failure="")
