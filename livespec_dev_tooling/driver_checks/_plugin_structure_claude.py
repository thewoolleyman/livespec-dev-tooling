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
import sys
from pathlib import Path
from typing import cast

# `returns` is VENDORED, not installed; a bare import would resolve only
# when some earlier import in the process happened to run first.
_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.io import IOFailure, IOResult, IOSuccess  # noqa: E402  — vendor-path-aware import.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware import.

from livespec_dev_tooling.driver_checks._profile_read_failure import (  # noqa: E402
    ProfileUnreadable,
)

__all__: list[str] = [
    "EXPECTED_SKILLS",
    "FRONTMATTER_NAME_RE",
    "ProfileViolations",
    "claude_profile_violations",
    "collect_violations",
    "fenced_invocation_violations",
    "read_profile_text",
]


# The railway alias for both profiles. Declared HERE and re-declared in
# `_plugin_structure_codex` rather than imported, because the offender
# check matches an annotation's TERMINAL NAME and cannot resolve an alias
# across a module boundary — an imported alias reads as a plain container
# and the conversion is only partially credited (the pin-walker family
# paid this, 61 → 56 instead of 53).
ProfileViolations = IOResult[list[str], ProfileUnreadable]


def read_profile_text(*, path: Path, root: Path) -> IOResult[str | None, ProfileUnreadable]:
    """Read a file the profile must inspect. THREE answers, not two.

    `None` on the success track means ABSENT — definitive, reproducible,
    and the caller's to report as a violation. The failure track means
    PRESENT BUT UNREADABLE, which says nothing about the Driver.

    ⛔ The `FileNotFoundError` arm must come FIRST: it IS an `OSError`,
    so catching the parent alone would sweep absence onto the failure
    track and convert a real violation into a silent non-answer.
    """
    try:
        return IOSuccess(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return IOSuccess(None)
    except OSError as unreadable:
        return IOFailure(
            ProfileUnreadable(path=_relative(path=path, root=root), detail=str(unreadable))
        )


def _relative(*, path: Path, root: Path) -> str:
    """`path` relative to the repo root, falling back to its bare name.

    Repo-relative so a CI diagnostic never leaks an absolute host path.
    """
    try:
        return str(path.relative_to(root))
    except ValueError:
        return path.name


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


def fenced_invocation_violations(*, skill_md: Path, root: Path) -> ProfileViolations:
    """Fenced wrapper-invocation rules — byte-identical across both profiles.

    Any fenced line invoking a `bin/<name>.py` wrapper MUST use the
    `$LIVESPEC_CORE_ROOT` resolution variable, MUST NOT use `uv run`,
    MUST NOT use a literal `.claude-plugin/scripts` path, and MUST NOT
    use the Driver's own plugin-root placeholder (which would resolve to
    the Driver root, which carries no scripts/).
    """
    text = read_profile_text(path=skill_md, root=root)
    if isinstance(text, IOFailure):
        return text
    body = unsafe_perform_io(text.unwrap())
    if body is None:
        # Absent, and definitively so — the caller globbed this path.
        return IOSuccess([f"{_relative(path=skill_md, root=root)}: absent"])
    out: list[str] = []
    in_fence = False
    for line_no, raw in enumerate(body.splitlines(), start=1):
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
    return IOSuccess(out)


def _load_manifest(
    *, path: Path, root: Path
) -> IOResult[dict[str, object] | str, ProfileUnreadable]:
    """The parsed manifest, or a VIOLATION STRING for absent/malformed bytes.

    The success track carries either the payload or the one-line violation,
    because absence and malformation are both definitive properties of the
    committed tree and belong to the caller's violation list. Only a
    present-but-unreadable file leaves the success track.
    """
    text = read_profile_text(path=path, root=root)
    if isinstance(text, IOFailure):
        return text
    body = unsafe_perform_io(text.unwrap())
    name = path.name
    if body is None:
        return IOSuccess(f"{name} absent")
    try:
        parsed = cast("object", json.loads(body))
    except ValueError as invalid:
        return IOSuccess(f"{name} invalid: {invalid}")
    if not isinstance(parsed, dict):
        return IOSuccess(f"{name} MUST be a JSON object")
    return IOSuccess(cast("dict[str, object]", parsed))


def _claude_manifest_violations(*, root: Path) -> ProfileViolations:
    plugin_dir = root / ".claude-plugin"
    out: list[str] = []
    loaded = _load_manifest(path=plugin_dir / "plugin.json", root=root)
    if isinstance(loaded, IOFailure):
        return loaded
    plugin = unsafe_perform_io(loaded.unwrap())
    if isinstance(plugin, str):
        return IOSuccess([plugin])
    loaded = _load_manifest(path=plugin_dir / "marketplace.json", root=root)
    if isinstance(loaded, IOFailure):
        return loaded
    marketplace = unsafe_perform_io(loaded.unwrap())
    if isinstance(marketplace, str):
        return IOSuccess([marketplace])
    if plugin.get("name") != "livespec":
        out.append(f"plugin.json name MUST be 'livespec'; got {plugin.get('name')!r}")
    if marketplace.get("name") != "livespec-driver-claude":
        out.append(
            "marketplace.json name MUST be 'livespec-driver-claude'; "
            f"got {marketplace.get('name')!r}"
        )
    out.extend(_marketplace_entry_violations(marketplace=marketplace, plugin=plugin))
    return IOSuccess(out)


def _marketplace_entry_violations(
    *, marketplace: dict[str, object], plugin: dict[str, object]
) -> list[str]:
    """The single marketplace plugin entry's own invariants.

    Extracted to keep `_claude_manifest_violations` under the six-return and
    ten-branch caps the conversion's new failure arms pushed it past.
    """
    entries = cast("list[object]", marketplace.get("plugins", []))
    if len(entries) != 1:
        return [f"marketplace.json MUST list exactly one plugin; got {len(entries)}"]
    raw = entries[0]
    if not isinstance(raw, dict):
        return ["marketplace.json plugin entry MUST be a JSON object"]
    entry = cast("dict[str, object]", raw)
    out: list[str] = []
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


def _claude_skill_set_violations(*, root: Path) -> ProfileViolations:
    skills_dir = root / ".claude-plugin" / "skills"
    out: list[str] = []
    if not skills_dir.is_dir():
        # Fail soft (mirrors the codex profile's guard): a `.claude-plugin/`
        # tree with plugin.json but no `skills/` dir is the artifact-carrier
        # topology of livespec-core. Report it as a violation rather than
        # crashing on `iterdir()` of a missing directory.
        return IOSuccess([f"missing skills directory: {skills_dir.relative_to(root)}/"])
    found = {p.name for p in skills_dir.iterdir() if p.is_dir()}
    for missing in sorted(EXPECTED_SKILLS - found):
        out.append(f"missing skill directory: skills/{missing}/")
    for extra in sorted(found - EXPECTED_SKILLS):
        out.append(f"unexpected skill directory: skills/{extra}/")
    for name in sorted(EXPECTED_SKILLS & found):
        skill_md = skills_dir / name / "SKILL.md"
        # No `is_file()` pre-check: `read_profile_text` already distinguishes
        # absent (None) from present-but-unreadable, and a separate stat would
        # both duplicate that answer and make the failure arm unreachable by
        # construction. A DIRECTORY named SKILL.md is unreadable, not missing.
        text = read_profile_text(path=skill_md, root=root)
        if isinstance(text, IOFailure):
            return text
        body = unsafe_perform_io(text.unwrap())
        if body is None:
            out.append(f"missing skills/{name}/SKILL.md")
            continue
        match = FRONTMATTER_NAME_RE.search(body)
        if match is None or match.group(1) != name:
            got = None if match is None else match.group(1)
            out.append(f"skills/{name}/SKILL.md frontmatter name MUST be {name!r}; got {got!r}")
    return IOSuccess(out)


def collect_violations(*, parts: list[ProfileViolations]) -> ProfileViolations:
    """Flatten violation lists, short-circuiting on the FIRST unreadable part.

    Shared by both profile entry points. Short-circuit rather than collect:
    once one file could not be read, the run has not measured the bundle,
    and appending the violations it DID manage to find would render a
    partial answer as a complete one — the shape this epic removes.
    """
    out: list[str] = []
    for part in parts:
        if isinstance(part, IOFailure):
            return part
        out.extend(unsafe_perform_io(part.unwrap()))
    return IOSuccess(out)


def claude_profile_violations(*, root: Path) -> ProfileViolations:
    skills_dir = root / ".claude-plugin" / "skills"
    return collect_violations(
        parts=[
            _claude_manifest_violations(root=root),
            _claude_skill_set_violations(root=root),
            *(
                fenced_invocation_violations(skill_md=skill_md, root=root)
                for skill_md in sorted(skills_dir.glob("*/SKILL.md"))
            ),
        ]
    )
