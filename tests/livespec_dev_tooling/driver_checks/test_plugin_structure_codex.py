"""Outside-in tests for `driver_checks/_plugin_structure_codex.py`.

The CODEX packaging-profile invariants. These tests build synthetic codex
plugin trees under `tmp_path` and drive the public `codex_profile_violations`
entry point; the fine-grained `_`-prefixed helpers are covered
transitively. The synthetic-tree builder (`_make_codex_tree`, `_w`) is
imported from the parent `test_plugin_structure` module (the cross-test
fixture pattern this package's conftest enables). No subprocess is ever
spawned and the real repo is never read.

Coverage target: 100% line + branch of `_plugin_structure_codex.py`,
covering each individual invariant violated so a silently-weakened gate
cannot pass.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from test_plugin_structure import _make_codex_tree, _w

from livespec_dev_tooling.driver_checks import _plugin_structure_codex

__all__: list[str] = []


def _joined(*, violations: list[str]) -> str:
    return "\n".join(violations)


def _codex_violations(*, root: Path) -> list[str]:
    return _plugin_structure_codex.codex_profile_violations(root=root)


def test_codex_profile_valid_passes(*, tmp_path: Path) -> None:
    """A fully-valid codex tree yields zero violations (every False arm + is_dir filter)."""
    _make_codex_tree(root=tmp_path)
    assert _codex_violations(root=tmp_path) == []


def test_codex_marketplace_unreadable(*, tmp_path: Path) -> None:
    _make_codex_tree(root=tmp_path)
    _w(path=tmp_path / ".agents" / "plugins" / "marketplace.json", content="{ not json")
    assert any(
        ".agents/plugins/marketplace.json unreadable/invalid" in v
        for v in _codex_violations(root=tmp_path)
    )


def test_codex_marketplace_name_wrong(*, tmp_path: Path) -> None:
    _make_codex_tree(root=tmp_path)
    _w(
        path=tmp_path / ".agents" / "plugins" / "marketplace.json",
        content=json.dumps(
            {
                "name": "wrong",
                "plugins": [
                    {
                        "name": "livespec",
                        "source": {"source": "local", "path": "./livespec"},
                        "description": "DESC",
                    }
                ],
            }
        ),
    )
    assert any(
        "marketplace.json name MUST be 'livespec-driver-codex'" in v
        for v in _codex_violations(root=tmp_path)
    )


def test_codex_marketplace_entries_not_one_and_manifest_desc_skipped(*, tmp_path: Path) -> None:
    """plugins=[] → marketplace returns description None, so the manifest desc check skips."""
    _make_codex_tree(root=tmp_path)
    _w(
        path=tmp_path / ".agents" / "plugins" / "marketplace.json",
        content=json.dumps({"name": "livespec-driver-codex", "plugins": []}),
    )
    violations = _codex_violations(root=tmp_path)
    assert "marketplace.json MUST list exactly one plugin; got 0" in violations
    # The otherwise-valid manifest produces no description violation (market desc is None).
    assert not any("description MUST duplicate" in v for v in violations)


def test_codex_marketplace_entry_name_and_source_wrong(*, tmp_path: Path) -> None:
    _make_codex_tree(root=tmp_path)
    _w(
        path=tmp_path / ".agents" / "plugins" / "marketplace.json",
        content=json.dumps(
            {
                "name": "livespec-driver-codex",
                "plugins": [{"name": "wrong", "source": "./elsewhere", "description": "DESC"}],
            }
        ),
    )
    text = _joined(violations=_codex_violations(root=tmp_path))
    assert "marketplace plugin entry name MUST be 'livespec'" in text
    assert "marketplace plugin entry source MUST be" in text


def test_codex_manifest_unreadable(*, tmp_path: Path) -> None:
    _make_codex_tree(root=tmp_path)
    _w(path=tmp_path / "livespec" / ".codex-plugin" / "plugin.json", content="{ not json")
    assert any(
        "livespec/.codex-plugin/plugin.json unreadable/invalid" in v
        for v in _codex_violations(root=tmp_path)
    )


def test_codex_manifest_field_violations_and_desc_mismatch(*, tmp_path: Path) -> None:
    _make_codex_tree(root=tmp_path)
    _w(
        path=tmp_path / "livespec" / ".codex-plugin" / "plugin.json",
        content=json.dumps(
            {"name": "wrong", "version": "", "skills": "x", "hooks": "y", "description": "OTHER"}
        ),
    )
    text = _joined(violations=_codex_violations(root=tmp_path))
    assert "plugin.json name MUST be 'livespec'" in text
    assert "plugin.json version MUST be non-empty" in text
    assert "plugin.json skills MUST be './skills/'" in text
    assert "plugin.json hooks MUST be './hooks/hooks.json'" in text
    assert "marketplace plugin description MUST duplicate plugin.json's verbatim" in text


def test_codex_skill_set_missing_skills_dir(*, tmp_path: Path) -> None:
    _make_codex_tree(root=tmp_path)
    shutil.rmtree(tmp_path / "livespec" / "skills")
    assert "missing skills directory: livespec/skills/" in _codex_violations(root=tmp_path)


def test_codex_skill_set_missing_and_extra(*, tmp_path: Path) -> None:
    _make_codex_tree(root=tmp_path)
    shutil.rmtree(tmp_path / "livespec" / "skills" / "seed")
    _w(
        path=tmp_path / "livespec" / "skills" / "extra" / "SKILL.md",
        content="---\nname: extra\ndescription: x\n---\ncodex plugin list --json -m livespec\n",
    )
    text = _joined(violations=_codex_violations(root=tmp_path))
    assert "missing skill directory: skills/seed/" in text
    assert "unexpected skill directory: skills/extra/" in text


def test_codex_skill_set_missing_skill_md(*, tmp_path: Path) -> None:
    _make_codex_tree(root=tmp_path)
    (tmp_path / "livespec" / "skills" / "doctor" / "SKILL.md").unlink()
    assert any("missing skills/doctor/SKILL.md" in v for v in _codex_violations(root=tmp_path))


def test_codex_skill_set_frontmatter_empty_file(*, tmp_path: Path) -> None:
    """An empty SKILL.md → `_frontmatter_block` `not lines` arm → 'MUST open' violation."""
    _make_codex_tree(root=tmp_path)
    _w(path=tmp_path / "livespec" / "skills" / "help" / "SKILL.md", content="")
    assert any(
        "skills/help/SKILL.md MUST open with a `---`-fenced frontmatter block" in v
        for v in _codex_violations(root=tmp_path)
    )


def test_codex_skill_set_frontmatter_no_opening_fence(*, tmp_path: Path) -> None:
    """A SKILL.md whose first line is not `---` → frontmatter parser returns None."""
    _make_codex_tree(root=tmp_path)
    _w(
        path=tmp_path / "livespec" / "skills" / "help" / "SKILL.md",
        content="not a fence\nsecond line\n",
    )
    assert any(
        "skills/help/SKILL.md MUST open with a `---`-fenced frontmatter block" in v
        for v in _codex_violations(root=tmp_path)
    )


def test_codex_skill_set_frontmatter_no_closing_fence(*, tmp_path: Path) -> None:
    """A SKILL.md with an opening fence but no closing fence → parser loop exhausts → None."""
    _make_codex_tree(root=tmp_path)
    _w(
        path=tmp_path / "livespec" / "skills" / "help" / "SKILL.md",
        content="---\nname: help\nno closing fence here\n",
    )
    assert any(
        "skills/help/SKILL.md MUST open with a `---`-fenced frontmatter block" in v
        for v in _codex_violations(root=tmp_path)
    )


def test_codex_skill_set_name_absent_and_desc_absent(*, tmp_path: Path) -> None:
    _make_codex_tree(root=tmp_path)
    _w(
        path=tmp_path / "livespec" / "skills" / "next" / "SKILL.md",
        content="---\nirrelevant: x\n---\ncodex plugin list --json -m livespec\n",
    )
    text = _joined(violations=_codex_violations(root=tmp_path))
    assert "skills/next/SKILL.md frontmatter name MUST be 'next'; got None" in text
    assert "skills/next/SKILL.md frontmatter description MUST be non-empty" in text


def test_codex_skill_set_name_wrong_and_allowed_tools(*, tmp_path: Path) -> None:
    _make_codex_tree(root=tmp_path)
    _w(
        path=tmp_path / "livespec" / "skills" / "revise" / "SKILL.md",
        content=(
            "---\nname: other\ndescription: d\nallowed-tools: Bash\n---\n"
            "codex plugin list --json -m livespec\n"
        ),
    )
    text = _joined(violations=_codex_violations(root=tmp_path))
    assert "skills/revise/SKILL.md frontmatter name MUST be 'revise'; got 'other'" in text
    assert "skills/revise/SKILL.md frontmatter MUST NOT carry an 'allowed-tools' key" in text


def test_codex_binding_body_all_bans(*, tmp_path: Path) -> None:
    """A no-frontmatter body missing the snippet and carrying every banned Claude marker."""
    _make_codex_tree(root=tmp_path)
    _w(
        path=tmp_path / "livespec" / "skills" / "doctor" / "SKILL.md",
        content=(
            "Run /livespec:doctor via installed_plugins.json in the Claude Code Driver "
            "shipped from livespec-driver-claude.\n"
        ),
    )
    text = _joined(violations=_codex_violations(root=tmp_path))
    assert "MUST carry the Codex core-resolution invocation" in text
    assert "MUST NOT use the '/livespec:' slash-command form" in text
    assert "MUST NOT reference 'installed_plugins.json'" in text
    assert "MUST NOT contain the phrase 'Claude Code Driver'" in text
    assert "MUST NOT reference the sibling repo 'livespec-driver-claude'" in text


def test_codex_binding_body_indented_closing_fence(*, tmp_path: Path) -> None:
    """An indented closing fence makes the body-trim `find` return -1 (body stays full text)."""
    _make_codex_tree(root=tmp_path)
    # Valid frontmatter NAME+description (so skill-set passes), but an INDENTED
    # closing fence so the binding-body trim's `text.find('\\n---')` returns -1.
    _w(
        path=tmp_path / "livespec" / "skills" / "doctor" / "SKILL.md",
        content="---\nname: doctor\ndescription: d\n  ---\ncodex plugin list --json -m livespec\n",
    )
    # The full text still carries the snippet and no banned marker → no binding-body violation.
    assert not any("core-resolution invocation" in v for v in _codex_violations(root=tmp_path))


def test_codex_hook_bundle_guard_missing_and_unreadable(*, tmp_path: Path) -> None:
    _make_codex_tree(root=tmp_path)
    (tmp_path / "livespec" / "hooks" / "livespec_footgun_guard.py").unlink()
    _w(path=tmp_path / "livespec" / "hooks" / "hooks.json", content="{ not json")
    text = _joined(violations=_codex_violations(root=tmp_path))
    assert "missing livespec/hooks/livespec_footgun_guard.py" in text
    assert "livespec/hooks/hooks.json unreadable/invalid" in text


def test_codex_hook_bundle_top_level_description(*, tmp_path: Path) -> None:
    _make_codex_tree(root=tmp_path)
    _w(
        path=tmp_path / "livespec" / "hooks" / "hooks.json",
        content=json.dumps(
            {
                "description": "banned",
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "Bash",
                            "hooks": [{"command": "python livespec_footgun_guard.py"}],
                        }
                    ]
                },
            }
        ),
    )
    assert any(
        "MUST NOT carry a top-level 'description' key" in v
        for v in _codex_violations(root=tmp_path)
    )


def test_codex_hook_bundle_no_bash_entry(*, tmp_path: Path) -> None:
    _make_codex_tree(root=tmp_path)
    _w(
        path=tmp_path / "livespec" / "hooks" / "hooks.json",
        content=json.dumps({"hooks": {"PreToolUse": [{"matcher": "Other", "hooks": []}]}}),
    )
    assert "hooks.json MUST register a PreToolUse entry with matcher 'Bash'" in _codex_violations(
        root=tmp_path
    )


def test_codex_hook_bundle_guard_not_referenced(*, tmp_path: Path) -> None:
    _make_codex_tree(root=tmp_path)
    _w(
        path=tmp_path / "livespec" / "hooks" / "hooks.json",
        content=json.dumps(
            {
                "hooks": {
                    "PreToolUse": [{"matcher": "Bash", "hooks": [{"command": "python other.py"}]}]
                }
            }
        ),
    )
    assert (
        "hooks.json PreToolUse/Bash entry MUST reference 'livespec_footgun_guard.py'"
        in _codex_violations(root=tmp_path)
    )
