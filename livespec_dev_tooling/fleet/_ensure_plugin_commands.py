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
fact, and collapsing them onto one VALUE type is a separate, larger
change: `_local_context`'s `CommandResult` carries `stdout`/`stderr`,
which this seam DELIBERATELY does not capture — `claude plugin install`
writes progress a human is meant to see, so its streams are inherited
rather than piped, and there is no honest value to put in those two
fields here. What the two DO share is the one FAILURE track
(`InvocationNotPerformed`), which is where the drift that made this
worth filing actually was, and which they now share in fact rather than
in intent.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

# `returns` is VENDORED, not installed, so a bare import resolves only if
# some EARLIER import in the same process already put `_vendor/` on
# `sys.path`. Nothing runs before this module in the `python -m
# livespec_dev_tooling.fleet.ensure_plugins` entry point that imports it,
# so it establishes the path itself exactly as `_local_context` does.
_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.io import IOFailure, IOResult, IOSuccess  # noqa: E402  — vendor-path-aware import.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware import.

from livespec_dev_tooling.fleet._invocation_failure import (  # noqa: E402
    BINARY_ABSENT,
    SPAWN_FAILED,
    InvocationNotPerformed,
)

__all__: list[str] = [
    "PluginCommandOutcome",
    "PluginCommandResult",
    "PluginCommandRunner",
    "enabled_plugin_names",
    "marketplace_repo_ref",
    "planned_commands",
    "plugin_command_answer",
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


# The railway alias for this seam, reading as `_local_context`'s
# `CommandOutcome` does: a plugin command that RAN is a SUCCESS carrying
# its exit code as data, however that code reads.
PluginCommandOutcome = IOResult[PluginCommandResult, InvocationNotPerformed]


class PluginCommandRunner(Protocol):
    """Callable seam for plugin CLI invocations; `args` includes the program.

    The failure track carries ONLY "the invocation did not happen". A
    program that RAN is a success carrying its exit code as data — the
    seam does not adjudicate what the plugin CLI said.
    """

    def __call__(self, *, args: tuple[str, ...]) -> PluginCommandOutcome: ...


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


def subprocess_runner(*, args: tuple[str, ...]) -> PluginCommandOutcome:
    """Run one Claude CLI command; a program that never ran FAILS.

    This used to answer an absent `claude` with
    `PluginCommandResult(returncode=127)` — a fabricated code a real
    program can also return, so "never ran" and "ran and exited 127" were
    the same value, and `_run_commands` reported the sentinel to the
    operator as the plugin CLI's own refusal.
    """
    if shutil.which(args[0]) is None:
        return IOFailure(
            InvocationNotPerformed(argv=args, kind=BINARY_ABSENT, detail=f"{args[0]} not on PATH")
        )
    try:
        completed = subprocess.run(list(args), check=False)
    except OSError as unspawnable:
        return IOFailure(
            InvocationNotPerformed(argv=args, kind=SPAWN_FAILED, detail=str(unspawnable))
        )
    return IOSuccess(PluginCommandResult(returncode=completed.returncode))


def plugin_command_answer(
    *, outcome: PluginCommandOutcome
) -> PluginCommandResult | InvocationNotPerformed:
    """The answer of a plugin command that RAN, or the record of one that did not.

    Both consumers of this seam need exactly this split and neither needs
    it differently, so it lives here once rather than as inline
    `isinstance` + `unsafe_perform_io` pairs at each call site —
    `_local_context.command_answer` is the precedent it is shaped after.
    """
    if isinstance(outcome, IOFailure):
        return unsafe_perform_io(outcome.failure())
    return unsafe_perform_io(outcome.unwrap())


def run_from_settings(
    *, settings_path: Path, runner: PluginCommandRunner
) -> IOResult[int, InvocationNotPerformed]:
    """Exit code of the first plugin command that refused, or `0` if none did.

    An invocation that never HAPPENED has no exit code to report, so it
    travels the failure track rather than being flattened into a
    fabricated one — the whole point of the seam's conversion. A command
    that RAN and exited non-zero stays an ANSWER on the success track.
    """
    settings_text = settings_path.read_text(encoding="utf-8")
    for command in planned_commands(settings_text=settings_text):
        answer = plugin_command_answer(outcome=runner(args=command))
        if isinstance(answer, InvocationNotPerformed):
            return IOFailure(answer)
        if answer.returncode != 0:
            return IOSuccess(answer.returncode)
    return IOSuccess(0)
