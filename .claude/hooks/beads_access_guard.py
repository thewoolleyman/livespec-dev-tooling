#!/usr/bin/env python3
"""
beads-access guard — Claude Code PreToolUse hook (Bash).

Blocks a bare `bd` / `dolt` / direct-tenant `mysql` invocation unless the
command already runs under a recognized per-project credential-injection env
wrapper (`with-<id>-env.sh`). This repo's tenant password is projected from
1Password and never lives on disk, so an un-wrapped call fails with
`Error 1045 (28000): Access denied` — a signature three sessions independently
read as a store outage on 2026-08-19 and 2026-08-20. The guard turns that
silent footgun into an actionable deny that names the wrapper.

Detection is TOKEN/COMMAND-POSITION based, not substring based. `bd` and
`dolt` are short words that appear constantly as DATA — in a path, a grep
pattern, a here-doc body, a work-item id — and blocking those would make the
guard worse than the footgun. So each shell segment is tokenized, leading
env-assignments and `command`/`sudo`/`env` prefixes are skipped, here-document
BODIES are dropped, and only the resulting command-position word is inspected.

Always exits 0; fails OPEN on any parse/tokenize error (a guard bug must never
block legitimate work — the wrapper itself is the real mechanism; this guard is
only a fast early warning). It blocks ONLY on a POSITIVE match.
"""

import json
import re
import shlex
import sys

__all__: list[str] = []

_WRAPPER_RE = re.compile(r"with-[a-z0-9-]+-env\.sh")
_COMMAND_SEPARATORS = {";", "&", "&&", "|", "||", "(", ")"}
_COMMAND_SUBSTITUTION_PREFIX = "$"
_ENV_COMMAND = "env"
_COMMAND_PREFIXES = {"command", "sudo"}
_HEREDOC_OPERATORS = {"<<", "<<-"}
_TENANT_COMMANDS = {"bd", "dolt"}
# `mysql` is legitimate against plenty of servers, so it is blocked only when
# the command also names the tenant endpoint this repo's Dolt server listens on.
_TENANT_HINTS = ("3307", "127.0.0.1")
_ASSIGNMENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=.*")

_REASON = (
    "Blocked: direct beads/Dolt tenant access must run under this project's "
    "configured credential-injection env wrapper — "
    "`/usr/local/bin/with-livespec-env.sh -- <command>`. An 'Access denied' / "
    "'no beads database found' failure means you are OUTSIDE the wrapper (the "
    "bare BEADS_DOLT_PASSWORD is absent); it is NOT a store outage, a corrupt "
    "database, or a reason to diagnose the Dolt server. Never hand-hunt the "
    "secret or reach around the seam with raw mysql/dolt/sudo. "
    "(AGENTS.md section 'Beads runtime prerequisites')"
)


def _shell_tokens(*, command: str) -> list[str]:
    """Split `command` into shell-like words and control operators.

    Raises `ValueError` on an unbalanced quote; `main`'s fail-open seam turns
    that into a pass-through.
    """
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    return list(lexer)


def _heredoc_delimiters(*, line: str) -> list[str]:
    """Return here-document delimiters introduced on a command line."""
    delimiters: list[str] = []
    tokens = iter(_shell_tokens(command=line))
    for token in tokens:
        if token in _HEREDOC_OPERATORS:
            delimiters.append(next(tokens, ""))
    return delimiters


def _without_heredoc_bodies(*, command: str) -> str:
    """Return `command` with here-document body lines removed.

    A here-doc body is DATA. Leaving it in is how a guard blocks a session for
    writing the word `bd` into a file it was asked to write.
    """
    stripped_lines: list[str] = []
    pending_delimiters: list[str] = []
    for line in command.splitlines():
        if pending_delimiters:
            if line == pending_delimiters[0]:
                _ = pending_delimiters.pop(0)
            continue
        stripped_lines.append(line)
        pending_delimiters.extend(_heredoc_delimiters(line=line))
    return "\n".join(stripped_lines)


def _effective_command_index(*, tokens: list[str], start: int) -> int:
    """Skip shell prefixes that still leave a later word in command position."""
    token_index = start
    while token_index < len(tokens):
        token = tokens[token_index]
        if token in _COMMAND_SEPARATORS:
            return token_index
        if _ASSIGNMENT_RE.fullmatch(token) or token in _COMMAND_PREFIXES:
            token_index += 1
            continue
        if token == _ENV_COMMAND:
            token_index += 1
            while token_index < len(tokens) and _ASSIGNMENT_RE.fullmatch(tokens[token_index]):
                token_index += 1
            continue
        return token_index
    return token_index


def _command_position_tokens(*, command: str) -> list[str]:
    """Return the shell words that occupy command position in `command`."""
    tokens = _shell_tokens(command=_without_heredoc_bodies(command=command))
    command_position_tokens: list[str] = []
    expect_command = True
    token_index = 0
    while token_index < len(tokens):
        token = tokens[token_index]
        if token == _COMMAND_SUBSTITUTION_PREFIX:
            token_index += 1
            continue
        if token in _COMMAND_SEPARATORS:
            expect_command = True
            token_index += 1
            continue
        if not expect_command:
            token_index += 1
            continue
        token_index = _effective_command_index(tokens=tokens, start=token_index)
        if token_index >= len(tokens):
            break
        if tokens[token_index] in _COMMAND_SEPARATORS:
            continue
        command_position_tokens.append(tokens[token_index])
        expect_command = False
        token_index += 1
    return command_position_tokens


def _should_block(*, command: str) -> bool:
    """Return True iff `command` is an un-wrapped tenant-tooling invocation.

    A command already running under any recognized per-project env wrapper
    (`with-<id>-env.sh`) is never blocked. Otherwise a bare `bd` or `dolt` word
    in command position, or a `mysql` invocation aimed at the tenant endpoint,
    is blocked.
    """
    if _WRAPPER_RE.search(command):
        return False
    command_tokens = _command_position_tokens(command=command)
    if any(token in _TENANT_COMMANDS for token in command_tokens):
        return True
    return "mysql" in command_tokens and any(hint in command for hint in _TENANT_HINTS)


def _deny_payload() -> str:
    payload = {
        "decision": "block",
        "reason": _REASON,
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": _REASON,
        },
    }
    return json.dumps(payload)


def _decision(*, raw: str) -> str | None:
    """Return the deny payload for an un-wrapped tenant call, or None to allow.

    Raises `json.JSONDecodeError` on malformed hook input, and `ValueError` on
    an untokenizable command; `main`'s narrow seam catch turns both into the
    fail-open pass-through.
    """
    if not raw.strip():
        return None
    data = json.loads(raw)
    if data.get("tool_name", "") != "Bash":
        return None
    command = data.get("tool_input", {}).get("command", "")
    if not command or not _should_block(command=command):
        return None
    return _deny_payload()


def main() -> int:
    try:
        decision = _decision(raw=sys.stdin.read())
        if decision is not None:
            _ = sys.stdout.write(decision + "\n")
    except json.JSONDecodeError:
        return 0
    except Exception:  # noqa: BLE001 — sole fail-open hook boundary: silent pass-through, exit 0
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
