"""Outside-in test for `livespec_dev_tooling/checks/plugin_structure.py`.

The unified structural gate reconciles the two formerly-divergent Driver
copies (CLAUDE + CODEX packaging profiles) into one profile-auto-detecting
check. These tests build synthetic plugin trees under `tmp_path` and drive
the module's PUBLIC entry points — `claude_profile_violations`,
`codex_profile_violations`, `detect_profile`, and `main` (which exercises
`run_check`) — exactly as `test_plugin_resolution.py` drives `load_harnesses`
/ `main`; the fine-grained `_`-prefixed helpers are covered transitively.
No subprocess is ever spawned and the real repo is never read.

Coverage targets every branch of both profiles: the self-skip when neither
manifest is present; a passing claude tree and a passing codex tree; and
each individual invariant violated, per profile, so a silently-weakened
gate cannot pass these tests.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from livespec_dev_tooling.checks import plugin_structure

__all__: list[str] = []


_SKILLS = (
    "seed",
    "propose-change",
    "critique",
    "revise",
    "doctor",
    "prune-history",
    "next",
    "help",
)

# Assembled (never the literal token) — the banned Driver-root placeholder a
# fenced wrapper invocation must not use.
_DRIVER_TOKEN = "CLAUDE_PLUGIN" + "_ROOT"


def _w(*, path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(content, encoding="utf-8")


def _joined(*, violations: list[str]) -> str:
    return "\n".join(violations)


# ---------------------------------------------------------------------------
# Synthetic-tree builders (no conditionals — each just writes a valid tree).
# ---------------------------------------------------------------------------


def _make_claude_tree(*, root: Path) -> None:
    plugin_dir = root / ".claude-plugin"
    _w(
        path=plugin_dir / "plugin.json",
        content=json.dumps({"name": "livespec", "description": "DESC"}),
    )
    _w(
        path=plugin_dir / "marketplace.json",
        content=json.dumps(
            {
                "name": "livespec-driver-claude",
                "plugins": [
                    {"name": "livespec", "source": "./.claude-plugin", "description": "DESC"}
                ],
            }
        ),
    )
    for op in _SKILLS:
        _w(
            path=plugin_dir / "skills" / op / "SKILL.md",
            content=f"---\nname: {op}\ndescription: stub\n---\nBody for {op}.\n",
        )
    # A stray non-directory entry exercises the `if p.is_dir()` False arm.
    _w(path=plugin_dir / "skills" / "README.md", content="not a skill dir\n")


def _make_codex_tree(*, root: Path) -> None:
    _w(
        path=root / ".agents" / "plugins" / "marketplace.json",
        content=json.dumps(
            {
                "name": "livespec-driver-codex",
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
    plugin = root / "livespec"
    _w(
        path=plugin / ".codex-plugin" / "plugin.json",
        content=json.dumps(
            {
                "name": "livespec",
                "version": "0.1.0",
                "skills": "./skills/",
                "hooks": "./hooks/hooks.json",
                "description": "DESC",
            }
        ),
    )
    for op in _SKILLS:
        _w(
            path=plugin / "skills" / op / "SKILL.md",
            content=(
                f"---\nname: {op}\ndescription: A {op} skill.\n---\n"
                "Use codex plugin list --json -m livespec to resolve core.\n"
            ),
        )
    _w(path=plugin / "skills" / "README.md", content="stray\n")
    _w(
        path=plugin / "hooks" / "hooks.json",
        content=json.dumps(
            {
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "Bash",
                            "hooks": [{"command": "python livespec_footgun_guard.py"}],
                        }
                    ]
                }
            }
        ),
    )
    _w(path=plugin / "hooks" / "livespec_footgun_guard.py", content="# guard\n")


def _claude_violations(*, root: Path) -> list[str]:
    return plugin_structure.claude_profile_violations(root=root)


def _codex_violations(*, root: Path) -> list[str]:
    return plugin_structure.codex_profile_violations(root=root)


# ===========================================================================
# CLAUDE profile.
# ===========================================================================


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


def test_claude_manifest_plugin_unreadable(*, tmp_path: Path) -> None:
    _make_claude_tree(root=tmp_path)
    _w(path=tmp_path / ".claude-plugin" / "plugin.json", content="{ not json")
    assert any("plugin.json unreadable/invalid" in v for v in _claude_violations(root=tmp_path))


def test_claude_manifest_marketplace_unreadable(*, tmp_path: Path) -> None:
    _make_claude_tree(root=tmp_path)
    _w(path=tmp_path / ".claude-plugin" / "marketplace.json", content="{ not json")
    assert any(
        "marketplace.json unreadable/invalid" in v for v in _claude_violations(root=tmp_path)
    )


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


# ===========================================================================
# CODEX profile.
# ===========================================================================


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


# ===========================================================================
# Profile detection.
# ===========================================================================


def test_detect_profile_claude(*, tmp_path: Path) -> None:
    _make_claude_tree(root=tmp_path)
    assert plugin_structure.detect_profile(root=tmp_path) == "claude"


def test_detect_profile_codex(*, tmp_path: Path) -> None:
    _make_codex_tree(root=tmp_path)
    assert plugin_structure.detect_profile(root=tmp_path) == "codex"


def test_detect_profile_none(*, tmp_path: Path) -> None:
    assert plugin_structure.detect_profile(root=tmp_path) is None


# ===========================================================================
# main() — argparse + root resolution + run_check dispatch/emit/skip.
# ===========================================================================


def test_main_skips_via_cwd(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No --project-root → resolves Path.cwd(); empty cwd → self-skip, exit 0."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.argv", ["check-plugin-structure"])
    assert plugin_structure.main() == 0


def test_main_claude_pass_via_project_root(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--project-root resolves the given path; a valid claude tree → exit 0 (claude dispatch arm)."""
    _make_claude_tree(root=tmp_path)
    monkeypatch.setattr("sys.argv", ["check-plugin-structure", "--project-root", str(tmp_path)])
    assert plugin_structure.main() == 0


def test_main_codex_fail_via_project_root(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A broken codex tree under --project-root → exit 1 (codex dispatch arm + emit loop)."""
    _make_codex_tree(root=tmp_path)
    (tmp_path / "livespec" / "hooks" / "livespec_footgun_guard.py").unlink()
    monkeypatch.setattr("sys.argv", ["check-plugin-structure", "--project-root", str(tmp_path)])
    assert plugin_structure.main() == 1
