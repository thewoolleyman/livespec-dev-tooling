"""_cli_e2e_discovery — structural skill discovery + per-skill fixtures loader.

Extracted verbatim from `cli_e2e` (two of the harness contract's five
components). Both walk the on-disk tree as the source of truth — there is
no parallel manifest file:

- **Structural skill discovery** (`discover_skills`) — walks
  `<installed-plugin>/skills/*/SKILL.md` in each plugin's installed
  location and reads the slash-command prefix from `plugin.json`'s `name`
  field (contract requirement 3).
- **Per-skill fixtures loader** (`discover_fixtures`) — a fixtures
  directory `<consumer-repo>/tests/e2e-cli/fixtures/<skill>/` holds a
  `prompt.md` and an optional `expected_files.txt` per skill; directory
  present (with a `prompt.md`) == fixture exists (contract requirement 4).

`cli_e2e` re-exports `FixturedSkill`, `discover_skills`, and
`discover_fixtures` so the public surface is unchanged.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast

__all__: list[str] = [
    "FixturedSkill",
    "discover_fixtures",
    "discover_skills",
]


_PLUGIN_MANIFEST = "plugin.json"
_SKILLS_DIRNAME = "skills"
_SKILL_FILENAME = "SKILL.md"

_PROMPT_FILENAME = "prompt.md"
_EXPECTED_FILES_FILENAME = "expected_files.txt"


@dataclass(frozen=True, kw_only=True)
class FixturedSkill:
    """One discovered fixture directory — `prompt.md` + `expected_files.txt`."""

    skill: str
    prompt: str
    expected_files: tuple[str, ...]


def _read_plugin_prefix(*, plugin_dir: Path) -> str | None:
    """Read the slash-command prefix from `<plugin_dir>/plugin.json` `name`.

    Returns the `name` field verbatim (the slash prefix, e.g. `livespec`), or
    `None` when the manifest is absent or carries no usable `name`. There MUST
    be no parallel manifest file — `plugin.json` is the canonical source of the
    prefix (contract requirement 3).
    """
    manifest = plugin_dir / _PLUGIN_MANIFEST
    if not manifest.is_file():
        return None
    text = manifest.read_text(encoding="utf-8")
    try:
        parsed = json.loads(text)
    except (ValueError, json.JSONDecodeError):
        return None
    if not isinstance(parsed, dict):
        return None
    # The `cast` is the single typed parse boundary: `json.loads` yields `Any`;
    # casting to `dict[str, object]` (under the `isinstance` guard above) types
    # `.get("name")` so the result narrows from `object` via the `isinstance`
    # guard below — the same typed-boundary pattern as `pin_autodiscovery`.
    manifest_dict = cast("dict[str, object]", parsed)
    name = manifest_dict.get("name")
    return name if isinstance(name, str) and name else None


def _walk_skill_dirs(*, plugin_dir: Path) -> list[str]:
    """Return the skill names under `<plugin_dir>/skills/*/SKILL.md`, sorted.

    A skill is a subdirectory of `skills/` containing a `SKILL.md`; the skill
    name is the subdirectory name (matching the slash sub-command). Walking
    the directory layout — not a manifest — is the contract's source of truth.
    """
    skills_dir = plugin_dir / _SKILLS_DIRNAME
    if not skills_dir.is_dir():
        return []
    names: list[str] = []
    for child in sorted(skills_dir.iterdir()):
        if child.is_dir() and (child / _SKILL_FILENAME).is_file():
            names.append(child.name)
    return names


def discover_skills(*, plugin_install_dirs: tuple[Path, ...]) -> dict[str, tuple[str, ...]]:
    """Walk each installed plugin and map its slash prefix → discovered skills.

    For each directory in `plugin_install_dirs`, reads the slash-command prefix
    from `plugin.json` `name` and enumerates `skills/*/SKILL.md`. A directory
    whose manifest is missing/unreadable, or whose `skills/` dir is absent, is
    skipped. The returned mapping is keyed by slash prefix so a caller can pair
    the fixed spec-side plugin with the parametrized impl-side plugin.
    """
    out: dict[str, tuple[str, ...]] = {}
    for plugin_dir in plugin_install_dirs:
        prefix = _read_plugin_prefix(plugin_dir=plugin_dir)
        if prefix is None:
            continue
        skills = _walk_skill_dirs(plugin_dir=plugin_dir)
        out[prefix] = tuple(skills)
    return out


def _parse_expected_files(*, text: str) -> tuple[str, ...]:
    """Parse `expected_files.txt` — one path per line, blanks/`#` comments out."""
    out: list[str] = []
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        out.append(stripped)
    return tuple(out)


def discover_fixtures(*, fixtures_root: Path) -> dict[str, FixturedSkill]:
    """Walk `<fixtures_root>/<skill>/` and load each `prompt.md` fixture.

    Directory present (with a `prompt.md`) == fixture exists (contract
    requirement 4). The optional `expected_files.txt` enumerates paths that
    MUST exist after the skill's turn; an absent file means no file assertions.
    Returns a mapping of skill name → its loaded fixture.
    """
    if not fixtures_root.is_dir():
        return {}
    out: dict[str, FixturedSkill] = {}
    for child in sorted(fixtures_root.iterdir()):
        if not child.is_dir():
            continue
        prompt_path = child / _PROMPT_FILENAME
        if not prompt_path.is_file():
            continue
        expected_path = child / _EXPECTED_FILES_FILENAME
        expected = (
            _parse_expected_files(text=expected_path.read_text(encoding="utf-8"))
            if expected_path.is_file()
            else ()
        )
        out[child.name] = FixturedSkill(
            skill=child.name,
            prompt=prompt_path.read_text(encoding="utf-8"),
            expected_files=expected,
        )
    return out
