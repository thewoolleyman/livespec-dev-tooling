"""Claude plugin command planning and execution helpers."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

__all__: list[str] = [
    "CommandResult",
    "CommandRunner",
    "enabled_plugin_names",
    "marketplace_repo_ref",
    "planned_commands",
    "run_from_settings",
    "subprocess_runner",
]


@dataclass(frozen=True, kw_only=True)
class CommandResult:
    """Outcome of one command."""

    returncode: int


class CommandRunner(Protocol):
    """Callable seam for command execution."""

    def __call__(self, *, args: tuple[str, ...]) -> CommandResult: ...


def marketplace_repo_ref(*, entry: object) -> str | None:
    """The `<repo>@<ref>` target for one extraKnownMarketplaces entry."""
    if not isinstance(entry, dict):
        return None
    source = cast("dict[str, object]", entry).get("source")
    if not isinstance(source, dict):
        return None
    source_map = cast("dict[str, object]", source)
    repo = source_map.get("repo")
    ref = source_map.get("ref")
    if not isinstance(repo, str) or not isinstance(ref, str):
        return None
    return f"{repo}@{ref}"


def enabled_plugin_names(*, raw: object) -> tuple[str, ...] | None:
    """The enabled plugin names from settings, preserving file order."""
    if raw is None:
        return ()
    if isinstance(raw, list):
        names: list[str] = []
        for item in cast("list[object]", raw):
            if not isinstance(item, str):
                return None
            names.append(item)
        return tuple(names)
    if not isinstance(raw, dict):
        return None
    names: list[str] = []
    for key, enabled in cast("dict[str, object]", raw).items():
        if not isinstance(enabled, bool):
            return None
        if enabled:
            names.append(key)
    return tuple(names)


def planned_commands(*, settings_text: str) -> tuple[tuple[str, ...], ...]:
    """Return Claude plugin commands derived from `.claude/settings.json`."""
    parsed = json.loads(settings_text)
    if not isinstance(parsed, dict):
        return ()
    settings = cast("dict[str, object]", parsed)
    commands: list[tuple[str, ...]] = []
    marketplaces = settings.get("extraKnownMarketplaces")
    if isinstance(marketplaces, dict):
        for entry in cast("dict[str, object]", marketplaces).values():
            repo_ref = marketplace_repo_ref(entry=entry)
            if repo_ref is not None:
                commands.append(("claude", "plugin", "marketplace", "add", repo_ref))
    plugins = enabled_plugin_names(raw=settings.get("enabledPlugins"))
    if plugins is None:
        return tuple(commands)
    for plugin in plugins:
        commands.append(("claude", "plugin", "install", plugin, "-s", "project"))
        commands.append(("claude", "plugin", "update", plugin, "-s", "project"))
    return tuple(commands)


def subprocess_runner(*, args: tuple[str, ...]) -> CommandResult:
    """Run one Claude CLI command."""
    try:
        completed = subprocess.run(list(args), check=False)
    except OSError:
        return CommandResult(returncode=127)
    return CommandResult(returncode=completed.returncode)


def run_from_settings(*, settings_path: Path, runner: CommandRunner) -> int:
    """Run the Claude plugin commands derived from `settings_path`."""
    settings_text = settings_path.read_text(encoding="utf-8")
    for command in planned_commands(settings_text=settings_text):
        result = runner(args=command)
        if result.returncode != 0:
            return result.returncode
    return 0
