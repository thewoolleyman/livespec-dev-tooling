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

THE PARSING HALF RIDES ITS OWN RAILWAY — livespec-dev-tooling-qndn,
cluster 7. The conversion above put the INVOCATION half on `IOResult`; it
left `enabled_plugin_names` answering every malformed `enabledPlugins`
value with `None`, the same word it used for nothing being wrong. That
sentinel collapsed THREE conditions, each a different edit to
`.claude/settings.json`: the value is not a collection at all, a list
entry is not a plugin name, or a mapping value is not an enable flag.
`PluginEnablementMalformed` keeps them apart and names the offending
entry or key.

⚠️ `Result`, NOT `IOResult`, and the difference is not cosmetic. The
parser reads no file and spawns nothing — it is handed an already-decoded
JSON value — so an `IOResult` would claim an effect that is not there and
would force every caller through `unsafe_perform_io` for a pure answer.
The command seam above stays `IOResult` because it really does spawn.
`checks/_ci_matrix_parse` makes the same split between its pure recipe
parsers and its file reads.
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
    "ENABLEMENT_FLAG_NOT_A_BOOLEAN",
    "ENABLEMENT_NAME_NOT_A_STRING",
    "ENABLEMENT_NOT_A_COLLECTION",
    "PluginCommandOutcome",
    "PluginCommandResult",
    "PluginCommandRunner",
    "PluginEnablementMalformed",
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


# The three distinguishable ways an `enabledPlugins` value is not an
# enablement, kept apart because each names a DIFFERENT edit to
# `.claude/settings.json`. Collapsed onto one `None` they were the same word,
# and the operator was told only that something about the key was wrong.
ENABLEMENT_NOT_A_COLLECTION = "enablement_not_a_collection"
ENABLEMENT_NAME_NOT_A_STRING = "enablement_name_not_a_string"
ENABLEMENT_FLAG_NOT_A_BOOLEAN = "enablement_flag_not_a_boolean"


@dataclass(frozen=True, kw_only=True)
class PluginEnablementMalformed:
    """The `enabledPlugins` value is not a shape an enablement can be read from.

    Deliberately NOT inhabited by "the file declares no plugins": that is
    `Success(())`, and keeping the two apart is the whole point. `kind` is a
    small closed vocabulary (the three module constants), matching
    `InvocationNotPerformed`'s spelling in this same package rather than
    inventing a second convention; `detail` names the offending ENTRY or KEY,
    which is what an operator has to go and edit.
    """

    kind: str
    detail: str

    @property
    def reason(self) -> str:
        """One human-readable line, ready to render as a settings-file finding."""
        return f"enabledPlugins {self.detail}"


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


def _malformed(*, kind: str, detail: str) -> Result[tuple[str, ...], PluginEnablementMalformed]:
    """The failure track, naming WHICH malformation the value carries."""
    return Failure(PluginEnablementMalformed(kind=kind, detail=detail))


def enabled_plugin_names(*, raw: object) -> Result[tuple[str, ...], PluginEnablementMalformed]:
    """The enabled plugin names from settings, preserving file order.

    AN ABSENT KEY IS AN ANSWER, NOT A FAILURE: a settings file that declares
    no `enabledPlugins` is well-formed and simply enables nothing, so it is
    `Success(())`. Only a value enablement cannot be READ from lands on the
    failure track. The pre-conversion spelling of the two was `()` and `None`,
    which differ by one `is None` arm a caller has to remember to write —
    and `not ()` and `not None` are both true, so forgetting it reads as
    "nothing is enabled" rather than as an error.

    The two accepted shapes are the mapping (`{name: bool}`, where `false` is
    an explicit DISABLE rather than a malformation) and the legacy list of
    names, in which every entry is enabled.
    """
    if raw is None:
        return Success(())
    if isinstance(raw, list):
        listed: list[str] = []
        for index, item in enumerate(cast("list[object]", raw)):
            if not isinstance(item, str):
                return _malformed(
                    kind=ENABLEMENT_NAME_NOT_A_STRING,
                    detail=f"list entries must be strings; entry {index} is {type(item).__name__}",
                )
            listed.append(item)
        return Success(tuple(listed))
    if not isinstance(raw, dict):
        return _malformed(
            kind=ENABLEMENT_NOT_A_COLLECTION,
            detail=f"must be a JSON object or array; got {type(raw).__name__}",
        )
    names: list[str] = []
    for key, enabled in cast("dict[str, object]", raw).items():
        if not isinstance(enabled, bool):
            return _malformed(
                kind=ENABLEMENT_FLAG_NOT_A_BOOLEAN,
                detail=f"values must be JSON booleans; {key!r} is not",
            )
        if enabled:
            names.append(key)
    return Success(tuple(names))


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
    # An unreadable enablement derives no install/update commands, and the
    # marketplace registrations this text DOES support still stand. The
    # malformation is not swallowed anywhere: `ensure` runs
    # `settings_findings` — which reports this same failure's `reason` — as a
    # precondition BEFORE it reaches the planner, so the diagnostic an
    # operator acts on is already emitted by the time control gets here.
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
    """
    settings_text = settings_path.read_text(encoding="utf-8")
    for command in planned_commands(settings_text=settings_text):
        answer = plugin_command_answer(outcome=runner(args=command))
        if isinstance(answer, InvocationNotPerformed):
            return IOFailure(answer)
        if answer.returncode != 0:
            return IOSuccess(answer.returncode)
    return IOSuccess(0)
