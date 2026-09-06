"""Claude plugin command planning and execution helpers.

⛔ THE SEAM'S TYPES ARE NAMED FOR THE PLUGIN SEAM, NOT FOR COMMANDS IN
GENERAL, and that is a mechanical requirement rather than a stylistic
preference. They were once spelled `CommandResult` / `CommandRunner` —
the SAME two names `_local_context` declares for ITS subprocess seam, in
the SAME package, carrying DIFFERENT shapes. Two types under one name in
one package do not collide loudly: a module importing one when it meant
the other gets a SILENT SHADOW, because both are legitimate names here.
Nothing mechanical convicted the collision either, so it survived months
of edits to both sides. `tests/livespec_dev_tooling/fleet/
test_type_name_collisions.py` is what sees it now
(`livespec-dev-tooling-6e83`).

⚠️ THE RENAME CLOSED THE NAME QUESTION AND NOT THE DUPLICATION ONE. This
seam and `_local_context`'s remain two runners over one operating-system
fact, and collapsing them is a separate, larger change: `_local_context`'s
`CommandResult` carries `stdout`/`stderr`, which this seam DELIBERATELY
does not capture — `claude plugin install` writes progress a human is
meant to see, so its streams are inherited rather than piped, and there is
no honest value to put in those two fields here. They do share the ONE
failure track (`InvocationNotPerformed`), which is where the drift that
made this worth filing actually was.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

__all__: list[str] = [
    "PluginCommandResult",
    "PluginCommandRunner",
    "enabled_plugin_names",
    "marketplace_repo_ref",
    "planned_commands",
    "run_from_settings",
    "subprocess_runner",
]


@dataclass(frozen=True, kw_only=True)
class PluginCommandResult:
    """Answer of one plugin CLI invocation that RAN — its exit code, alone.

    Deliberately narrower than `_local_context.CommandResult`: this seam
    inherits the child's streams rather than capturing them, so it has no
    `stdout`/`stderr` to report and does not pretend to.
    """

    returncode: int


class PluginCommandRunner(Protocol):
    """Callable seam for plugin CLI invocations; `args` includes the program."""

    def __call__(self, *, args: tuple[str, ...]) -> PluginCommandResult: ...


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


def subprocess_runner(*, args: tuple[str, ...]) -> PluginCommandResult:
    """Run one Claude CLI command."""
    try:
        completed = subprocess.run(list(args), check=False)
    except OSError:
        return PluginCommandResult(returncode=127)
    return PluginCommandResult(returncode=completed.returncode)


def run_from_settings(*, settings_path: Path, runner: PluginCommandRunner) -> int:
    """Run the Claude plugin commands derived from `settings_path`."""
    settings_text = settings_path.read_text(encoding="utf-8")
    for command in planned_commands(settings_text=settings_text):
        result = runner(args=command)
        if result.returncode != 0:
            return result.returncode
    return 0
