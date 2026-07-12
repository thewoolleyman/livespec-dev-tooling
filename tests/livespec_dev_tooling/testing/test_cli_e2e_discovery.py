"""Outside-in tests for `testing/_cli_e2e_discovery.py`.

Per `livespec/SPECIFICATION/contracts.md` §"CLI end-to-end harness contract",
the structural skill-discovery (`discover_skills`) and per-skill fixtures
loader (`discover_fixtures`) components walk the on-disk tree as the source of
truth. These tests cover the discovery edge branches (missing manifest,
unparsable manifest, non-dict manifest, missing/blank `name`, absent `skills/`
dir, a `skills/` child that is a file or lacks `SKILL.md`) and the fixtures
loader edge branches (absent root, non-dir child, missing `prompt.md`, absent
vs. present `expected_files.txt`, comment/blank lines).

The synthetic plugin/fixture builders (`_make_plugin`, `_make_fixture`) are
imported from the parent `test_cli_e2e` module (the cross-test fixture pattern
this package's conftest enables).

Coverage target: 100% line + branch of `_cli_e2e_discovery.py`.
"""

from __future__ import annotations

import json
from pathlib import Path

from test_cli_e2e import _make_fixture, _make_plugin

from livespec_dev_tooling.testing._cli_e2e_discovery import discover_fixtures, discover_skills

__all__: list[str] = []


# ---------------------------------------------------------------------------
# Structural skill discovery.
# ---------------------------------------------------------------------------


def test_discover_skills_reads_prefix_and_walks_skill_dirs(*, tmp_path: Path) -> None:
    plugin = _make_plugin(
        root=tmp_path / "p", name="livespec", skills={"seed": True, "doctor": True}
    )
    discovered = discover_skills(plugin_install_dirs=(plugin,))
    assert discovered == {"livespec": ("doctor", "seed")}


def test_discover_skills_skips_plugin_with_missing_manifest(*, tmp_path: Path) -> None:
    plugin_dir = tmp_path / "no-manifest"
    (plugin_dir / "skills").mkdir(parents=True)
    discovered = discover_skills(plugin_install_dirs=(plugin_dir,))
    assert discovered == {}


def test_discover_skills_skips_unparsable_manifest(*, tmp_path: Path) -> None:
    plugin_dir = tmp_path / "bad-json"
    plugin_dir.mkdir()
    _ = (plugin_dir / "plugin.json").write_text("{not json", encoding="utf-8")
    discovered = discover_skills(plugin_install_dirs=(plugin_dir,))
    assert discovered == {}


def test_discover_skills_skips_non_dict_manifest(*, tmp_path: Path) -> None:
    plugin_dir = tmp_path / "list-json"
    plugin_dir.mkdir()
    _ = (plugin_dir / "plugin.json").write_text("[1, 2, 3]", encoding="utf-8")
    discovered = discover_skills(plugin_install_dirs=(plugin_dir,))
    assert discovered == {}


def test_discover_skills_skips_manifest_missing_name(*, tmp_path: Path) -> None:
    plugin_dir = tmp_path / "no-name"
    plugin_dir.mkdir()
    _ = (plugin_dir / "plugin.json").write_text(json.dumps({"version": "0.1.0"}), encoding="utf-8")
    discovered = discover_skills(plugin_install_dirs=(plugin_dir,))
    assert discovered == {}


def test_discover_skills_skips_manifest_blank_name(*, tmp_path: Path) -> None:
    plugin_dir = tmp_path / "blank-name"
    plugin_dir.mkdir()
    _ = (plugin_dir / "plugin.json").write_text(json.dumps({"name": ""}), encoding="utf-8")
    discovered = discover_skills(plugin_install_dirs=(plugin_dir,))
    assert discovered == {}


def test_discover_skills_empty_when_no_skills_dir(*, tmp_path: Path) -> None:
    plugin_dir = tmp_path / "no-skills-dir"
    plugin_dir.mkdir()
    _ = (plugin_dir / "plugin.json").write_text(json.dumps({"name": "livespec"}), encoding="utf-8")
    discovered = discover_skills(plugin_install_dirs=(plugin_dir,))
    assert discovered == {"livespec": ()}


def test_discover_skills_skips_skill_child_without_skill_md(*, tmp_path: Path) -> None:
    plugin = _make_plugin(
        root=tmp_path / "p", name="livespec", skills={"good": True, "empty": False}
    )
    # A stray FILE inside skills/ must also be ignored.
    _ = (plugin / "skills" / "stray.txt").write_text("x", encoding="utf-8")
    discovered = discover_skills(plugin_install_dirs=(plugin,))
    assert discovered == {"livespec": ("good",)}


# ---------------------------------------------------------------------------
# Per-skill fixtures loader.
# ---------------------------------------------------------------------------


def test_discover_fixtures_absent_root_yields_empty(*, tmp_path: Path) -> None:
    assert discover_fixtures(fixtures_root=tmp_path / "nope") == {}


def test_discover_fixtures_loads_prompt_and_expected(*, tmp_path: Path) -> None:
    root = tmp_path / "fixtures"
    _make_fixture(root=root, skill="seed", prompt="/livespec:seed go", expected=("a.md", "b.md"))
    fixtures = discover_fixtures(fixtures_root=root)
    assert set(fixtures) == {"seed"}
    assert fixtures["seed"].prompt == "/livespec:seed go"
    assert fixtures["seed"].expected_files == ("a.md", "b.md")


def test_discover_fixtures_absent_expected_files_means_no_assertions(*, tmp_path: Path) -> None:
    root = tmp_path / "fixtures"
    _make_fixture(root=root, skill="help", prompt="/livespec:help", expected=None)
    fixtures = discover_fixtures(fixtures_root=root)
    assert fixtures["help"].expected_files == ()


def test_discover_fixtures_skips_non_dir_child(*, tmp_path: Path) -> None:
    root = tmp_path / "fixtures"
    root.mkdir()
    _ = (root / "README.md").write_text("not a fixture dir", encoding="utf-8")
    assert discover_fixtures(fixtures_root=root) == {}


def test_discover_fixtures_skips_dir_without_prompt(*, tmp_path: Path) -> None:
    root = tmp_path / "fixtures"
    (root / "incomplete").mkdir(parents=True)
    assert discover_fixtures(fixtures_root=root) == {}


def test_discover_fixtures_strips_comments_and_blanks_in_expected(*, tmp_path: Path) -> None:
    root = tmp_path / "fixtures"
    sd = root / "seed"
    sd.mkdir(parents=True)
    _ = (sd / "prompt.md").write_text("/livespec:seed", encoding="utf-8")
    _ = (sd / "expected_files.txt").write_text(
        "# a comment\n\nSPECIFICATION/spec.md\n   \n# trailing\n",
        encoding="utf-8",
    )
    fixtures = discover_fixtures(fixtures_root=root)
    assert fixtures["seed"].expected_files == ("SPECIFICATION/spec.md",)
