"""Integration-shaped tests for fleet-wide Claude plugin adoption."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import pytest

from livespec_dev_tooling.fleet._local_context import CommandResult

__all__: list[str] = []

pytestmark = pytest.mark.integration

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


def _write_split_registry(*, registry_path: Path, alpha: Path, beta: Path) -> None:
    """Write distinct project-scoped builds for the two fixture members."""
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(
        json.dumps(
            {
                "plugins": {
                    _PLUGIN: [
                        {"projectPath": str(alpha), "gitCommitSha": _AFTER},
                        {"projectPath": str(beta), "gitCommitSha": _BEFORE},
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


def test_adoption_continues_after_missing_clone_and_failed_member_recipe(*, tmp_path: Path) -> None:
    """Each member is attempted even when another member cannot be adopted."""
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
                    {"repo": "missing", "class": "impl-plugin"},
                    {"repo": "beta", "class": "impl-plugin"},
                ],
            }
        ),
        encoding="utf-8",
    )
    registry_path = tmp_path / "home" / ".claude" / "plugins" / "installed_plugins.json"
    _write_registry(registry_path=registry_path, members=(alpha, beta), build=_BEFORE)
    calls: list[Path | None] = []

    def run(*, args: list[str], cwd: Path | None = None) -> CommandResult:
        assert args == ["just", "ensure-plugins"]
        calls.append(cwd)
        return CommandResult(
            returncode=7 if cwd == alpha else 0,
            stdout="",
            stderr="alpha refusal" if cwd == alpha else "",
        )

    report = module.adopt(
        manifest_path=manifest_path,
        clones_root=clones_root,
        registry_path=registry_path,
        run=run,
    )

    assert calls == [alpha, beta]
    assert report.exit_code == 1
    assert f"missing failed: local clone missing at {clones_root / 'missing'}" in report.lines
    assert "alpha failed: ensure-plugins exited 7: alpha refusal" in report.lines


def test_adoption_refuses_a_split_enabled_plugin_build(*, tmp_path: Path) -> None:
    """A successful fleet adoption still refuses a per-project build split."""
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

    def run(*, args: list[str], cwd: Path | None = None) -> CommandResult:
        assert args == ["just", "ensure-plugins"]
        assert cwd is not None
        _write_split_registry(registry_path=registry_path, alpha=alpha, beta=beta)
        return CommandResult(returncode=0, stdout="", stderr="")

    report = module.adopt(
        manifest_path=manifest_path,
        clones_root=clones_root,
        registry_path=registry_path,
        run=run,
    )

    assert report.exit_code == 1
    assert (
        report.lines[-1]
        == f"{_PLUGIN} has split installed builds: {_BEFORE}: beta; {_AFTER}: alpha"
    )


def test_fleet_adoption_entrypoint_carries_its_own_vendor_import_path() -> None:
    """The operator command must run as a module without ambient imports."""
    source = (
        Path(__file__).resolve().parents[3]
        / "livespec_dev_tooling"
        / "fleet"
        / "ensure_plugins_fleet.py"
    ).read_text(encoding="utf-8")

    assert "_VENDOR_DIR" in source
