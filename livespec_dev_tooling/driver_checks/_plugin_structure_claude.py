"""_plugin_structure_claude — CLAUDE packaging-profile invariants.

Extracted verbatim from `plugin_structure` (the CLAUDE profile preserved
verbatim from the `livespec-driver-claude` copy). This module also owns
the helpers that are BYTE-IDENTICAL and SHARED across both profiles — the
`EXPECTED_SKILLS` frozenset, the frontmatter-name regex, and the
`fenced_invocation_violations` function — so they are single-sourced here
and imported by `_plugin_structure_codex`.

CLAUDE profile invariants (preserved verbatim from the claude copy):

1. `.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json`
   parse as JSON.
2. Plugin name is `livespec`; marketplace name is
   `livespec-driver-claude`; the single marketplace plugin entry's
   `source` is the STRING `./.claude-plugin` and its `description`
   duplicates `plugin.json`'s verbatim (plugin.json is the source of
   truth).
3. All eight operations ship a SKILL.md under `.claude-plugin/skills/<op>/`
   whose frontmatter `name` matches its directory; no extra skill
   directories exist. The claude profile fails SOFT (a `missing skills
   directory` violation, not an uncaught `FileNotFoundError`) when a
   `.claude-plugin/` carries plugin.json but no `skills/` dir — the
   livespec-core artifact-carrier topology (livespec-2exa).
4. Fenced wrapper-invocation rules (shared with the codex profile).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

__all__: list[str] = [
    "EXPECTED_SKILLS",
    "FRONTMATTER_NAME_RE",
    "claude_profile_violations",
    "fenced_invocation_violations",
]


# --- shared constants (byte-identical between the two Driver originals) ---
EXPECTED_SKILLS = frozenset(
    {
        "seed",
        "propose-change",
        "critique",
        "revise",
        "doctor",
        "prune-history",
        "next",
        "help",
    }
)

_WRAPPER_INVOCATION_RE = re.compile(r"bin/[a-z_]+\.py\b")
FRONTMATTER_NAME_RE = re.compile(r"^name:\s*(\S+)\s*$", re.MULTILINE)
# Assembled from parts so this checker file itself never contains the
# literal placeholder token it bans (a plugin loader textually
# substitutes the token anywhere it appears in plugin-shipped files).
_DRIVER_ROOT_TOKEN = "CLAUDE_PLUGIN" + "_ROOT"


def fenced_invocation_violations(*, skill_md: Path, root: Path) -> list[str]:
    """Fenced wrapper-invocation rules — byte-identical across both profiles.

    Any fenced line invoking a `bin/<name>.py` wrapper MUST use the
    `$LIVESPEC_CORE_ROOT` resolution variable, MUST NOT use `uv run`,
    MUST NOT use a literal `.claude-plugin/scripts` path, and MUST NOT
    use the Driver's own plugin-root placeholder (which would resolve to
    the Driver root, which carries no scripts/).
    """
    out: list[str] = []
    in_fence = False
    for line_no, raw in enumerate(skill_md.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = raw.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence or _WRAPPER_INVOCATION_RE.search(stripped) is None:
            continue
        where = f"{skill_md.relative_to(root)}:{line_no}"
        if "uv run" in stripped:
            out.append(f"{where}: fenced wrapper invocation uses 'uv run'")
        if ".claude-plugin/scripts" in stripped:
            out.append(f"{where}: fenced wrapper invocation uses a literal .claude-plugin path")
        if _DRIVER_ROOT_TOKEN in stripped:
            out.append(
                f"{where}: fenced wrapper invocation uses the Driver's own plugin-root "
                "placeholder (resolves to the Driver root, which has no scripts/)"
            )
        if "$LIVESPEC_CORE_ROOT" not in stripped:
            out.append(f"{where}: fenced wrapper invocation MUST use $LIVESPEC_CORE_ROOT")
    return out


def _claude_manifest_violations(*, root: Path) -> list[str]:
    plugin_dir = root / ".claude-plugin"
    out: list[str] = []
    try:
        plugin = json.loads((plugin_dir / "plugin.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [f"plugin.json unreadable/invalid: {exc}"]
    try:
        marketplace = json.loads((plugin_dir / "marketplace.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [f"marketplace.json unreadable/invalid: {exc}"]
    if plugin.get("name") != "livespec":
        out.append(f"plugin.json name MUST be 'livespec'; got {plugin.get('name')!r}")
    if marketplace.get("name") != "livespec-driver-claude":
        out.append(
            "marketplace.json name MUST be 'livespec-driver-claude'; "
            f"got {marketplace.get('name')!r}"
        )
    entries = marketplace.get("plugins", [])
    if len(entries) != 1:
        out.append(f"marketplace.json MUST list exactly one plugin; got {len(entries)}")
        return out
    entry = entries[0]
    if entry.get("name") != "livespec":
        out.append(f"marketplace plugin entry name MUST be 'livespec'; got {entry.get('name')!r}")
    if entry.get("source") != "./.claude-plugin":
        out.append(
            f"marketplace plugin entry source MUST be './.claude-plugin'; "
            f"got {entry.get('source')!r}"
        )
    if entry.get("description") != plugin.get("description"):
        out.append(
            "marketplace plugin description MUST duplicate plugin.json's verbatim "
            "(plugin.json is the source of truth)"
        )
    return out


def _claude_skill_set_violations(*, root: Path) -> list[str]:
    skills_dir = root / ".claude-plugin" / "skills"
    out: list[str] = []
    if not skills_dir.is_dir():
        # Fail soft (mirrors the codex profile's guard): a `.claude-plugin/`
        # tree with plugin.json but no `skills/` dir is the artifact-carrier
        # topology of livespec-core. Report it as a violation rather than
        # crashing on `iterdir()` of a missing directory.
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
        match = FRONTMATTER_NAME_RE.search(skill_md.read_text(encoding="utf-8"))
        if match is None or match.group(1) != name:
            got = None if match is None else match.group(1)
            out.append(f"skills/{name}/SKILL.md frontmatter name MUST be {name!r}; got {got!r}")
    return out


def claude_profile_violations(*, root: Path) -> list[str]:
    skills_dir = root / ".claude-plugin" / "skills"
    violations = _claude_manifest_violations(root=root)
    violations.extend(_claude_skill_set_violations(root=root))
    for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
        violations.extend(fenced_invocation_violations(skill_md=skill_md, root=root))
    return violations
