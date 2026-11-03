"""Hermetic tests for fleet-wide Claude plugin adoption."""

from __future__ import annotations

import json
from pathlib import Path

from livespec_dev_tooling.fleet._local_context import CommandResult

__all__: list[str] = []


_PLUGIN = "orchestrator@livespec"
_BEFORE = "a" * 40
_AFTER = "b" * 40


def _settings() -> str:
    """A member settings file enabling the fixture plugin."""
    return json.dumps({"enabledPlugins": {_PLUGIN: True}})


def _write_member(*, clones_root: Path, name: str) -> Path:
    """Create one minimal local member clone."""
    member = clones_root / name
    (member / ".claude").mkdir(parents=True)
    (member / ".claude" / "settings.json").write_text(_settings(), encoding="utf-8")
    return member


def _write_registry(*, registry_path: Path, builds: dict[Path, str]) -> None:
    """Write project-scoped install records for the fixture members."""
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(
        json.dumps(
            {
                "plugins": {
                    _PLUGIN: [
                        {"projectPath": str(member), "gitCommitSha": build}
                        for member, build in builds.items()
                    ]
                }
            }
        ),
        encoding="utf-8",
    )


def test_adoption_runs_each_members_recipe_and_reports_project_scoped_build_pairs(
    *, tmp_path: Path
) -> None:
    """Each member owns its recipe while its registry records supply the report."""
    module_path = (
        Path(__file__).resolve().parents[3]
        / "livespec_dev_tooling"
        / "fleet"
        / "ensure_plugins_fleet.py"
    )
    assert module_path.is_file()
    from livespec_dev_tooling.fleet.ensure_plugins_fleet import adopt

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
    registry_path = tmp_path / "plugins" / "installed_plugins.json"
    _write_registry(registry_path=registry_path, builds={alpha: _BEFORE, beta: _BEFORE})
    calls: list[Path | None] = []

    def run(*, args: list[str], cwd: Path | None = None) -> CommandResult:
        assert args == ["just", "ensure-plugins"]
        assert cwd is not None
        calls.append(cwd)
        _write_registry(
            registry_path=registry_path,
            builds={
                alpha: _AFTER if cwd == alpha else _BEFORE,
                beta: _AFTER if cwd == beta else _BEFORE,
            },
        )
        return CommandResult(returncode=0, stdout="", stderr="")

    report = adopt(
        manifest_path=manifest_path,
        clones_root=clones_root,
        registry_path=registry_path,
        run=run,
    )

    assert calls == [alpha, beta]
    assert report.exit_code == 0
    assert report.lines == (
        f"alpha {_PLUGIN} before={_BEFORE} after={_AFTER}",
        f"beta {_PLUGIN} before={_BEFORE} after={_AFTER}",
    )


def test_adoption_continues_after_missing_clone_and_failed_recipe(*, tmp_path: Path) -> None:
    """A member failure is reported without suppressing a later member."""
    from livespec_dev_tooling.fleet.ensure_plugins_fleet import adopt

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
    registry_path = tmp_path / "plugins" / "installed_plugins.json"
    _write_registry(registry_path=registry_path, builds={alpha: _BEFORE, beta: _BEFORE})
    calls: list[Path | None] = []

    def run(*, args: list[str], cwd: Path | None = None) -> CommandResult:
        assert args == ["just", "ensure-plugins"]
        calls.append(cwd)
        return CommandResult(returncode=7 if cwd == alpha else 0, stdout="", stderr="refused")

    report = adopt(
        manifest_path=manifest_path, clones_root=clones_root, registry_path=registry_path, run=run
    )

    assert calls == [alpha, beta]
    assert report.exit_code == 1
    assert f"missing failed: local clone missing at {clones_root / 'missing'}" in report.lines
    assert "alpha failed: ensure-plugins exited 7: refused" in report.lines


def test_adoption_refuses_split_builds_after_successful_recipes(*, tmp_path: Path) -> None:
    """Successful recipes do not hide a remaining project-scoped build split."""
    from livespec_dev_tooling.fleet.ensure_plugins_fleet import adopt

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
    registry_path = tmp_path / "plugins" / "installed_plugins.json"
    _write_registry(registry_path=registry_path, builds={alpha: _BEFORE, beta: _BEFORE})

    def run(*, args: list[str], cwd: Path | None = None) -> CommandResult:
        assert args == ["just", "ensure-plugins"]
        assert cwd is not None
        _write_registry(registry_path=registry_path, builds={alpha: _AFTER, beta: _BEFORE})
        return CommandResult(returncode=0, stdout="", stderr="")

    report = adopt(
        manifest_path=manifest_path, clones_root=clones_root, registry_path=registry_path, run=run
    )

    assert report.exit_code == 1
    assert (
        report.lines[-1]
        == f"{_PLUGIN} has split installed builds: {_AFTER}: alpha; {_BEFORE}: beta"
    )
