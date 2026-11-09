"""Single adoption path: no project-scope plugin adoption outside the three sanctioned paths.

In a fleet member's clone only `ensure-plugins`, `just adopt-orchestrator-build`
and `just ensure-plugins-fleet` may adopt a plugin build at project scope. This
guard reads this library's recipes, hooks, verbs and skills for any other
project-scope plugin update or install, and reads committed `.claude/settings.json`
files (this repository's and each named fleet member's) for an enabled automatic
plugin update. It is an operator-invoked probe, wired nowhere in CI.
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import cast

from livespec_dev_tooling.fleet._fleet_manifest_read import (
    ManifestUnreadable,
    manifest_names,
    master_manifest_source,
)
from livespec_dev_tooling.fleet._local_context import default_command_runner
from livespec_dev_tooling.fleet.adopt_orchestrator_build import CloneUnresolved, clones_root

__all__: list[str] = [
    "main",
    "scan_member_settings",
    "scan_tree",
    "settings_adoption_findings",
    "source_adoption_findings",
]

_PROJECT_ADOPTION = re.compile(
    r"claude\W+plugin\W+(?:update|install)\b[^\n]{0,200}?(?:-s|--scope)\W{0,5}project"
)
_SANCTIONED_SOURCES = frozenset(
    {
        "livespec_dev_tooling/fleet/_ensure_plugin_commands.py",
        "livespec_dev_tooling/fleet/adopt_orchestrator_build.py",
    }
)
_RECIPE_AND_VERB_ROOTS = (
    "justfile",
    "lefthook.yml",
    ".claude/hooks",
    "livespec_dev_tooling",
    "scripts",
    "dev-tooling",
)
_SKILL_ROOTS = (".claude/skills", ".claude/commands")
_CODE_SUFFIXES = frozenset({".py", ".sh", ".just", ".yml", ".yaml"})
_UNSCANNED_PARTS = frozenset({"_vendor", "__pycache__"})
_SETTINGS = ".claude/settings.json"
_FORCE_AUTOUPDATE = "FORCE_AUTOUPDATE_PLUGINS"
_FALSE_SPELLINGS = frozenset({"", "0", "false", "no", "off"})
_REMEDY = (
    "a project-scope plugin update or install is allowed only in ensure-plugins, "
    "just adopt-orchestrator-build and just ensure-plugins-fleet"
)


def source_adoption_findings(*, path: str, text: str) -> tuple[str, ...]:
    """A finding when one recipe, hook, verb or skill adopts a plugin at project scope."""
    if path in _SANCTIONED_SOURCES or _PROJECT_ADOPTION.search(text) is None:
        return ()
    return (f"{path}: runs a raw project-scope plugin update or install; {_REMEDY}",)


def settings_adoption_findings(*, path: str, text: str) -> tuple[str, ...]:
    """Findings for one committed settings file: raw adoption commands and automatic updates."""
    findings = list(source_adoption_findings(path=path, text=text))
    try:
        parsed: object = json.loads(text)
    except json.JSONDecodeError as unparseable:
        return (
            *findings,
            f"{path}: is not JSON, so automatic updates cannot be ruled out: {unparseable}",
        )
    settings = cast("dict[str, object]", parsed) if isinstance(parsed, dict) else {}
    marketplaces = settings.get("extraKnownMarketplaces")
    for name, entry in sorted(cast("dict[str, object]", marketplaces or {}).items()):
        if isinstance(entry, dict) and cast("dict[str, object]", entry).get("autoUpdate") is True:
            findings.append(f"{path}: marketplace {name!r} enables autoUpdate")
    env = settings.get("env")
    forced = (
        cast("dict[str, object]", env).get(_FORCE_AUTOUPDATE) if isinstance(env, dict) else None
    )
    if isinstance(forced, str) and forced.strip().lower() not in _FALSE_SPELLINGS:
        findings.append(f"{path}: env {_FORCE_AUTOUPDATE} forces automatic plugin updates")
    return tuple(findings)


def _scanned_files(*, root: Path, entry: str, suffixes: frozenset[str]) -> Iterable[Path]:
    """The files one scan root contributes, vendored and cached trees excluded."""
    target = root / entry
    if target.is_file():
        return (target,)
    return tuple(
        found
        for found in sorted(target.rglob("*"))
        if found.is_file()
        and found.suffix in suffixes
        and not _UNSCANNED_PARTS.intersection(found.relative_to(root).parts)
    )


def scan_tree(*, root: Path) -> tuple[str, ...]:
    """Findings over a checkout's recipes, hooks, verbs, skills and committed settings."""
    findings: list[str] = []
    for entries, suffixes in (
        (_RECIPE_AND_VERB_ROOTS, _CODE_SUFFIXES),
        (_SKILL_ROOTS, _CODE_SUFFIXES | {".md"}),
    ):
        for entry in entries:
            for found in _scanned_files(root=root, entry=entry, suffixes=suffixes):
                relative = found.relative_to(root).as_posix()
                text = found.read_text(encoding="utf-8", errors="replace")
                findings.extend(source_adoption_findings(path=relative, text=text))
    for settings in [path for path in (root / _SETTINGS,) if path.is_file()]:
        text = settings.read_text(encoding="utf-8")
        findings.extend(settings_adoption_findings(path=_SETTINGS, text=text))
    return tuple(sorted(findings))


def scan_member_settings(*, clones_root: Path, names: Iterable[str]) -> tuple[str, ...]:
    """Findings over each named member clone's committed settings, when the clone exists."""
    findings: list[str] = []
    for name in sorted(names):
        settings = clones_root / name / _SETTINGS
        if settings.is_file():
            findings.extend(
                settings_adoption_findings(
                    path=f"{name}/{_SETTINGS}", text=settings.read_text(encoding="utf-8")
                )
            )
    return tuple(findings)


def main() -> int:  # pragma: no cover
    """Scan this checkout, then each fleet member's clone under the clones root."""
    findings = list(scan_tree(root=Path.cwd()))
    source = master_manifest_source()
    root = clones_root(
        env_root=os.environ.get("LIVESPEC_FLEET_CLONES_ROOT"),
        cwd=Path.cwd(),
        run=default_command_runner,
    )
    if isinstance(source, ManifestUnreadable):
        _ = sys.stderr.write(f"plugin-adoption-path: members not scanned: {source.cause}\n")
        return 1
    if isinstance(root, CloneUnresolved):
        _ = sys.stderr.write(f"plugin-adoption-path: members not scanned: {root.cause}\n")
        return 1
    findings.extend(
        scan_member_settings(clones_root=root, names=manifest_names(manifest_source=source))
    )
    for finding in findings:
        _ = sys.stderr.write(f"plugin-adoption-path: {finding}\n")
    return 4 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
