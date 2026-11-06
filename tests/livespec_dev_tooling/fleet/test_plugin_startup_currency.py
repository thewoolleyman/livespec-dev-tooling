"""Startup skips proven-current commands without weakening verification or repair."""

from __future__ import annotations

import inspect
import json
from pathlib import Path

from returns.io import IOSuccess

from livespec_dev_tooling.fleet.ensure_plugins import (
    PluginCommandOutcome,
    PluginCommandResult,
    ensure,
)


def test_current_plugins_skip_commands_but_still_verify_and_repair(tmp_path: Path) -> None:
    settings = json.dumps(
        {
            "enabledPlugins": {"one@alpha": True},
            "extraKnownMarketplaces": {
                "alpha": {"source": {"source": "github", "repo": "acme/alpha", "ref": "release"}}
            },
        }
    )
    artifact = tmp_path / "one"
    artifact.mkdir()
    (artifact / "plugin.json").write_text("{}")
    registry = json.dumps(
        {"plugins": {"one@alpha": [{"projectPath": "/repo", "installPath": str(artifact)}]}}
    )
    seen: list[tuple[str, ...]] = []

    def runner(*, args: tuple[str, ...]) -> PluginCommandOutcome:
        seen.append(args)
        return IOSuccess(PluginCommandResult(returncode=0))

    currency = (
        {
            "current_plugins": frozenset({"one@alpha"}),
            "registered_marketplaces": frozenset({"acme/alpha@release"}),
        }
        if "current_plugins" in inspect.signature(ensure).parameters
        else {}
    )
    assert (
        ensure(
            settings_text=settings,
            project_root="/repo",
            runner=runner,
            read_registry=lambda: registry,
            **currency,
        )
        == ()
    )
    assert seen == []
    (artifact / "plugin.json").unlink()
    removed: list[str] = []

    def remove(*, install_path: str) -> IOSuccess[str]:
        removed.append(install_path)
        (artifact / "plugin.json").write_text("{}")
        return IOSuccess(install_path)

    assert (
        ensure(
            settings_text=settings,
            project_root="/repo",
            runner=runner,
            read_registry=lambda: registry,
            **currency,
            remove_cache_dir=remove,
        )
        == ()
    )
    assert removed == [str(artifact)]
    assert len(seen) == 3
