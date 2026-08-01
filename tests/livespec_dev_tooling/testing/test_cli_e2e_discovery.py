"""Outside-in tests for `testing/_cli_e2e_discovery.py`.

Per `livespec/SPECIFICATION/contracts.md` §"CLI end-to-end harness contract",
the structural skill-discovery (`discover_skills`) and per-skill fixtures
loader (`discover_fixtures`) components walk the on-disk tree as the source of
truth. These tests cover the discovery edge branches (unparsable manifest,
non-object manifest, missing/blank `name`, absent `skills/` dir, a `skills/`
child that is a file or lacks `SKILL.md`) and the fixtures loader edge branches
(non-dir child, missing `prompt.md`, absent vs. present `expected_files.txt`,
comment/blank lines).

BOTH WALKS ARE ON THE `IOResult` RAILWAY since `8o8e` pair B, so every
assertion here reads the UNWRAPPED VALUE rather than the container. The
container-versus-payload confusion is not hypothetical in this repo:
`frozenset(IOResult.unwrap())` shipped once and silently produced a set holding
the wrapper, because `.unwrap()` on an `IOResult` yields an `IO[...]`.

⛔ FOUR TESTS HERE USED TO ASSERT `== {}` AND WERE RENAMED, not merely
rewritten. A manifest that is unparsable, non-object, or carries no usable
`name` is a BROKEN PLUGIN, and the old names said "skips" — which is the same
conflation the conversion removed, one layer out. The `manifest-absent` and
unreadable-tree arms live in `test_cli_e2e_discovery_railway.py` beside the
vacuous-gate headline they belong to.

The synthetic plugin/fixture builders (`_make_plugin`, `_make_fixture`) are
imported from the parent `test_cli_e2e` module (the cross-test fixture pattern
this package's conftest enables).

Coverage target: 100% line + branch of `_cli_e2e_discovery.py`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from test_cli_e2e import _make_fixture, _make_plugin

from livespec_dev_tooling.testing import cli_e2e
from livespec_dev_tooling.testing._cli_e2e_discovery import (
    FixturedSkill,
    discover_fixtures,
    discover_skills,
)

_VENDOR_DIR = Path(cli_e2e.__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware import.

__all__: list[str] = []


def _skills(*, plugin_install_dirs: tuple[Path, ...]) -> dict[str, tuple[str, ...]]:
    """`discover_skills`' success VALUE; a failure track raises here, loudly."""
    return unsafe_perform_io(discover_skills(plugin_install_dirs=plugin_install_dirs).unwrap())


def _fixtures(*, fixtures_root: Path) -> dict[str, FixturedSkill]:
    """`discover_fixtures`' success VALUE; a failure track raises here, loudly."""
    return unsafe_perform_io(discover_fixtures(fixtures_root=fixtures_root).unwrap())


def _failure_reason(*, plugin_dir: Path) -> str:
    """The `reason` discriminator off `discover_skills`' failure track."""
    return unsafe_perform_io(discover_skills(plugin_install_dirs=(plugin_dir,)).failure()).reason


def _manifest_plugin(*, root: Path, body: str) -> Path:
    """A plugin root whose `plugin.json` carries exactly `body`."""
    root.mkdir(parents=True)
    _ = (root / "plugin.json").write_text(body, encoding="utf-8")
    return root


# ---------------------------------------------------------------------------
# Structural skill discovery.
# ---------------------------------------------------------------------------


def test_discover_skills_reads_prefix_and_walks_skill_dirs(*, tmp_path: Path) -> None:
    plugin = _make_plugin(
        root=tmp_path / "p", name="livespec", skills={"seed": True, "doctor": True}
    )
    assert _skills(plugin_install_dirs=(plugin,)) == {"livespec": ("doctor", "seed")}


def test_discover_skills_fails_on_unparsable_manifest(*, tmp_path: Path) -> None:
    plugin_dir = _manifest_plugin(root=tmp_path / "bad-json", body="{not json")
    assert _failure_reason(plugin_dir=plugin_dir) == "manifest-not-json"


def test_discover_skills_fails_on_non_object_manifest(*, tmp_path: Path) -> None:
    plugin_dir = _manifest_plugin(root=tmp_path / "list-json", body="[1, 2, 3]")
    assert _failure_reason(plugin_dir=plugin_dir) == "manifest-not-an-object"


def test_discover_skills_fails_on_manifest_missing_name(*, tmp_path: Path) -> None:
    plugin_dir = _manifest_plugin(root=tmp_path / "no-name", body=json.dumps({"version": "0.1.0"}))
    assert _failure_reason(plugin_dir=plugin_dir) == "manifest-no-name"


def test_discover_skills_fails_on_manifest_blank_name(*, tmp_path: Path) -> None:
    """A present-but-empty `name` is as unusable as an absent one, and says so."""
    plugin_dir = _manifest_plugin(root=tmp_path / "blank-name", body=json.dumps({"name": ""}))
    assert _failure_reason(plugin_dir=plugin_dir) == "manifest-no-name"


def test_discover_skills_empty_when_no_skills_dir(*, tmp_path: Path) -> None:
    plugin_dir = _manifest_plugin(
        root=tmp_path / "no-skills-dir", body=json.dumps({"name": "livespec"})
    )
    assert _skills(plugin_install_dirs=(plugin_dir,)) == {"livespec": ()}


def test_discover_skills_skips_skill_child_without_skill_md(*, tmp_path: Path) -> None:
    plugin = _make_plugin(
        root=tmp_path / "p", name="livespec", skills={"good": True, "empty": False}
    )
    # A stray FILE inside skills/ must also be ignored.
    _ = (plugin / "skills" / "stray.txt").write_text("x", encoding="utf-8")
    assert _skills(plugin_install_dirs=(plugin,)) == {"livespec": ("good",)}


def test_discover_skills_over_no_plugins_at_all_is_an_empty_map() -> None:
    """Zero declared roots is an ANSWER — the empty-collection arm of the fold."""
    assert _skills(plugin_install_dirs=()) == {}


# ---------------------------------------------------------------------------
# Per-skill fixtures loader.
# ---------------------------------------------------------------------------


def test_discover_fixtures_absent_root_yields_empty(*, tmp_path: Path) -> None:
    assert _fixtures(fixtures_root=tmp_path / "nope") == {}


def test_discover_fixtures_loads_prompt_and_expected(*, tmp_path: Path) -> None:
    root = tmp_path / "fixtures"
    _make_fixture(root=root, skill="seed", prompt="/livespec:seed go", expected=("a.md", "b.md"))
    fixtures = _fixtures(fixtures_root=root)
    assert set(fixtures) == {"seed"}
    assert fixtures["seed"].prompt == "/livespec:seed go"
    assert fixtures["seed"].expected_files == ("a.md", "b.md")


def test_discover_fixtures_absent_expected_files_means_no_assertions(*, tmp_path: Path) -> None:
    root = tmp_path / "fixtures"
    _make_fixture(root=root, skill="help", prompt="/livespec:help", expected=None)
    assert _fixtures(fixtures_root=root)["help"].expected_files == ()


def test_discover_fixtures_skips_non_dir_child(*, tmp_path: Path) -> None:
    root = tmp_path / "fixtures"
    root.mkdir()
    _ = (root / "README.md").write_text("not a fixture dir", encoding="utf-8")
    assert _fixtures(fixtures_root=root) == {}


def test_discover_fixtures_skips_dir_without_prompt(*, tmp_path: Path) -> None:
    root = tmp_path / "fixtures"
    (root / "incomplete").mkdir(parents=True)
    assert _fixtures(fixtures_root=root) == {}


def test_discover_fixtures_strips_comments_and_blanks_in_expected(*, tmp_path: Path) -> None:
    root = tmp_path / "fixtures"
    sd = root / "seed"
    sd.mkdir(parents=True)
    _ = (sd / "prompt.md").write_text("/livespec:seed", encoding="utf-8")
    _ = (sd / "expected_files.txt").write_text(
        "# a comment\n\nSPECIFICATION/spec.md\n   \n# trailing\n",
        encoding="utf-8",
    )
    assert _fixtures(fixtures_root=root)["seed"].expected_files == ("SPECIFICATION/spec.md",)
