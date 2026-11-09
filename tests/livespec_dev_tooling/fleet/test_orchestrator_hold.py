"""Tests for the orchestrator build hold in `ensure-plugins`.

The orchestrator plugin moves only through a named operator step. A session
reconcile that finds an install record for the working directory holds that
build, whichever build the marketplace offers.
"""

from __future__ import annotations

import json
from pathlib import Path

from returns.io import IOFailure, IOSuccess

from livespec_dev_tooling.fleet import ensure_plugins
from livespec_dev_tooling.fleet._ensure_plugin_artifacts import (
    ArtifactOutcome,
    ArtifactUnreadable,
    RemovalOutcome,
)
from livespec_dev_tooling.fleet._ensure_plugin_commands import (
    PluginCommandOutcome,
    PluginCommandResult,
)

__all__: list[str] = []

_ORCH = "livespec-orchestrator-beads-fabro@livespec-orchestrator-beads-fabro"
_OTHER = "livespec@livespec"
_ROOT = "/work/clone"
_HELD_SHA = "a" * 40
_NEW_SHA = "b" * 40
_LAST_UPDATED = "2026-11-09T09:22:35.000Z"
_ORCH_PATH = "/cache/orch-held"
_ORCH_NEW_PATH = "/cache/orch-new"
_OTHER_PATH = "/cache/livespec"
_OTHER_NEW_PATH = "/cache/livespec-new"


def _settings() -> str:
    return json.dumps(
        {
            "enabledPlugins": {_ORCH: True, _OTHER: True},
            "extraKnownMarketplaces": {
                "livespec-orchestrator-beads-fabro": {
                    "source": {
                        "source": "github",
                        "repo": "thewoolleyman/livespec-orchestrator-beads-fabro",
                        "ref": "release",
                    }
                },
                "livespec": {
                    "source": {
                        "source": "github",
                        "repo": "thewoolleyman/livespec",
                        "ref": "release",
                    }
                },
            },
        }
    )


class _Host:
    """A fake host: install records change only when a plugin command runs."""

    def __init__(
        self,
        *,
        orch: tuple[str, str] | None,
        broken: frozenset[str] = frozenset(),
        unanswered: frozenset[str] = frozenset(),
        marketplace_exit: int = 0,
    ) -> None:
        self.orch = orch
        self.broken = broken
        self.unanswered = unanswered
        self.marketplace_exit = marketplace_exit
        self.other_path = _OTHER_PATH
        self.calls: list[tuple[str, ...]] = []
        self.removed: list[str] = []

    def runner(self, *, args: tuple[str, ...]) -> PluginCommandOutcome:
        self.calls.append(args)
        if args[2] == "marketplace":
            return IOSuccess(PluginCommandResult(returncode=self.marketplace_exit))
        if args[3] == _ORCH:
            self.orch = (_NEW_SHA, _ORCH_NEW_PATH)
        elif _OTHER_PATH in self.removed:
            self.other_path = _OTHER_NEW_PATH
        return IOSuccess(PluginCommandResult(returncode=0))

    def registry(self) -> str:
        orch_records: list[dict[str, str]] = [
            {
                "scope": "project",
                "projectPath": "/work/primary",
                "installPath": "/cache/orch-primary",
                "gitCommitSha": "c" * 40,
            }
        ]
        if self.orch is not None:
            orch_records.append(
                {
                    "scope": "project",
                    "projectPath": _ROOT,
                    "installPath": self.orch[1],
                    "gitCommitSha": self.orch[0],
                    "lastUpdated": _LAST_UPDATED,
                }
            )
        other = {
            "scope": "project",
            "projectPath": _ROOT,
            "installPath": self.other_path,
            "gitCommitSha": "d" * 40,
            "lastUpdated": _LAST_UPDATED,
        }
        return json.dumps({"version": 2, "plugins": {_ORCH: orch_records, _OTHER: [other]}})

    def read_artifact(self, *, install_path: str) -> ArtifactOutcome:
        if install_path in self.unanswered:
            return IOFailure(
                ArtifactUnreadable(
                    install_path=install_path, reason="cache-manifest-unparseable", detail="x"
                )
            )
        if install_path in self.broken:
            return IOSuccess((f"installPath {install_path} has no readable plugin.json",))
        return IOSuccess(())

    def remove_cache_dir(self, *, install_path: str) -> RemovalOutcome:
        self.removed.append(install_path)
        return IOSuccess(install_path)

    def orchestrator_calls(self) -> list[tuple[str, ...]]:
        return [call for call in self.calls if _ORCH in call]


def _run(*, host: _Host) -> ensure_plugins.EnsureReport:
    assert hasattr(ensure_plugins, "ensure_report")
    return ensure_plugins.ensure_report(
        settings_text=_settings(),
        project_root=_ROOT,
        runner=host.runner,
        read_registry=host.registry,
        read_artifact=host.read_artifact,
        remove_cache_dir=host.remove_cache_dir,
    )


def test_held_orchestrator_is_neither_installed_nor_updated_and_one_line_names_the_hold() -> None:
    host = _Host(orch=(_HELD_SHA, _ORCH_PATH))
    before = host.registry()

    report = _run(host=host)

    assert host.orchestrator_calls() == []
    assert host.registry().count(_HELD_SHA) == before.count(_HELD_SHA) > 0
    assert report.findings == ()
    assert len(report.notices) == 1
    line = report.notices[0]
    for needle in (_ORCH, _HELD_SHA, _LAST_UPDATED, "just adopt-orchestrator-build"):
        assert needle in line


def test_held_orchestrator_leaves_the_install_record_byte_identical() -> None:
    host = _Host(orch=(_HELD_SHA, _ORCH_PATH))
    before = host.registry()

    _ = _run(host=host)

    assert host.registry() == before


def test_every_other_enabled_plugin_is_still_installed_and_updated() -> None:
    host = _Host(orch=(_HELD_SHA, _ORCH_PATH))

    _ = _run(host=host)

    assert ("claude", "plugin", "install", _OTHER, "-s", "project") in host.calls
    assert ("claude", "plugin", "update", _OTHER, "-s", "project") in host.calls


def test_absent_install_in_a_linked_worktree_installs_the_offered_build() -> None:
    host = _Host(orch=None)

    report = _run(host=host)

    assert ("claude", "plugin", "install", _ORCH, "-s", "project") in host.calls
    assert report.findings == ()
    assert host.orch == (_NEW_SHA, _ORCH_NEW_PATH)


def test_absent_install_is_still_attempted_after_the_marketplace_fetch_failed() -> None:
    host = _Host(orch=None, marketplace_exit=1)

    report = _run(host=host)

    assert ("claude", "plugin", "install", _ORCH, "-s", "project") in host.calls
    assert report.findings != ()


def test_broken_installed_build_is_repaired_and_the_build_before_and_after_is_printed() -> None:
    host = _Host(orch=(_HELD_SHA, _ORCH_PATH), broken=frozenset({_ORCH_PATH}))

    report = _run(host=host)

    assert ("claude", "plugin", "install", _ORCH, "-s", "project") in host.calls
    assert report.findings == ()
    (line,) = report.notices
    for needle in (_ORCH, _HELD_SHA, _NEW_SHA):
        assert needle in line


def test_unanswered_probe_is_a_finding_and_runs_no_command_for_the_orchestrator() -> None:
    host = _Host(orch=(_HELD_SHA, _ORCH_PATH), unanswered=frozenset({_ORCH_PATH}))
    before = host.registry()

    report = _run(host=host)

    assert host.orchestrator_calls() == []
    assert host.registry() == before
    assert host.removed == []
    assert any("could not be inspected" in finding for finding in report.findings)


def test_another_plugin_failing_verification_never_moves_the_held_orchestrator() -> None:
    host = _Host(orch=(_HELD_SHA, _ORCH_PATH), broken=frozenset({_OTHER_PATH}))
    before = host.registry()

    report = _run(host=host)

    assert host.orchestrator_calls() == []
    assert host.removed == [_OTHER_PATH]
    assert report.findings == ()
    assert _HELD_SHA in host.registry()
    assert before.count(_HELD_SHA) == host.registry().count(_HELD_SHA)


def test_every_session_start_source_runs_the_ensure_plugins_recipe() -> None:
    settings_path = Path(__file__).resolve().parents[3] / ".claude" / "settings.json"
    settings = json.loads(settings_path.read_text(encoding="utf-8"))

    (group,) = settings["hooks"]["SessionStart"]

    assert group["matcher"] == ""
    assert [hook["command"] for hook in group["hooks"]] == ["mise exec -- just ensure-plugins"]
