"""Integration-shaped tests for fleet-wide Claude plugin adoption."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

from livespec_dev_tooling.fleet._local_context import CommandResult

__all__: list[str] = []

_PLUGIN = "orchestrator@livespec"
_BEFORE = "a" * 40
_AFTER = "b" * 40


def _settings() -> str:
    return json.dumps({"enabledPlugins": {_PLUGIN: True}})


def _write_member(*, clones_root: Path, name: str) -> Path:
    member = clones_root / name
    (member / ".claude").mkdir(parents=True)
    (member / ".claude" / "settings.json").write_text(_settings(), encoding="utf-8")
    return member


def _write_registry(*, registry_path: Path, members: tuple[Path, ...], build: str) -> None:
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(
        json.dumps(
            {
                "plugins": {
                    _PLUGIN: [
                        {"projectPath": str(member), "gitCommitSha": build} for member in members
                    ]
                }
            }
        ),
        encoding="utf-8",
    )


def test_adoption_runs_each_members_own_recipe_and_reports_each_before_and_after_build(
    *, tmp_path: Path
) -> None:
    """Every manifest member is reconciled in its clone and read back by project path."""
    module = importlib.import_module("livespec_dev_tooling.fleet.ensure_plugins_fleet")
    clones_root = tmp_path / "projects"
    alpha = _write_member(clones_root=clones_root, name="alpha")
    beta = _write_member(clones_root=clones_root, name="beta")
    manifest_path = clones_root / "livespec" / ".livespec-fleet-manifest.jsonc"
    manifest_path.parent.mkdir()
    manifest_path.write_text(
        json.dumps(
            {
                "owner": "acme",
                "fleet": [
                    {"repo": "alpha", "class": "impl-plugin"},
                    {"repo": "beta", "class": "impl-plugin"},
                ],
            }
        ),
        encoding="utf-8",
    )
    registry_path = tmp_path / "home" / ".claude" / "plugins" / "installed_plugins.json"
    _write_registry(registry_path=registry_path, members=(alpha, beta), build=_BEFORE)
    calls: list[tuple[tuple[str, ...], Path | None]] = []

    def run(*, args: list[str], cwd: Path | None = None) -> Any:
        calls.append((tuple(args), cwd))
        _write_registry(registry_path=registry_path, members=(alpha, beta), build=_AFTER)
        return CommandResult(returncode=0, stdout="", stderr="")

    report = module.adopt(
        manifest_path=manifest_path,
        clones_root=clones_root,
        registry_path=registry_path,
        run=run,
    )

    assert calls == [
        (("just", "ensure-plugins"), alpha),
        (("just", "ensure-plugins"), beta),
    ]
    assert report.exit_code == 0
    assert report.lines == (
        f"alpha {_PLUGIN} before={_BEFORE} after={_AFTER}",
        f"beta {_PLUGIN} before={_BEFORE} after={_AFTER}",
    )
