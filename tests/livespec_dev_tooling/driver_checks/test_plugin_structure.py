"""Outside-in test for `driver_checks/plugin_structure.py` — profile dispatch + re-export.

The unified structural gate reconciles the two formerly-divergent Driver
copies (CLAUDE + CODEX packaging profiles) into one profile-auto-detecting
check. The per-profile invariant sets now live in two cohesive helper
modules (`_plugin_structure_claude`, `_plugin_structure_codex`) exercised
by their own mirror test files; this file exercises the parent dispatch
surface — `detect_profile`, and `main` (which drives `run_check`'s
detect → dispatch → emit/skip path). It also proves the re-export is
wired: `run_check` invokes the `claude_profile_violations` /
`codex_profile_violations` names re-imported into this module.

This module OWNS the synthetic-tree builders (`_make_claude_tree`,
`_make_codex_tree`) and the `_w` writer; the profile mirror test modules
import them from here (via the driver_checks-test conftest sys.path
insertion). No subprocess is ever spawned and the real repo is never read.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from livespec_dev_tooling.driver_checks import plugin_structure

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


def _w(*, path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Synthetic-tree builders (no conditionals — each just writes a valid tree).
# Shared with the profile mirror test modules.
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
# main() — argparse + root resolution + run_check dispatch/emit/skip, which
# drives the re-imported claude_profile_violations / codex_profile_violations.
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
