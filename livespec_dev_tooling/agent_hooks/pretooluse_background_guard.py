"""pretooluse_background_guard — deny `run_in_background` for gate commands.

Per work-item livespec-dev-tooling-7us.2: the premature-turn-end
failure starts when an executor backgrounds a long gate command
(`just check`, the Red-Green-Replay commit hook, `git push`, the PR
handoff) because it exceeds the default foreground Bash timeout, then
ends its turn to "wait for the notification" — fatal in a one-shot
sub-agent. A BARE backgrounded gate leaves the tool output as the only
record of the verdict, so nothing survives the turn. This Claude Code
`PreToolUse` hook (matcher `Bash`) denies any Bash call that combines
`run_in_background` with a gate command.

COMMAND-TOKEN POSITION, NOT SUBSTRING (livespec-dev-tooling-k169).
A command is a gate only where the shell would actually run one:
the recipe word a `just` invocation names, or the subcommand a
`git`/`gh` invocation names. The shapes used to be regexes over the
whole command text — `just check` meant "the word `check` anywhere
after the word `just`" — which matched ARGUMENTS as readily as
commands. A sanctioned `just gate-wait "$(cat .../run-checks.id)"`
was therefore denied for the `checks` in its run-id scratch path,
and a poll loop was denied for the words `just check` inside an
`echo` string that ran no gate at all; each denial then prescribed
the detached runner to a caller already using it, which leaves no
move but engineering AROUND the guard. Classification instead
tokenizes the command, cuts it at shell separators, skips the
transparent prefixes a command word hides behind (`mise exec --`,
`nohup`, `NAME=value`, a control word such as `until`), and reads
the command word and its subcommand from POSITION. A shell runner's
script argument (`bash -c '<text>'`) is itself command text and is
classified recursively, so quoting cannot launder a bare gate —
while an `echo` argument stays an argument, which is exactly what
makes the string case allowed.

Exception — the sanctioned detached runner. The original rationale
also claimed that "with the committed `BASH_DEFAULT_TIMEOUT_MS`
raised, gates always fit FOREGROUND". That premise was measured
false: the commit aggregate runs 593s and 1043s unloaded and exceeds
`BASH_MAX_TIMEOUT_MS=1200000` under sustained fleet load, at which
point the harness kills the tool call and NO verdict is produced at
all. `scripts/gate-run.sh` (and the `just gate-start|gate-wait|
gate-status|gate-list` recipes that delegate to it) exists for exactly
that case: it runs the gate in its own detached session and records a
durable verdict on disk, so the record does NOT live in the tool
output and its waiter is safe to background. Commands dispatched
through it are therefore allowed. The allowance is anchored at the
START of the command, so merely NAMING the runner cannot launder a
bare backgrounded gate. See `.ai/gate-runtime-vs-harness-patience.md`.

The deny hint is composed against the VENUE the hook fires in —
prescribing the detached runner only where its recipes actually
resolve, and naming the one-line install command first where they do
not (livespec-dev-tooling-h7qp). That concern, its filesystem probe
and its clause text live in the sibling `_deny_hint` module; the
rationale for the venue-awareness and for declining self-install is
recorded there.

Wire-up (consuming repo's committed `.claude/settings.json`): a
`PreToolUse` hook entry with matcher `Bash` whose command is

    mise exec -- uv run --no-sync python -m \
        livespec_dev_tooling.agent_hooks.pretooluse_background_guard

Hook protocol: hook-input JSON on stdin (`tool_name`, `tool_input`
with the Bash `command` + `run_in_background` fields). Exit `2` denies
the tool call and feeds stderr back to the agent; exit `0` allows it.
Every error path returns `0` (fail-open).

Scoping limitation (documented per the work-item): Claude Code
settings-level hooks carry no agent identity in the hook input, so
per-agent (executor-only) scoping is NOT expressible — this deny
applies session-wide, main session included. That is acceptable
because the deny fires only on the conjunction (`run_in_background`
AND a gate command); legitimate main-session background usage of
non-gate commands is untouched, and a BARE backgrounded gate has no
legitimate use in any session — the one legitimate background form,
the detached runner's waiter, is allowed explicitly above.

Output discipline: structlog JSON to stderr (the deny reason the
agent reads IS the structured event); no `print`, no
`sys.stderr.write`. The vendored `structlog` under
`livespec_dev_tooling/_vendor` is added to `sys.path` at module
import time.
"""

from __future__ import annotations

import json
import re
import shlex
import sys
from pathlib import Path
from typing import cast

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

from livespec_dev_tooling.agent_hooks._deny_hint import deny_hint  # noqa: E402

__all__: list[str] = []


# Gate-command shapes, read off the COMMAND-TOKEN POSITION: the recipe
# word a `just` invocation names (`check`, `check-types`, …), and the
# subcommand a `git`/`gh` invocation names.
_JUST_GATE_RECIPE_PREFIX = "check"
_GIT_GATE_SUBCOMMANDS: frozenset[str] = frozenset({"commit", "push"})
_GH_GATE_SUBCOMMAND = "pr"

# Shell punctuation that ENDS a command segment: the next command word
# begins after it. This is what keeps `git log && echo push` from reading
# as `git push` (the retired filler class excluded the same characters).
_SEPARATOR: re.Pattern[str] = re.compile(r"^[;&|()<>]+$")

# Fallback tokenizer for command text `shlex` cannot lex — an apostrophe
# in an unquoted word, say. It reproduces the word/separator split above;
# quotes stay glued to their word, which can only make a token FAIL to
# look like a command word, never invent a command position.
_FALLBACK_TOKENS: re.Pattern[str] = re.compile(r"[;&|()<>]+|[^\s;&|()<>]+")

# Tokens that may stand between a segment boundary and the command word:
# shell control words, the `--` an argument-forwarding wrapper puts ahead
# of the command it runs, and the launcher wrappers whose tail IS the real
# command (`mise exec -- git commit`, `nohup just check`).
_TRANSPARENT_PREFIXES: frozenset[str] = frozenset(
    {
        "!",
        "--",
        "command",
        "do",
        "elif",
        "else",
        "env",
        "exec",
        "if",
        "mise",
        "nohup",
        "setsid",
        "sudo",
        "then",
        "time",
        "until",
        "while",
    }
)

# Runners whose first non-option argument is COMMAND TEXT rather than an
# opaque argument, so `bash -c 'just check'` cannot launder a bare gate.
_SHELL_RUNNERS: frozenset[str] = frozenset({"bash", "dash", "sh", "zsh"})

# `NAME=value` — an environment prefix ahead of the command word, and
# equally a `just` argument assignment standing before the recipe word
# (`just skip="check-coverage" check`).
_ASSIGNMENT: re.Pattern[str] = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*=")

# Global options that consume the NEXT token as their value, so that token
# is not the subcommand (`git -C <path> push`).
_VALUE_OPTIONS: dict[str, frozenset[str]] = {
    "git": frozenset({"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"}),
    "gh": frozenset({"-R", "--repo"}),
    "just": frozenset({"-f", "--justfile", "-d", "--working-directory", "--chdir", "--shell"}),
}

# The sanctioned detached-gate runner. Anchored at the START of the
# command (tolerating a `mise exec --` wrapper and any path prefix) so
# the command must BE a runner invocation rather than merely mention
# one: `git commit -m 'add scripts/gate-run.sh'` stays denied.
_SANCTIONED_RUNNER: re.Pattern[str] = re.compile(
    r"^\s*(?:mise\s+exec\s+--\s+)?(?:\S*/)?"
    r"(?:gate-run\.sh|just\s+gate-(?:start|wait|status|list))\b"
)


def _configure_logger() -> structlog.stdlib.BoundLogger:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    return structlog.get_logger("pretooluse_background_guard")


def _tokenize(*, command: str) -> list[str]:
    """Split `command` into shell words, keeping separator punctuation.

    Quoting is resolved here, which is what demotes the words inside an
    `echo` string to a single argument token: they can no longer occupy a
    command position. Text `shlex` refuses degrades to the coarse
    fallback rather than raising into the hook's fail-open boundary,
    which would ALLOW the bare backgrounded gate this hook exists to deny.
    """
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    try:
        return list(lexer)
    except ValueError:
        return _FALLBACK_TOKENS.findall(command)


def _segments(*, tokens: list[str]) -> list[list[str]]:
    """Cut the token list into command segments at shell separators."""
    segments: list[list[str]] = [[]]
    for token in tokens:
        if _SEPARATOR.match(token):
            segments.append([])
        else:
            segments[-1].append(token)
    return segments


def _command_word(*, segment: list[str]) -> tuple[str, list[str]] | None:
    """Return the segment's command word and its arguments, or None.

    Transparent prefixes are skipped so the wrapper forms this guard has
    always tolerated still resolve to the command they run
    (`mise exec -- git commit` → `git`, `until gh pr checks` → `gh`), and
    the word is taken by basename so `/usr/bin/git push` is not a way out.
    """
    for index, token in enumerate(segment):
        word = token.rsplit("/", maxsplit=1)[-1]
        if word in _TRANSPARENT_PREFIXES or _ASSIGNMENT.match(token):
            continue
        return word, segment[index + 1 :]
    return None


def _subcommand(*, binary: str, args: list[str]) -> str | None:
    """Return the argument occupying `binary`'s subcommand position."""
    value_options = _VALUE_OPTIONS.get(binary, frozenset())
    skip_next = False
    for token in args:
        if skip_next:
            skip_next = False
        elif token in value_options:
            skip_next = True
        elif not token.startswith("-") and _ASSIGNMENT.match(token) is None:
            return token
    return None


def _gate_label(*, binary: str, subcommand: str | None) -> str | None:
    """Return the gate an invocation of `binary` names, or None."""
    if subcommand is None:
        return None
    if binary == "just" and subcommand.startswith(_JUST_GATE_RECIPE_PREFIX):
        return "just check"
    if binary == "git" and subcommand in _GIT_GATE_SUBCOMMANDS:
        return f"git {subcommand}"
    if binary == "gh" and subcommand == _GH_GATE_SUBCOMMAND:
        return "gh pr"
    return None


def _matched_gate(*, command: str) -> str | None:
    """Return the gate label the command INVOKES, or None.

    Every segment is classified, so a gate reached through a compound
    command (`echo start && mise exec -- git push`) is still found, while
    a gate WORD carried by an argument path or a quoted string is not —
    it never occupies a command position.
    """
    for segment in _segments(tokens=_tokenize(command=command)):
        head = _command_word(segment=segment)
        if head is None:
            continue
        binary, args = head
        subcommand = _subcommand(binary=binary, args=args)
        gate = (
            _matched_gate(command=subcommand)
            if binary in _SHELL_RUNNERS and subcommand is not None
            else _gate_label(binary=binary, subcommand=subcommand)
        )
        if gate is not None:
            return gate
    return None


def _should_deny(*, tool_name: str, tool_input: dict[str, object]) -> str | None:
    """Pure deny decision — the matched gate label, or None to allow.

    Denies iff the call is a Bash tool call, `run_in_background` is
    literally true, the command matches a gate pattern, and it is NOT
    dispatched through the sanctioned detached runner.
    """
    if tool_name != "Bash":
        return None
    if tool_input.get("run_in_background") is not True:
        return None
    command = tool_input.get("command")
    if not isinstance(command, str):
        return None
    if _SANCTIONED_RUNNER.search(command):
        return None
    return _matched_gate(command=command)


def _load_hook_input(*, raw: str) -> dict[str, object] | None:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    return cast("dict[str, object]", payload)


def _guard(*, raw_input: str, log: structlog.stdlib.BoundLogger) -> int:
    hook_input = _load_hook_input(raw=raw_input)
    if hook_input is None:
        log.warning("unparseable hook input; failing open", check_id="pretooluse-background-guard")
        return 0
    tool_name_raw = hook_input.get("tool_name")
    tool_name = tool_name_raw if isinstance(tool_name_raw, str) else ""
    tool_input_raw = hook_input.get("tool_input")
    if not isinstance(tool_input_raw, dict):
        return 0
    tool_input = cast("dict[str, object]", tool_input_raw)
    gate = _should_deny(tool_name=tool_name, tool_input=tool_input)
    if gate is None:
        return 0
    log.error(
        "DENIED: bare-backgrounding a gate command — dispatch it through the detached runner",
        check_id="pretooluse-background-guard-deny",
        gate=gate,
        command=tool_input.get("command"),
        hint=deny_hint(cwd=Path.cwd()),
    )
    return 2


def main() -> int:
    log = _configure_logger()
    try:
        return _guard(raw_input=sys.stdin.read(), log=log)
    except Exception as exc:  # noqa: BLE001 — sole fail-open hook boundary: silent pass-through, exit 0
        log.warning(
            "pretooluse_background_guard crashed; failing open",
            check_id="pretooluse-background-guard-crash",
            error=repr(exc),
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
