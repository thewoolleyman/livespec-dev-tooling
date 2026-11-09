"""Hermetic tests for fleet-wide Claude plugin adoption."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from returns.io import IOSuccess

from livespec_dev_tooling.fleet._local_context import CommandOutcome, CommandResult
from livespec_dev_tooling.fleet._manifest_git import GitReadRefused
from livespec_dev_tooling.fleet._plugin_build_currency_core import (
    BuildIdentifier,
    resolved_build,
    unresolved_build,
)
from livespec_dev_tooling.fleet.adopt_orchestrator_build import AdoptionOutcome

if TYPE_CHECKING:
    from livespec_dev_tooling.fleet.ensure_plugins_fleet import AdoptStep, RecipeRunner

__all__: list[str] = []


_PLUGIN = "orchestrator@livespec"
_ORCH = "livespec-orchestrator-beads-fabro@livespec-orchestrator-beads-fabro"
_BEFORE = "a" * 40
_AFTER = "b" * 40


def _tip(*, sha: str) -> BuildIdentifier:
    """The commit the marketplace clone names, as the adopt step reads it."""
    return resolved_build(sha=sha)


def _settings(*, plugin: str = _PLUGIN) -> str:
    """A member settings file enabling one fixture plugin."""
    return json.dumps({"enabledPlugins": {plugin: True}})


def _write_member(*, clones_root: Path, name: str, plugin: str = _PLUGIN) -> Path:
    """Create one minimal local member clone."""
    member = clones_root / name
    (member / ".claude").mkdir(parents=True)
    (member / ".claude" / "settings.json").write_text(_settings(plugin=plugin), encoding="utf-8")
    return member


def _write_registry(*, registry_path: Path, builds: dict[Path, str], plugin: str = _PLUGIN) -> None:
    """Write project-scoped install records for the fixture members."""
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(
        json.dumps(
            {
                "plugins": {
                    plugin: [
                        {"projectPath": str(member), "gitCommitSha": build}
                        for member, build in builds.items()
                    ]
                }
            }
        ),
        encoding="utf-8",
    )


def _recording_step(*, adopted: list[Path]) -> AdoptStep:
    """An adopt step that records the clones it was taken for and succeeds."""

    def step(*, clone: Path, build: str) -> AdoptionOutcome:
        del build
        adopted.append(clone)
        return AdoptionOutcome(lines=(), failure="")

    return step


def _recording_run(*, calls: list[Path | None]) -> RecipeRunner:
    """A member recipe runner that records the working directories it ran in and succeeds."""

    def run(*, args: list[str], cwd: Path | None = None) -> CommandResult:
        del args
        calls.append(cwd)
        return CommandResult(returncode=0, stdout="", stderr="")

    return run


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
    manifest_source = json.dumps(
        {
            "owner": "acme",
            "fleet": [
                {"repo": "alpha", "class": "impl-plugin"},
                {"repo": "beta", "class": "impl-plugin"},
            ],
        }
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

    adopted: list[Path] = []
    report = adopt(
        manifest_source=manifest_source,
        clones_root=clones_root,
        registry_path=registry_path,
        run=run,
        build=_AFTER,
        tip=_tip(sha=_AFTER),
        adopt_step=_recording_step(adopted=adopted),
    )

    assert adopted == []
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
    manifest_source = json.dumps(
        {
            "owner": "acme",
            "fleet": [
                {"repo": "alpha", "class": "impl-plugin"},
                {"repo": "missing", "class": "impl-plugin"},
                {"repo": "beta", "class": "impl-plugin"},
            ],
        }
    )
    registry_path = tmp_path / "plugins" / "installed_plugins.json"
    _write_registry(registry_path=registry_path, builds={alpha: _BEFORE, beta: _BEFORE})
    calls: list[Path | None] = []

    def run(*, args: list[str], cwd: Path | None = None) -> CommandResult:
        assert args == ["just", "ensure-plugins"]
        calls.append(cwd)
        return CommandResult(returncode=7 if cwd == alpha else 0, stdout="", stderr="refused")

    adopted: list[Path] = []
    report = adopt(
        manifest_source=manifest_source,
        clones_root=clones_root,
        registry_path=registry_path,
        run=run,
        build=_AFTER,
        tip=_tip(sha=_AFTER),
        adopt_step=_recording_step(adopted=adopted),
    )

    assert adopted == []
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
    manifest_source = json.dumps(
        {
            "owner": "acme",
            "fleet": [
                {"repo": "alpha", "class": "impl-plugin"},
                {"repo": "beta", "class": "impl-plugin"},
            ],
        }
    )
    registry_path = tmp_path / "plugins" / "installed_plugins.json"
    _write_registry(registry_path=registry_path, builds={alpha: _BEFORE, beta: _BEFORE})

    def run(*, args: list[str], cwd: Path | None = None) -> CommandResult:
        assert args == ["just", "ensure-plugins"]
        assert cwd is not None
        _write_registry(registry_path=registry_path, builds={alpha: _AFTER, beta: _BEFORE})
        return CommandResult(returncode=0, stdout="", stderr="")

    adopted: list[Path] = []
    report = adopt(
        manifest_source=manifest_source,
        clones_root=clones_root,
        registry_path=registry_path,
        run=run,
        build=_AFTER,
        tip=_tip(sha=_AFTER),
        adopt_step=_recording_step(adopted=adopted),
    )

    assert adopted == []
    assert report.exit_code == 1
    assert (
        report.lines[-1]
        == f"{_PLUGIN} has split installed builds: {_AFTER}: alpha; {_BEFORE}: beta"
    )


def test_membership_is_read_from_livespec_master_over_git_not_a_local_clone() -> None:
    """The manifest comes from livespec master at run time, as Sibling discovery reads it."""
    from livespec_dev_tooling.fleet.ensure_plugins_fleet import fetch_master_manifest

    seen: list[list[str]] = []

    def read_git(*, args: list[str], cwd: Path | None = None) -> CommandOutcome:
        assert cwd is None
        seen.append(args)
        stdout = "MANIFEST-BYTES" if "show" in args else ""
        return IOSuccess(CommandResult(returncode=0, stdout=stdout, stderr=""))

    fetched = fetch_master_manifest(owner="acme", read_git=read_git)

    assert fetched == "MANIFEST-BYTES"
    assert any(arg == "https://github.com/acme/livespec.git" for arg in seen[0])
    assert seen[1][-2:] == ["show", "HEAD:.livespec-fleet-manifest.jsonc"]


def test_unreadable_master_manifest_is_a_refusal_not_an_empty_member_set() -> None:
    """A manifest that cannot be fetched yields the refusal, never a silent empty fleet."""
    from livespec_dev_tooling.fleet.ensure_plugins_fleet import fetch_master_manifest

    def read_git(*, args: list[str], cwd: Path | None = None) -> CommandOutcome:
        assert args[0] == "git"
        assert cwd is None
        return IOSuccess(CommandResult(returncode=128, stdout="", stderr="no access"))

    fetched = fetch_master_manifest(owner="acme", read_git=read_git)

    assert isinstance(fetched, GitReadRefused)
    assert fetched.returncode == 128
    assert fetched.detail == "no access"
    assert not isinstance(fetched, str)


def _orch_fleet(*, tmp_path: Path) -> tuple[Path, Path, Path, Path, str]:
    """Two orchestrator-enabling members, a registry and a manifest naming an adopter."""
    clones_root = tmp_path / "projects"
    alpha = _write_member(clones_root=clones_root, name="alpha", plugin=_ORCH)
    beta = _write_member(clones_root=clones_root, name="beta", plugin=_ORCH)
    registry_path = tmp_path / "plugins" / "installed_plugins.json"
    _write_registry(
        registry_path=registry_path, builds={alpha: _BEFORE, beta: _BEFORE}, plugin=_ORCH
    )
    manifest = json.dumps(
        {
            "owner": "acme",
            "fleet": [
                {"repo": "alpha", "class": "impl-plugin"},
                {"repo": "beta", "class": "impl-plugin"},
            ],
            "adopters": [{"repo": "side", "profile": ["baseline"], "posture": "pinned"}],
        }
    )
    return clones_root, alpha, beta, registry_path, manifest


def test_a_build_that_is_not_the_marketplace_tip_runs_no_member(*, tmp_path: Path) -> None:
    from livespec_dev_tooling.fleet.ensure_plugins_fleet import adopt

    clones_root, _alpha, _beta, registry_path, manifest = _orch_fleet(tmp_path=tmp_path)
    calls: list[Path | None] = []
    run = _recording_run(calls=calls)
    adopted: list[Path] = []
    report = adopt(
        manifest_source=manifest,
        clones_root=clones_root,
        registry_path=registry_path,
        run=run,
        build=_BEFORE,
        tip=_tip(sha=_AFTER),
        adopt_step=_recording_step(adopted=adopted),
    )

    assert adopted == []
    assert calls == []
    assert report.exit_code == 1
    assert _BEFORE in report.lines[0]
    assert _AFTER in report.lines[0]


def test_an_unreadable_marketplace_tip_runs_no_member(*, tmp_path: Path) -> None:
    from livespec_dev_tooling.fleet.ensure_plugins_fleet import adopt

    clones_root, _alpha, _beta, registry_path, manifest = _orch_fleet(tmp_path=tmp_path)

    calls: list[Path | None] = []
    run = _recording_run(calls=calls)

    adopted: list[Path] = []
    report = adopt(
        manifest_source=manifest,
        clones_root=clones_root,
        registry_path=registry_path,
        run=run,
        build=_AFTER,
        tip=unresolved_build(detail="marketplace is not registered"),
        adopt_step=_recording_step(adopted=adopted),
    )

    assert adopted == []
    assert report.exit_code == 1
    assert calls == []
    assert "marketplace is not registered" in report.lines[0]


def test_each_orchestrator_member_runs_its_recipe_then_takes_the_adopt_step(
    *, tmp_path: Path
) -> None:
    from livespec_dev_tooling.fleet.ensure_plugins_fleet import adopt

    clones_root, alpha, beta, registry_path, manifest = _orch_fleet(tmp_path=tmp_path)
    events: list[tuple[str, Path | None]] = []

    def run(*, args: list[str], cwd: Path | None = None) -> CommandResult:
        assert args == ["just", "ensure-plugins"]
        events.append(("recipe", cwd))
        return CommandResult(returncode=0, stdout="", stderr="")

    def step(*, clone: Path, build: str) -> AdoptionOutcome:
        assert build == _AFTER
        events.append(("adopt", clone))
        _write_registry(
            registry_path=registry_path,
            builds={alpha: _AFTER, beta: _AFTER if clone == beta else _BEFORE},
            plugin=_ORCH,
        )
        return AdoptionOutcome(lines=(), failure="")

    report = adopt(
        manifest_source=manifest,
        clones_root=clones_root,
        registry_path=registry_path,
        run=run,
        build=_AFTER,
        tip=_tip(sha=_AFTER),
        adopt_step=step,
    )

    assert events == [("recipe", alpha), ("adopt", alpha), ("recipe", beta), ("adopt", beta)]
    assert report.exit_code == 0
    assert report.lines[:2] == (
        f"alpha {_ORCH} before={_BEFORE} after={_AFTER}",
        f"beta {_ORCH} before={_BEFORE} after={_AFTER}",
    )


def test_a_failed_recipe_or_adopt_step_does_not_stop_the_remaining_members(
    *, tmp_path: Path
) -> None:
    from livespec_dev_tooling.fleet.ensure_plugins_fleet import adopt

    clones_root, alpha, beta, registry_path, manifest = _orch_fleet(tmp_path=tmp_path)
    adopted: list[Path] = []

    def run(*, args: list[str], cwd: Path | None = None) -> CommandResult:
        del args
        return CommandResult(returncode=7 if cwd == beta else 0, stdout="", stderr="refused")

    def step(*, clone: Path, build: str) -> AdoptionOutcome:
        del build
        adopted.append(clone)
        return AdoptionOutcome(lines=(), failure="update exited 5" if clone == alpha else "")

    report = adopt(
        manifest_source=manifest,
        clones_root=clones_root,
        registry_path=registry_path,
        run=run,
        build=_AFTER,
        tip=_tip(sha=_AFTER),
        adopt_step=step,
    )

    assert adopted == [alpha, beta]
    assert report.exit_code == 1
    assert "alpha failed: update exited 5" in report.lines
    assert "beta failed: ensure-plugins exited 7: refused" in report.lines


def test_an_orchestrator_left_at_different_builds_is_named_with_its_holders(
    *, tmp_path: Path
) -> None:
    from livespec_dev_tooling.fleet.ensure_plugins_fleet import adopt

    clones_root, alpha, beta, registry_path, manifest = _orch_fleet(tmp_path=tmp_path)

    def run(*, args: list[str], cwd: Path | None = None) -> CommandResult:
        del args, cwd
        return CommandResult(returncode=0, stdout="", stderr="")

    def step(*, clone: Path, build: str) -> AdoptionOutcome:
        del clone, build
        _write_registry(
            registry_path=registry_path, builds={alpha: _AFTER, beta: _BEFORE}, plugin=_ORCH
        )
        return AdoptionOutcome(lines=(), failure="")

    report = adopt(
        manifest_source=manifest,
        clones_root=clones_root,
        registry_path=registry_path,
        run=run,
        build=_AFTER,
        tip=_tip(sha=_AFTER),
        adopt_step=step,
    )

    assert report.exit_code == 1
    assert (
        report.lines[-1] == f"{_ORCH} has split installed builds: {_AFTER}: alpha; {_BEFORE}: beta"
    )


def test_an_adopter_is_reported_with_the_adopt_command_and_never_adopted(*, tmp_path: Path) -> None:
    from livespec_dev_tooling.fleet.ensure_plugins_fleet import adopt

    clones_root, alpha, beta, registry_path, manifest = _orch_fleet(tmp_path=tmp_path)
    side = _write_member(clones_root=clones_root, name="side", plugin=_ORCH)
    _write_registry(
        registry_path=registry_path,
        builds={alpha: _AFTER, beta: _AFTER, side: _BEFORE},
        plugin=_ORCH,
    )
    ran: list[Path | None] = []

    def run(*, args: list[str], cwd: Path | None = None) -> CommandResult:
        del args
        ran.append(cwd)
        return CommandResult(returncode=0, stdout="", stderr="")

    def step(*, clone: Path, build: str) -> AdoptionOutcome:
        del build
        assert clone != side
        return AdoptionOutcome(lines=(), failure="")

    report = adopt(
        manifest_source=manifest,
        clones_root=clones_root,
        registry_path=registry_path,
        run=run,
        build=_AFTER,
        tip=_tip(sha=_AFTER),
        adopt_step=step,
    )

    assert side not in ran
    assert report.exit_code == 0
    assert report.lines[-1] == (
        f"side {_ORCH} installed={_BEFORE}; adopt with: just adopt-orchestrator-build side <build>"
    )


def test_an_adopter_without_a_clone_or_the_orchestrator_prints_nothing(*, tmp_path: Path) -> None:
    from livespec_dev_tooling.fleet.ensure_plugins_fleet import adopt

    clones_root, alpha, beta, registry_path, manifest = _orch_fleet(tmp_path=tmp_path)
    _write_registry(registry_path=registry_path, builds={alpha: _AFTER, beta: _AFTER}, plugin=_ORCH)
    calls: list[Path | None] = []
    adopted: list[Path] = []

    def adopt_fleet() -> tuple[str, ...]:
        return adopt(
            manifest_source=manifest,
            clones_root=clones_root,
            registry_path=registry_path,
            run=_recording_run(calls=calls),
            build=_AFTER,
            tip=_tip(sha=_AFTER),
            adopt_step=_recording_step(adopted=adopted),
        ).lines

    assert not any(line.startswith("side ") for line in adopt_fleet())
    _ = _write_member(clones_root=clones_root, name="side", plugin="other@other")
    assert not any(line.startswith("side ") for line in adopt_fleet())
    assert calls == [alpha, beta, alpha, beta]
    assert adopted == [alpha, beta, alpha, beta]


def test_the_justfile_fleet_recipe_takes_the_build() -> None:
    justfile = (Path(__file__).resolve().parents[3] / "justfile").read_text(encoding="utf-8")

    assert "\n[positional-arguments]\nensure-plugins-fleet build:\n" in justfile
    assert 'livespec_dev_tooling.fleet.ensure_plugins_fleet "$1"' in justfile
