"""_plugin_structure_codex — CODEX packaging-profile invariants.

Extracted verbatim from `plugin_structure` (the CODEX profile preserved
verbatim from the `livespec-driver-codex` copy). The helpers that are
byte-identical across both profiles — `EXPECTED_SKILLS`,
`FRONTMATTER_NAME_RE`, and `fenced_invocation_violations` — are imported
from `_plugin_structure_claude`, their single source.

CODEX profile invariants (preserved verbatim from the codex copy):

1. `.agents/plugins/marketplace.json` parses; top-level `name` is
   `livespec-driver-codex`; exactly one plugin entry named `livespec`
   whose `source` is the OBJECT `{"source":"local","path":"./livespec"}`
   and whose `description` duplicates the plugin manifest's verbatim.
2. `livespec/.codex-plugin/plugin.json` parses; `name` is `livespec`;
   `version` non-empty; `skills` is `./skills/`; `hooks` is
   `./hooks/hooks.json`.
3. All eight operations ship a SKILL.md under `livespec/skills/<op>/`
   with a `---`-fenced frontmatter whose `name` matches its directory
   and a non-empty `description`; no `allowed-tools` key; no extra skill
   directories exist.
4. Codex-binding body markers: the body MUST carry `codex plugin list
   --json -m livespec` and MUST NOT carry any Claude-specific marker
   (`/livespec:`, `installed_plugins.json`, `Claude Code Driver`,
   `livespec-driver-claude`).
5. Fenced wrapper-invocation rules (shared with the claude profile).
6. `livespec/hooks/hooks.json` parses, has NO top-level `description`
   key, and registers a PreToolUse/Bash matcher whose command references
   `livespec_footgun_guard.py`; the guard script exists.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from livespec_dev_tooling.driver_checks._plugin_structure_claude import (
    EXPECTED_SKILLS,
    FRONTMATTER_NAME_RE,
    fenced_invocation_violations,
)

__all__: list[str] = ["codex_profile_violations"]


# --- codex-only constants ---
# The Codex core-resolution invocation every SKILL.md body MUST carry.
_CODEX_RESOLUTION_SNIPPET = "codex plugin list --json -m livespec"
_FRONTMATTER_DESCRIPTION_RE = re.compile(r"^description:\s*(\S.*?)\s*$", re.MULTILINE)


def _frontmatter_block(*, text: str) -> str | None:
    """Return the `---`-fenced frontmatter block, or None if absent/malformed.

    The block MUST be the first thing in the file: an opening `---` line,
    body lines, then a closing `---` line.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            return "\n".join(lines[1:idx])
    return None


def _codex_marketplace_violations(*, root: Path) -> tuple[list[str], str | None]:
    """Validate the repo-root marketplace catalog.

    Returns (violations, plugin_description) — the catalog's plugin
    description is returned so the manifest check can compare it as the
    source of truth.
    """
    marketplace_path = root / ".agents" / "plugins" / "marketplace.json"
    out: list[str] = []
    try:
        marketplace = json.loads(marketplace_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [f".agents/plugins/marketplace.json unreadable/invalid: {exc}"], None
    if marketplace.get("name") != "livespec-driver-codex":
        out.append(
            "marketplace.json name MUST be 'livespec-driver-codex'; "
            f"got {marketplace.get('name')!r}"
        )
    entries = marketplace.get("plugins", [])
    if len(entries) != 1:
        out.append(f"marketplace.json MUST list exactly one plugin; got {len(entries)}")
        return out, None
    entry = entries[0]
    if entry.get("name") != "livespec":
        out.append(f"marketplace plugin entry name MUST be 'livespec'; got {entry.get('name')!r}")
    expected_source = {"source": "local", "path": "./livespec"}
    if entry.get("source") != expected_source:
        out.append(
            "marketplace plugin entry source MUST be "
            f"{expected_source!r}; got {entry.get('source')!r}"
        )
    return out, entry.get("description")


def _codex_manifest_violations(*, root: Path, marketplace_description: str | None) -> list[str]:
    """Validate the Codex plugin manifest (source of truth for description)."""
    manifest_path = root / "livespec" / ".codex-plugin" / "plugin.json"
    out: list[str] = []
    try:
        plugin = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [f"livespec/.codex-plugin/plugin.json unreadable/invalid: {exc}"]
    if plugin.get("name") != "livespec":
        out.append(f"plugin.json name MUST be 'livespec'; got {plugin.get('name')!r}")
    if not plugin.get("version"):
        out.append(f"plugin.json version MUST be non-empty; got {plugin.get('version')!r}")
    if plugin.get("skills") != "./skills/":
        out.append(f"plugin.json skills MUST be './skills/'; got {plugin.get('skills')!r}")
    if plugin.get("hooks") != "./hooks/hooks.json":
        out.append(f"plugin.json hooks MUST be './hooks/hooks.json'; got {plugin.get('hooks')!r}")
    if marketplace_description is not None and plugin.get("description") != marketplace_description:
        out.append(
            "marketplace plugin description MUST duplicate plugin.json's verbatim "
            "(plugin.json is the source of truth)"
        )
    return out


def _codex_skill_set_violations(*, root: Path) -> list[str]:
    skills_dir = root / "livespec" / "skills"
    out: list[str] = []
    if not skills_dir.is_dir():
        return [f"missing skills directory: {skills_dir.relative_to(root)}/"]
    found = {p.name for p in skills_dir.iterdir() if p.is_dir()}
    for missing in sorted(EXPECTED_SKILLS - found):
        out.append(f"missing skill directory: skills/{missing}/")
    for extra in sorted(found - EXPECTED_SKILLS):
        out.append(f"unexpected skill directory: skills/{extra}/")
    for name in sorted(EXPECTED_SKILLS & found):
        skill_md = skills_dir / name / "SKILL.md"
        if not skill_md.is_file():
            out.append(f"missing skills/{name}/SKILL.md")
            continue
        text = skill_md.read_text(encoding="utf-8")
        frontmatter = _frontmatter_block(text=text)
        if frontmatter is None:
            out.append(f"skills/{name}/SKILL.md MUST open with a `---`-fenced frontmatter block")
            continue
        name_match = FRONTMATTER_NAME_RE.search(frontmatter)
        if name_match is None or name_match.group(1) != name:
            got = None if name_match is None else name_match.group(1)
            out.append(f"skills/{name}/SKILL.md frontmatter name MUST be {name!r}; got {got!r}")
        desc_match = _FRONTMATTER_DESCRIPTION_RE.search(frontmatter)
        if desc_match is None or not desc_match.group(1).strip():
            out.append(f"skills/{name}/SKILL.md frontmatter description MUST be non-empty")
        if "allowed-tools" in frontmatter:
            out.append(
                f"skills/{name}/SKILL.md frontmatter MUST NOT carry an 'allowed-tools' key "
                "(Codex skills have no allowed-tools surface)"
            )
    return out


def _codex_binding_body_violations(*, skill_md: Path, root: Path) -> list[str]:
    """Validate Codex-binding body markers (resolution snippet + bans)."""
    out: list[str] = []
    text = skill_md.read_text(encoding="utf-8")
    frontmatter = _frontmatter_block(text=text)
    body = text
    if frontmatter is not None:
        # Drop the frontmatter block (the body is what follows the closing `---`).
        closing = text.find("\n---", text.find("---") + 3)
        if closing != -1:
            body = text[closing + len("\n---") :]
    where = skill_md.relative_to(root)
    if _CODEX_RESOLUTION_SNIPPET not in body:
        out.append(
            f"{where}: body MUST carry the Codex core-resolution invocation "
            f"{_CODEX_RESOLUTION_SNIPPET!r}"
        )
    if "/livespec:" in body:
        out.append(
            f"{where}: body MUST NOT use the '/livespec:' slash-command form "
            "(Codex invocation is NAME-based: 'livespec:<op>')"
        )
    if "installed_plugins.json" in body:
        out.append(
            f"{where}: body MUST NOT reference 'installed_plugins.json' "
            "(that is the Claude resolution artifact)"
        )
    if "Claude Code Driver" in body:
        out.append(f"{where}: body MUST NOT contain the phrase 'Claude Code Driver'")
    if "livespec-driver-claude" in body:
        out.append(f"{where}: body MUST NOT reference the sibling repo 'livespec-driver-claude'")
    return out


def _codex_hook_bundle_violations(*, root: Path) -> list[str]:
    hooks_json = root / "livespec" / "hooks" / "hooks.json"
    guard_script = root / "livespec" / "hooks" / "livespec_footgun_guard.py"
    out: list[str] = []
    if not guard_script.is_file():
        out.append("missing livespec/hooks/livespec_footgun_guard.py")
    try:
        hooks = json.loads(hooks_json.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        out.append(f"livespec/hooks/hooks.json unreadable/invalid: {exc}")
        return out
    if "description" in hooks:
        out.append(
            "hooks.json MUST NOT carry a top-level 'description' key "
            "(Codex's hooks parser rejects it)"
        )
    pre_tool_use = hooks.get("hooks", {}).get("PreToolUse", [])
    bash_entries = [e for e in pre_tool_use if e.get("matcher") == "Bash"]
    if not bash_entries:
        out.append("hooks.json MUST register a PreToolUse entry with matcher 'Bash'")
        return out
    guard_referenced = any(
        "livespec_footgun_guard.py" in inner.get("command", "")
        for entry in bash_entries
        for inner in entry.get("hooks", [])
    )
    if not guard_referenced:
        out.append("hooks.json PreToolUse/Bash entry MUST reference 'livespec_footgun_guard.py'")
    return out


def codex_profile_violations(*, root: Path) -> list[str]:
    skills_dir = root / "livespec" / "skills"
    violations, marketplace_description = _codex_marketplace_violations(root=root)
    violations.extend(
        _codex_manifest_violations(root=root, marketplace_description=marketplace_description)
    )
    violations.extend(_codex_skill_set_violations(root=root))
    for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
        violations.extend(_codex_binding_body_violations(skill_md=skill_md, root=root))
        violations.extend(fenced_invocation_violations(skill_md=skill_md, root=root))
    violations.extend(_codex_hook_bundle_violations(root=root))
    return violations
