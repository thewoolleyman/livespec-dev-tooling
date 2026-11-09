"""Tests for the single-adoption-path guard over recipes, hooks, verbs, skills and settings."""

from __future__ import annotations

import json
from pathlib import Path

from livespec_dev_tooling.fleet.plugin_adoption_path import (
    scan_member_settings,
    scan_tree,
    settings_adoption_findings,
    source_adoption_findings,
)

__all__: list[str] = []

_RAW_RECIPE = "refresh:\n    claude plugin update livespec@livespec --scope project\n"
_RAW_ARGV = '    return ("claude", "plugin", "install", plugin, "-s", "project")\n'
_ALLOWED = "livespec_dev_tooling/fleet/_ensure_plugin_commands.py"
_REPO_ROOT = Path(__file__).resolve().parents[3]


def test_a_recipe_updating_a_plugin_at_project_scope_is_reported_with_its_path() -> None:
    findings = source_adoption_findings(path="justfile", text=_RAW_RECIPE)

    assert len(findings) == 1
    assert findings[0].startswith("justfile:")
    assert "adopt-orchestrator-build" in findings[0]


def test_an_argv_list_installing_at_project_scope_is_reported() -> None:
    findings = source_adoption_findings(path="livespec_dev_tooling/other.py", text=_RAW_ARGV)

    assert len(findings) == 1


def test_the_three_sanctioned_paths_are_not_reported() -> None:
    assert source_adoption_findings(path=_ALLOWED, text=_RAW_ARGV) == ()
    adopt = "livespec_dev_tooling/fleet/adopt_orchestrator_build.py"
    assert source_adoption_findings(path=adopt, text=_RAW_RECIPE) == ()


def test_user_scope_updates_and_marketplace_registration_are_not_project_scope_adoption() -> None:
    user_scope = "    claude plugin update livespec@livespec\n"
    registration = "    claude plugin marketplace add thewoolleyman/livespec@release\n"

    assert source_adoption_findings(path="justfile", text=user_scope) == ()
    assert source_adoption_findings(path="justfile", text=registration) == ()


def _settings(
    *, marketplace: dict[str, object] | None = None, env: dict[str, str] | None = None
) -> str:
    document: dict[str, object] = {
        "enabledPlugins": {"livespec@livespec": True},
        "extraKnownMarketplaces": {"livespec": marketplace or {"source": {"ref": "release"}}},
    }
    if env is not None:
        document["env"] = env
    return json.dumps(document)


def test_an_enabled_automatic_marketplace_update_is_reported() -> None:
    on = _settings(marketplace={"source": {"ref": "release"}, "autoUpdate": True})
    off = _settings(marketplace={"source": {"ref": "release"}, "autoUpdate": False})

    findings = settings_adoption_findings(path=".claude/settings.json", text=on)

    assert len(findings) == 1
    assert "autoUpdate" in findings[0]
    assert settings_adoption_findings(path=".claude/settings.json", text=off) == ()
    assert settings_adoption_findings(path=".claude/settings.json", text=_settings()) == ()


def test_a_forced_plugin_autoupdate_environment_is_reported() -> None:
    forced = _settings(env={"FORCE_AUTOUPDATE_PLUGINS": "1"})
    cleared = _settings(env={"FORCE_AUTOUPDATE_PLUGINS": "0"})

    assert len(settings_adoption_findings(path=".claude/settings.json", text=forced)) == 1
    assert settings_adoption_findings(path=".claude/settings.json", text=cleared) == ()


def test_a_settings_hook_running_a_raw_project_update_is_reported() -> None:
    hook = {
        "hooks": {"SessionStart": [{"hooks": [{"command": _RAW_RECIPE.strip().split("\n")[1]}]}]}
    }

    findings = settings_adoption_findings(path=".claude/settings.json", text=json.dumps(hook))

    assert len(findings) == 1


def test_settings_that_cannot_be_read_are_reported_not_passed() -> None:
    findings = settings_adoption_findings(path="alpha/.claude/settings.json", text="{not json")

    assert len(findings) == 1
    assert "alpha/.claude/settings.json" in findings[0]


def test_a_tree_scan_covers_recipes_hooks_verbs_and_skills_but_not_tests_or_docs(
    *, tmp_path: Path
) -> None:
    for relative in (
        "justfile",
        ".claude/hooks/refresh.sh",
        ".claude/skills/refresh/SKILL.md",
        "livespec_dev_tooling/verb.py",
        "tests/test_verb.py",
        "docs/runbook.md",
    ):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        _ = target.write_text(_RAW_RECIPE, encoding="utf-8")
    vendored = tmp_path / "livespec_dev_tooling" / "_vendor" / "dep.py"
    vendored.parent.mkdir(parents=True)
    _ = vendored.write_text(_RAW_RECIPE, encoding="utf-8")
    settings = tmp_path / ".claude" / "settings.json"
    _ = settings.write_text(_settings(marketplace={"autoUpdate": True}), encoding="utf-8")

    findings = scan_tree(root=tmp_path)

    flagged = sorted(finding.split(":", maxsplit=1)[0] for finding in findings)
    assert flagged == [
        ".claude/hooks/refresh.sh",
        ".claude/settings.json",
        ".claude/skills/refresh/SKILL.md",
        "justfile",
        "livespec_dev_tooling/verb.py",
    ]


def test_member_settings_are_scanned_for_each_named_member_that_has_a_clone(
    *, tmp_path: Path
) -> None:
    bad = tmp_path / "alpha" / ".claude" / "settings.json"
    bad.parent.mkdir(parents=True)
    _ = bad.write_text(_settings(marketplace={"autoUpdate": True}), encoding="utf-8")
    good = tmp_path / "beta" / ".claude" / "settings.json"
    good.parent.mkdir(parents=True)
    _ = good.write_text(_settings(), encoding="utf-8")

    findings = scan_member_settings(clones_root=tmp_path, names=("alpha", "beta", "absent"))

    assert [finding.split(":", maxsplit=1)[0] for finding in findings] == [
        "alpha/.claude/settings.json"
    ]


def test_this_library_has_a_single_adoption_path_today() -> None:
    assert scan_tree(root=_REPO_ROOT) == ()


def test_the_justfile_ships_the_guard_as_an_operator_recipe() -> None:
    justfile = (_REPO_ROOT / "justfile").read_text(encoding="utf-8")

    assert "\nplugin-adoption-path:\n" in justfile
    assert "livespec_dev_tooling.fleet.plugin_adoption_path" in justfile
