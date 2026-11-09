"""Tests for the operator-invoked orchestrator adopt step."""

from __future__ import annotations

import json
from pathlib import Path

from returns.io import IOFailure, IOSuccess

from livespec_dev_tooling.fleet._fleet_manifest_read import manifest_names
from livespec_dev_tooling.fleet._invocation_failure import BINARY_ABSENT, InvocationNotPerformed
from livespec_dev_tooling.fleet._local_context import CommandOutcome, CommandResult
from livespec_dev_tooling.fleet.adopt_orchestrator_build import (
    AdoptionOutcome,
    CloneUnresolved,
    adopt_build,
    clones_root,
    marketplace_tip,
    resolve_clone,
)

__all__: list[str] = []

_ORCH = "livespec-orchestrator-beads-fabro@livespec-orchestrator-beads-fabro"
_MARKET = "livespec-orchestrator-beads-fabro"
_LOCATION = "/host/marketplaces/livespec-orchestrator-beads-fabro"
_OLD = "a" * 40
_NEW = "b" * 40
_NEWER = "c" * 40


class _Host:
    """A fake host: a marketplace clone tip, an install record and a command log."""

    def __init__(
        self,
        *,
        tmp_path: Path,
        enabled: bool = True,
        tip: str = _NEW,
        refresh_exit: int = 0,
        update_exit: int = 0,
        update_lands: str = _NEW,
        update_unperformed: bool = False,
        marketplaces: bool = True,
    ) -> None:
        self.clone = tmp_path / "clone"
        (self.clone / ".claude").mkdir(parents=True)
        plugins = {_ORCH: True} if enabled else {"other@other": True}
        _ = (self.clone / ".claude" / "settings.json").write_text(
            json.dumps({"enabledPlugins": plugins}), encoding="utf-8"
        )
        self.tip = tip
        self.refresh_exit = refresh_exit
        self.update_exit = update_exit
        self.update_lands = update_lands
        self.update_unperformed = update_unperformed
        self.marketplaces = marketplaces
        self.installed = _OLD
        self.calls: list[tuple[list[str], Path | None]] = []

    def run(self, *, args: list[str], cwd: Path | None = None) -> CommandOutcome:
        self.calls.append((args, cwd))
        if args[:4] == ["claude", "plugin", "marketplace", "update"]:
            return IOSuccess(CommandResult(returncode=self.refresh_exit, stdout="", stderr="no"))
        if args[0] == "git":
            return IOSuccess(CommandResult(returncode=0, stdout=f"{self.tip}\n", stderr=""))
        if self.update_unperformed:
            return IOFailure(
                InvocationNotPerformed(argv=tuple(args), kind=BINARY_ABSENT, detail="no claude")
            )
        if self.update_exit == 0:
            self.installed = self.update_lands
        return IOSuccess(CommandResult(returncode=self.update_exit, stdout="", stderr="boom"))

    def read_registry(self) -> str | None:
        record = {"projectPath": str(self.clone), "gitCommitSha": self.installed}
        return json.dumps({"plugins": {_ORCH: [record]}})

    def read_known_marketplaces(self) -> str | None:
        if not self.marketplaces:
            return None
        entry = {
            "source": {"source": "github", "repo": "o/r", "ref": "release"},
            "installLocation": _LOCATION,
        }
        return json.dumps({_MARKET: entry})

    def update_calls(self) -> list[tuple[list[str], Path | None]]:
        return [call for call in self.calls if call[0][:3] == ["claude", "plugin", "update"]]


def _adopt(*, host: _Host, build: str, clone: Path | None = None) -> AdoptionOutcome:
    return adopt_build(
        clone=host.clone if clone is None else clone,
        build=build,
        run=host.run,
        read_registry=host.read_registry,
        read_known_marketplaces=host.read_known_marketplaces,
    )


def test_adopting_the_marketplace_tip_updates_at_project_scope_in_the_clone(
    *, tmp_path: Path
) -> None:
    host = _Host(tmp_path=tmp_path)

    outcome = _adopt(host=host, build=_NEW)

    assert outcome.failure == ""
    assert host.update_calls() == [
        (["claude", "plugin", "update", _ORCH, "-s", "project"], host.clone)
    ]
    assert outcome.lines == (f"{host.clone} {_ORCH} before={_OLD} after={_NEW}",)


def test_the_marketplace_is_refreshed_and_the_tip_read_at_the_recorded_ref() -> None:
    seen: list[list[str]] = []

    def run(*, args: list[str], cwd: Path | None = None) -> CommandOutcome:
        assert cwd is None
        seen.append(args)
        return IOSuccess(CommandResult(returncode=0, stdout=f"{_NEW}\n", stderr=""))

    entry = {"source": {"ref": "v9"}, "installLocation": _LOCATION}
    tip = marketplace_tip(run=run, read_known_marketplaces=lambda: json.dumps({_MARKET: entry}))

    assert tip.sha == _NEW
    assert seen[0] == ["claude", "plugin", "marketplace", "update", _MARKET]
    assert seen[1] == ["git", "-C", _LOCATION, "rev-parse", "--verify", "origin/v9"]


def test_naming_any_other_commit_moves_nothing_and_names_both_commits(*, tmp_path: Path) -> None:
    host = _Host(tmp_path=tmp_path, tip=_NEWER)

    outcome = _adopt(host=host, build=_NEW)

    assert host.update_calls() == []
    assert _NEW in outcome.failure
    assert _NEWER in outcome.failure
    assert host.installed == _OLD


def test_a_missing_clone_is_named(*, tmp_path: Path) -> None:
    host = _Host(tmp_path=tmp_path)

    outcome = _adopt(host=host, build=_NEW, clone=tmp_path / "absent")

    assert "missing" in outcome.failure
    assert str(tmp_path / "absent") in outcome.failure
    assert host.calls == []


def test_a_clone_whose_settings_do_not_enable_the_plugin_is_refused(*, tmp_path: Path) -> None:
    host = _Host(tmp_path=tmp_path, enabled=False)

    outcome = _adopt(host=host, build=_NEW)

    assert _ORCH in outcome.failure
    assert "enable" in outcome.failure
    assert host.update_calls() == []


def test_a_clone_without_committed_settings_is_refused(*, tmp_path: Path) -> None:
    host = _Host(tmp_path=tmp_path)
    (host.clone / ".claude" / "settings.json").unlink()

    outcome = _adopt(host=host, build=_NEW)

    assert "settings" in outcome.failure
    assert host.update_calls() == []


def test_a_failed_marketplace_refresh_stops_before_any_update(*, tmp_path: Path) -> None:
    host = _Host(tmp_path=tmp_path, refresh_exit=3)

    outcome = _adopt(host=host, build=_NEW)

    assert "exited 3" in outcome.failure
    assert host.update_calls() == []


def test_an_unknown_marketplace_is_a_failure_not_a_match(*, tmp_path: Path) -> None:
    host = _Host(tmp_path=tmp_path, marketplaces=False)

    outcome = _adopt(host=host, build=_NEW)

    assert _MARKET in outcome.failure
    assert host.update_calls() == []


def test_a_failing_update_command_is_named_with_its_exit(*, tmp_path: Path) -> None:
    host = _Host(tmp_path=tmp_path, update_exit=5)

    outcome = _adopt(host=host, build=_NEW)

    assert "exited 5" in outcome.failure
    assert host.installed == _OLD


def test_an_update_that_never_ran_is_named(*, tmp_path: Path) -> None:
    host = _Host(tmp_path=tmp_path, update_unperformed=True)

    outcome = _adopt(host=host, build=_NEW)

    assert "did not run" in outcome.failure


def test_an_update_that_lands_another_build_is_a_failure_naming_both(*, tmp_path: Path) -> None:
    host = _Host(tmp_path=tmp_path, update_lands=_NEWER)

    outcome = _adopt(host=host, build=_NEW)

    assert _NEW in outcome.failure
    assert _NEWER in outcome.failure


def test_a_name_resolves_to_the_clones_root_and_an_absolute_path_is_taken_as_given() -> None:
    root = Path("/data/projects")
    names = frozenset({"livespec", "sidecar"})

    assert resolve_clone(clone="livespec", clones_root=root, names=names) == root / "livespec"
    assert resolve_clone(clone="sidecar", clones_root=root, names=names) == root / "sidecar"
    worktree = "/home/u/.worktrees/livespec/branch"
    assert resolve_clone(clone=worktree, clones_root=root, names=names) == Path(worktree)


def test_a_name_outside_the_manifest_is_refused_naming_it() -> None:
    resolved = resolve_clone(clone="stranger", clones_root=Path("/r"), names=frozenset({"a"}))

    assert isinstance(resolved, CloneUnresolved)
    assert "stranger" in resolved.cause


def test_the_clones_root_is_the_env_value_else_the_parent_of_the_primary_checkout() -> None:
    def run(*, args: list[str], cwd: Path | None = None) -> CommandOutcome:
        del cwd
        assert args[:2] == ["git", "rev-parse"]
        assert "--git-common-dir" in args
        return IOSuccess(
            CommandResult(
                returncode=0, stdout="/data/projects/livespec-dev-tooling/.git\n", stderr=""
            )
        )

    worktree = Path("/home/u/.worktrees/livespec-dev-tooling/branch")
    assert clones_root(env_root="/custom", cwd=worktree, run=run) == Path("/custom")
    assert clones_root(env_root=None, cwd=worktree, run=run) == Path("/data/projects")
    assert clones_root(env_root="", cwd=worktree, run=run) == Path("/data/projects")


def test_an_unanswered_git_probe_leaves_the_clones_root_unresolved() -> None:
    def failed(*, args: list[str], cwd: Path | None = None) -> CommandOutcome:
        del args, cwd
        return IOSuccess(CommandResult(returncode=128, stdout="", stderr="not a repo"))

    def unperformed(*, args: list[str], cwd: Path | None = None) -> CommandOutcome:
        del cwd
        return IOFailure(
            InvocationNotPerformed(argv=tuple(args), kind=BINARY_ABSENT, detail="no git")
        )

    for run in (failed, unperformed):
        resolved = clones_root(env_root=None, cwd=Path("/x"), run=run)
        assert isinstance(resolved, CloneUnresolved)
        assert "primary checkout" in resolved.cause


def test_manifest_names_are_the_fleet_members_and_the_adopters() -> None:
    manifest = json.dumps(
        {
            "owner": "acme",
            "fleet": [{"repo": "alpha", "class": "impl-plugin"}],
            "adopters": [{"repo": "side", "profile": ["baseline"], "posture": "pinned"}],
        }
    )

    assert manifest_names(manifest_source=manifest) == frozenset({"alpha", "side"})


def _tip_with(*, refresh: CommandOutcome, read: CommandOutcome, record: dict[str, object]) -> str:
    def run(*, args: list[str], cwd: Path | None = None) -> CommandOutcome:
        del cwd
        return refresh if args[0] == "claude" else read

    return marketplace_tip(
        run=run, read_known_marketplaces=lambda: json.dumps({_MARKET: record})
    ).unresolved


def _ok(*, stdout: str = "") -> CommandOutcome:
    return IOSuccess(CommandResult(returncode=0, stdout=stdout, stderr=""))


def _never_ran() -> CommandOutcome:
    return IOFailure(InvocationNotPerformed(argv=("x",), kind=BINARY_ABSENT, detail="absent"))


def test_every_way_the_marketplace_tip_goes_unread_is_named() -> None:
    good = {"source": {"ref": "release"}, "installLocation": _LOCATION}
    git_exit = IOSuccess(CommandResult(returncode=128, stdout="", stderr="bad ref"))

    assert "refresh did not run" in _tip_with(refresh=_never_ran(), read=_ok(), record=good)
    assert "rev-parse did not run" in _tip_with(refresh=_ok(), read=_never_ran(), record=good)
    assert "exited 128" in _tip_with(refresh=_ok(), read=git_exit, record=good)
    assert "records no source" in _tip_with(refresh=_ok(), read=_ok(), record={"source": {}})
    assert "records no source" in _tip_with(refresh=_ok(), read=_ok(), record={})


def test_a_clone_with_unparseable_settings_is_refused(*, tmp_path: Path) -> None:
    host = _Host(tmp_path=tmp_path)
    _ = (host.clone / ".claude" / "settings.json").write_text("{not json", encoding="utf-8")

    outcome = _adopt(host=host, build=_NEW)

    assert "unusable" in outcome.failure
    assert host.update_calls() == []


def test_the_justfile_ships_the_adopt_recipe_taking_a_clone_and_a_build() -> None:
    justfile = (Path(__file__).resolve().parents[3] / "justfile").read_text(encoding="utf-8")

    assert "\n[positional-arguments]\nadopt-orchestrator-build clone build:\n" in justfile
    assert 'livespec_dev_tooling.fleet.adopt_orchestrator_build "$1" "$2"' in justfile
