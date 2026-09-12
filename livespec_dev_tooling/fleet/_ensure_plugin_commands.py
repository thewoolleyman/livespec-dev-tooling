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

EVERY PUBLIC ANSWER HERE RIDES A RAILWAY — livespec-dev-tooling-qndn, the
fleet-wide ROP conversion. The command seam was converted first
(`livespec-dev-tooling-6e83`); `enabled_plugin_names` followed, for the
same reason in a different spelling. It answered `tuple[str, ...] | None`,
and `None` carried THREE unrelated authoring mistakes in the operator's
committed `.claude/settings.json` while `()` carried the legitimate "this
file enables nothing" — four facts, two spellings, and the two that a
caller must tell apart were the ones sharing a shape. Its parse performs
no I/O, so it rides `Result` rather than `IOResult`: the seam beneath it
runs subprocesses and is honestly `IOResult`, and claiming an effect this
one does not have would blur that distinction rather than sharpen it.
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
from returns.result import Failure, Result, Success  # noqa: E402  — vendor-path-aware import.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware import.

from livespec_dev_tooling.fleet._invocation_failure import (  # noqa: E402
    BINARY_ABSENT,
    SPAWN_FAILED,
    InvocationNotPerformed,
)

__all__: list[str] = [
    "ENABLEMENT_ENTRY_NOT_A_STRING",
    "ENABLEMENT_NOT_A_LIST_OR_MAPPING",
    "ENABLEMENT_VALUE_NOT_A_BOOLEAN",
    "EnablementOutcome",
    "EnablementUnreadable",
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


# The three distinguishable ways an `enabledPlugins` value refuses to yield a
# name list. They stay apart because they name different authoring mistakes in
# the operator's own committed `.claude/settings.json`, and the repair for each
# is a different edit: the value is the wrong KIND of JSON, a legacy list
# carries something that is not a plugin name, or a mapping carries something
# that is not an enablement flag.
ENABLEMENT_NOT_A_LIST_OR_MAPPING = "enablement-not-a-list-or-mapping"
ENABLEMENT_ENTRY_NOT_A_STRING = "enablement-entry-not-a-string"
ENABLEMENT_VALUE_NOT_A_BOOLEAN = "enablement-value-not-a-boolean"


@dataclass(frozen=True, kw_only=True)
class EnablementUnreadable:
    """The `enabledPlugins` value could not be read as a name list, and why.

    Deliberately NOT inhabited by "nothing is enabled": a settings file with no
    `enabledPlugins` key, an empty list, or an all-false mapping is a file that
    ANSWERED and enables no plugin, which is `Success(())`. Collapsing the two
    is exactly what the pre-conversion `tuple[str, ...] | None` did, and the
    consequence was not academic — the empty tuple and the sentinel both reach
    `planned_commands` as "derive no plugin commands", so a settings file
    nobody could parse provisioned as quietly as one that enables nothing.
    """

    reason: str
    detail: str

    @property
    def finding(self) -> str:
        """The operator-facing line naming which `enabledPlugins` shape refused."""
        return f"enabledPlugins could not be read ({self.reason}: {self.detail})"


# The railway alias for the enablement parse. It is a `Result` rather than an
# `IOResult` because this seam performs no I/O at all: it is handed the already
# decoded settings value and answers from that alone, so lifting it into `IO`
# would claim an effect it does not have.
EnablementOutcome = Result[tuple[str, ...], EnablementUnreadable]


def _unreadable_enablement(*, reason: str, detail: str) -> EnablementOutcome:
    """The failure track, naming which `enabledPlugins` shape could not be read."""
    return Failure(EnablementUnreadable(reason=reason, detail=detail))


def _names_from_list(*, entries: list[object]) -> EnablementOutcome:
    """Names from the legacy list spelling, in which every entry is enabled."""
    names: list[str] = []
    for index, item in enumerate(entries):
        if not isinstance(item, str):
            return _unreadable_enablement(
                reason=ENABLEMENT_ENTRY_NOT_A_STRING,
                detail=f"entry {index} is a {type(item).__name__}",
            )
        names.append(item)
    return Success(tuple(names))


def _names_from_mapping(*, entries: dict[str, object]) -> EnablementOutcome:
    """Names the mapping spelling marks `true`; a `false` value is an explicit disable."""
    names: list[str] = []
    for key, enabled in entries.items():
        if not isinstance(enabled, bool):
            return _unreadable_enablement(
                reason=ENABLEMENT_VALUE_NOT_A_BOOLEAN,
                detail=f"{key!r} is a {type(enabled).__name__}",
            )
        if enabled:
            names.append(key)
    return Success(tuple(names))


def enabled_plugin_names(*, raw: object) -> Result[tuple[str, ...], EnablementUnreadable]:
    """The enabled plugin names from settings, preserving file order.

    LEGITIMATE ABSENCE IS A SUCCESS, NOT A FAILURE. An absent `enabledPlugins`
    key is a settings file that enables nothing, and it answers `Success(())`
    exactly as an empty list or an all-false mapping does. Only a value whose
    SHAPE nobody can read travels the failure track, carrying which of the
    three shapes it was — the fact the sentinel this replaced could not carry.

    ⚠️ The return spells `Result[...]` out rather than using the
    `EnablementOutcome` alias, because `checks/public_api_result_typed` reads
    the terminal name off the SOURCE annotation via `ast` and an alias reads to
    it as a bare name. The alias is for the private helpers above, which that
    check does not judge.
    """
    if raw is None:
        return Success(())
    if isinstance(raw, list):
        return _names_from_list(entries=cast("list[object]", raw))
    if not isinstance(raw, dict):
        return _unreadable_enablement(
            reason=ENABLEMENT_NOT_A_LIST_OR_MAPPING,
            detail=f"the value is a {type(raw).__name__}",
        )
    return _names_from_mapping(entries=cast("dict[str, object]", raw))


def planned_commands(*, settings_text: str) -> tuple[tuple[str, ...], ...]:
    """Return Claude plugin commands derived from `.claude/settings.json`.

    An unreadable enablement value contributes NO plugin command, which is the
    pre-railway behaviour preserved deliberately rather than by omission: the
    shipped path reaches here only through `ensure`, which gates on
    `settings_findings` first and so REPORTS the unreadable shape to the
    operator before any command is planned. Planning an install from a value
    nobody could read is the one thing this arm must not do.
    """
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
    if isinstance(plugins, Failure):
        return tuple(commands)
    for plugin in plugins.unwrap():
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

    THE REFUSAL IS REPORTED WITHOUT SUPPRESSING THE COMMANDS BEHIND IT. Every
    `marketplace add` this module plans precedes every `install`, and
    `marketplace add` reaches GitHub over the network, so returning at the first
    non-zero exit meant one rate limit or transient fault provisioned nothing at
    all (`livespec-dev-tooling-357j2y`). The answer is unchanged in meaning —
    the FIRST refusal's exit code, so the caller's exit status still names a
    command that genuinely refused — while the cycle behind it now runs.
    """
    settings_text = settings_path.read_text(encoding="utf-8")
    first_refusal = 0
    for command in planned_commands(settings_text=settings_text):
        answer = plugin_command_answer(outcome=runner(args=command))
        if isinstance(answer, InvocationNotPerformed):
            return IOFailure(answer)
        if first_refusal == 0 and answer.returncode != 0:
            first_refusal = answer.returncode
    return IOSuccess(first_refusal)
