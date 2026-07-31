"""Outside-in tests for `driver_checks/_plugin_structure_claude.py`.

The CLAUDE packaging-profile invariants (and the byte-identical shared
helpers this module owns — `EXPECTED_SKILLS`, `FRONTMATTER_NAME_RE`, and
`fenced_invocation_violations`). These tests build synthetic claude
plugin trees under `tmp_path` and drive the public `claude_profile_violations`
entry point; the fine-grained `_`-prefixed helpers are covered
transitively. The synthetic-tree builders (`_make_claude_tree`, `_w`) are
imported from the parent `test_plugin_structure` module (the cross-test
fixture pattern this package's conftest enables). No subprocess is ever
spawned and the real repo is never read.

Coverage target: 100% line + branch of `_plugin_structure_claude.py`,
covering each individual invariant violated so a silently-weakened gate
cannot pass.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from returns.unsafe import unsafe_perform_io
from test_plugin_structure import _make_claude_tree, _w

from livespec_dev_tooling.driver_checks import _plugin_structure_claude

__all__: list[str] = []


# Assembled (never the literal token) — the banned Driver-root placeholder a
# fenced wrapper invocation must not use.
_DRIVER_TOKEN = "CLAUDE_PLUGIN" + "_ROOT"


def _joined(*, violations: list[str]) -> str:
    return "\n".join(violations)


# ⛔ CORRECTED, NOT UPDATED. Five tests in this suite were named
# `*_unreadable` and every one of them wrote `{ not json` — which is
# INVALID, not unreadable. Not one ever exercised a file that could not be
# READ. The fused `unreadable/invalid` diagnostic made the misnomer
# invisible, and the absence of any real unreadable-file coverage is
# precisely why the collapse survived. They assert INVALID now, and say so
# in their names; the unreadable condition is covered for the first time in
# `test_plugin_structure_unreadable.py`.


def _claude_violations(*, root: Path) -> list[str]:
    """The violation list, unwrapped — these trees are all READABLE."""
    return unsafe_perform_io(_plugin_structure_claude.claude_profile_violations(root=root).unwrap())


def test_claude_profile_valid_passes(*, tmp_path: Path) -> None:
    """A fully-valid claude tree yields zero violations (every False arm + is_dir filter)."""
    _make_claude_tree(root=tmp_path)
    assert _claude_violations(root=tmp_path) == []


def test_claude_fenced_invocation_all_branches(*, tmp_path: Path) -> None:
    """One SKILL.md exercising every arm of the shared fenced-invocation helper."""
    _make_claude_tree(root=tmp_path)
    _w(
        path=tmp_path / ".claude-plugin" / "skills" / "seed" / "SKILL.md",
        content="\n".join(
            [
                "---",
                "name: seed",
                "description: stub",
                "---",
                "Outside the fence bin/x.py reference is ignored",
                "```",
                "plain in-fence line without any wrapper",
                "python bin/seed.py --root $LIVESPEC_CORE_ROOT",
                f"uv run python .claude-plugin/scripts/bin/seed.py {_DRIVER_TOKEN}",
                "```",
            ]
        )
        + "\n",
    )
    text = _joined(violations=_claude_violations(root=tmp_path))
    assert "uv run" in text
    assert "literal .claude-plugin path" in text
    assert "Driver's own plugin-root" in text
    assert "MUST use $LIVESPEC_CORE_ROOT" in text


def test_claude_manifest_plugin_invalid(*, tmp_path: Path) -> None:
    _make_claude_tree(root=tmp_path)
    _w(path=tmp_path / ".claude-plugin" / "plugin.json", content="{ not json")
    assert any("plugin.json invalid" in v for v in _claude_violations(root=tmp_path))


def test_claude_manifest_marketplace_invalid(*, tmp_path: Path) -> None:
    _make_claude_tree(root=tmp_path)
    _w(path=tmp_path / ".claude-plugin" / "marketplace.json", content="{ not json")
    assert any("marketplace.json invalid" in v for v in _claude_violations(root=tmp_path))


def test_claude_manifest_plugin_name_wrong(*, tmp_path: Path) -> None:
    _make_claude_tree(root=tmp_path)
    _w(
        path=tmp_path / ".claude-plugin" / "plugin.json",
        content=json.dumps({"name": "wrong", "description": "DESC"}),
    )
    assert any(
        "plugin.json name MUST be 'livespec'" in v for v in _claude_violations(root=tmp_path)
    )


def test_claude_manifest_marketplace_name_wrong(*, tmp_path: Path) -> None:
    _make_claude_tree(root=tmp_path)
    _w(
        path=tmp_path / ".claude-plugin" / "marketplace.json",
        content=json.dumps(
            {
                "name": "wrong",
                "plugins": [
                    {"name": "livespec", "source": "./.claude-plugin", "description": "DESC"}
                ],
            }
        ),
    )
    assert any(
        "marketplace.json name MUST be 'livespec-driver-claude'" in v
        for v in _claude_violations(root=tmp_path)
    )


def test_claude_manifest_entries_not_one(*, tmp_path: Path) -> None:
    _make_claude_tree(root=tmp_path)
    _w(
        path=tmp_path / ".claude-plugin" / "marketplace.json",
        content=json.dumps({"name": "livespec-driver-claude", "plugins": []}),
    )
    assert "marketplace.json MUST list exactly one plugin; got 0" in _claude_violations(
        root=tmp_path
    )


def test_claude_manifest_entry_fields_wrong(*, tmp_path: Path) -> None:
    _make_claude_tree(root=tmp_path)
    _w(
        path=tmp_path / ".claude-plugin" / "marketplace.json",
        content=json.dumps(
            {
                "name": "livespec-driver-claude",
                "plugins": [{"name": "wrong", "source": "./elsewhere", "description": "OTHER"}],
            }
        ),
    )
    text = _joined(violations=_claude_violations(root=tmp_path))
    assert "marketplace plugin entry name MUST be 'livespec'" in text
    assert "marketplace plugin entry source MUST be './.claude-plugin'" in text
    assert "marketplace plugin description MUST duplicate plugin.json's verbatim" in text


def test_claude_skill_set_missing_directory(*, tmp_path: Path) -> None:
    _make_claude_tree(root=tmp_path)
    shutil.rmtree(tmp_path / ".claude-plugin" / "skills" / "seed")
    assert any(
        "missing skill directory: skills/seed/" in v for v in _claude_violations(root=tmp_path)
    )


def test_claude_skill_set_absent_skills_dir_fails_soft(*, tmp_path: Path) -> None:
    """A claude tree with NO `skills/` dir at all → a clean 'missing skills directory'
    violation, never an uncaught FileNotFoundError. This is the exact topology of
    livespec-core: a `.claude-plugin/` artifact carrier with plugin.json but no
    skills tree. The codex profile already fails soft here (`_codex_skill_set_violations`
    guards a missing skills dir); the claude profile must too."""
    _make_claude_tree(root=tmp_path)
    shutil.rmtree(tmp_path / ".claude-plugin" / "skills")
    assert any(
        "missing skills directory: .claude-plugin/skills/" in v
        for v in _claude_violations(root=tmp_path)
    )


def test_claude_skill_set_unexpected_directory(*, tmp_path: Path) -> None:
    _make_claude_tree(root=tmp_path)
    _w(
        path=tmp_path / ".claude-plugin" / "skills" / "extra" / "SKILL.md",
        content="---\nname: extra\n---\n",
    )
    assert any(
        "unexpected skill directory: skills/extra/" in v for v in _claude_violations(root=tmp_path)
    )


def test_claude_skill_set_missing_skill_md(*, tmp_path: Path) -> None:
    _make_claude_tree(root=tmp_path)
    (tmp_path / ".claude-plugin" / "skills" / "doctor" / "SKILL.md").unlink()
    assert any("missing skills/doctor/SKILL.md" in v for v in _claude_violations(root=tmp_path))


def test_claude_skill_set_frontmatter_name_absent(*, tmp_path: Path) -> None:
    _make_claude_tree(root=tmp_path)
    _w(
        path=tmp_path / ".claude-plugin" / "skills" / "revise" / "SKILL.md",
        content="no frontmatter name here\n",
    )
    assert any(
        "skills/revise/SKILL.md frontmatter name MUST be 'revise'; got None" in v
        for v in _claude_violations(root=tmp_path)
    )


def test_claude_skill_set_frontmatter_name_wrong(*, tmp_path: Path) -> None:
    _make_claude_tree(root=tmp_path)
    _w(
        path=tmp_path / ".claude-plugin" / "skills" / "critique" / "SKILL.md",
        content="---\nname: other\n---\n",
    )
    assert any(
        "skills/critique/SKILL.md frontmatter name MUST be 'critique'; got 'other'" in v
        for v in _claude_violations(root=tmp_path)
    )
