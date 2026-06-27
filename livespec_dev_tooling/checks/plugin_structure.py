"""plugin_structure — one canonical structural gate for a Driver plugin bundle.

This is the single reconciliation of the two formerly-divergent vendored
copies that lived in the two Driver repos: the CLAUDE packaging profile
(`livespec-driver-claude`) and the CODEX packaging profile
(`livespec-driver-codex`). Both Drivers will later import THIS module and
delete their own copies; this file is the union, not a merge that weakens
either side — each profile's invariants are preserved VERBATIM and run
mutually-exclusively under a profile auto-detect.

Profile auto-detect (anchored on `--project-root`, default `Path.cwd()`):

- `<root>/.claude-plugin/plugin.json` present → the CLAUDE profile.
- else `<root>/.agents/plugins/marketplace.json` present → the CODEX
  profile.
- else → SKIP (exit 0). dev-tooling runs this check against ITSELF (it
  has no plugin manifest), so the self-skip branch is load-bearing.

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
   directories exist.
4. Fenced wrapper-invocation rules (shared with the codex profile).

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

Shared helpers (confirmed BYTE-IDENTICAL between the two originals before
sharing): the `_EXPECTED_SKILLS` frozenset, the wrapper-invocation regex,
the frontmatter-name regex, the banned Driver-root token, and the
`_fenced_invocation_violations` function. Everything that differed
between the originals is kept per-profile.

Exit 0 when every assertion holds (or the check self-skips); exit 1 with
one structured `log.error` per violation otherwise. Output discipline:
structlog JSON to stderr (no `print`, no `sys.stderr.write`), mirroring
the sibling checks.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

__all__: list[str] = []


_CHECK_ID = "plugin_structure"
_FAIL_EXIT = 1

# --- shared constants (byte-identical between the two Driver originals) ---
_EXPECTED_SKILLS = frozenset(
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
_FRONTMATTER_NAME_RE = re.compile(r"^name:\s*(\S+)\s*$", re.MULTILINE)
# Assembled from parts so this checker file itself never contains the
# literal placeholder token it bans (a plugin loader textually
# substitutes the token anywhere it appears in plugin-shipped files).
_DRIVER_ROOT_TOKEN = "CLAUDE_PLUGIN" + "_ROOT"

# --- codex-only constants ---
# The Codex core-resolution invocation every SKILL.md body MUST carry.
_CODEX_RESOLUTION_SNIPPET = "codex plugin list --json -m livespec"
_FRONTMATTER_DESCRIPTION_RE = re.compile(r"^description:\s*(\S.*?)\s*$", re.MULTILINE)


def _fenced_invocation_violations(*, skill_md: Path, root: Path) -> list[str]:
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


# ===========================================================================
# CLAUDE profile — invariants preserved verbatim from the claude Driver copy.
# ===========================================================================


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
    found = {p.name for p in skills_dir.iterdir() if p.is_dir()}
    for missing in sorted(_EXPECTED_SKILLS - found):
        out.append(f"missing skill directory: skills/{missing}/")
    for extra in sorted(found - _EXPECTED_SKILLS):
        out.append(f"unexpected skill directory: skills/{extra}/")
    for name in sorted(_EXPECTED_SKILLS & found):
        skill_md = skills_dir / name / "SKILL.md"
        if not skill_md.is_file():
            out.append(f"missing skills/{name}/SKILL.md")
            continue
        match = _FRONTMATTER_NAME_RE.search(skill_md.read_text(encoding="utf-8"))
        if match is None or match.group(1) != name:
            got = None if match is None else match.group(1)
            out.append(f"skills/{name}/SKILL.md frontmatter name MUST be {name!r}; got {got!r}")
    return out


def claude_profile_violations(*, root: Path) -> list[str]:
    skills_dir = root / ".claude-plugin" / "skills"
    violations = _claude_manifest_violations(root=root)
    violations.extend(_claude_skill_set_violations(root=root))
    for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
        violations.extend(_fenced_invocation_violations(skill_md=skill_md, root=root))
    return violations


# ===========================================================================
# CODEX profile — invariants preserved verbatim from the codex Driver copy.
# ===========================================================================


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
    for missing in sorted(_EXPECTED_SKILLS - found):
        out.append(f"missing skill directory: skills/{missing}/")
    for extra in sorted(found - _EXPECTED_SKILLS):
        out.append(f"unexpected skill directory: skills/{extra}/")
    for name in sorted(_EXPECTED_SKILLS & found):
        skill_md = skills_dir / name / "SKILL.md"
        if not skill_md.is_file():
            out.append(f"missing skills/{name}/SKILL.md")
            continue
        text = skill_md.read_text(encoding="utf-8")
        frontmatter = _frontmatter_block(text=text)
        if frontmatter is None:
            out.append(f"skills/{name}/SKILL.md MUST open with a `---`-fenced frontmatter block")
            continue
        name_match = _FRONTMATTER_NAME_RE.search(frontmatter)
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
        violations.extend(_fenced_invocation_violations(skill_md=skill_md, root=root))
    violations.extend(_codex_hook_bundle_violations(root=root))
    return violations


# ===========================================================================
# Profile dispatch.
# ===========================================================================

_PROFILE_CLAUDE = "claude"
_PROFILE_CODEX = "codex"


def detect_profile(*, root: Path) -> str | None:
    """Auto-detect the packaging profile from the on-disk manifest topology.

    `.claude-plugin/plugin.json` → claude; else
    `.agents/plugins/marketplace.json` → codex; else None (self-skip).
    """
    if (root / ".claude-plugin" / "plugin.json").is_file():
        return _PROFILE_CLAUDE
    if (root / ".agents" / "plugins" / "marketplace.json").is_file():
        return _PROFILE_CODEX
    return None


def _configure_logger() -> structlog.stdlib.BoundLogger:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    return structlog.get_logger(_CHECK_ID)


def run_check(*, root: Path, log: structlog.stdlib.BoundLogger) -> int:
    """Detect the profile, run its invariants, emit violations; return exit code.

    Returns 0 on a clean pass or a self-skip (no plugin manifest);
    `_FAIL_EXIT` when the detected profile reports one or more violations.
    """
    profile = detect_profile(root=root)
    if profile is None:
        log.info(
            "plugin-structure: skipped (no plugin manifest)",
            check_id=_CHECK_ID,
            root=str(root),
        )
        return 0
    if profile == _PROFILE_CLAUDE:
        violations = claude_profile_violations(root=root)
    else:
        violations = codex_profile_violations(root=root)
    for violation in violations:
        log.error(
            "plugin-structure violation",
            check_id=_CHECK_ID,
            profile=profile,
            detail=violation,
        )
    return _FAIL_EXIT if violations else 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="check-plugin-structure",
        description=(
            "Profile-auto-detecting structural gate for a Driver plugin bundle "
            "(claude / codex). Skips when no plugin manifest is present."
        ),
    )
    _ = parser.add_argument(
        "--project-root",
        type=str,
        default=None,
        help=(
            "Repo root to check (defaults to the current working directory). "
            "Reserved for hermetic test fixtures; production callers omit it."
        ),
    )
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    project_root: str | None = args.project_root
    log = _configure_logger()
    root = Path(project_root).resolve() if project_root is not None else Path.cwd()
    return run_check(root=root, log=log)


if __name__ == "__main__":
    raise SystemExit(main())
