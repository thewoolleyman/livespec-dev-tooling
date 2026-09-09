#!/usr/bin/env python3
"""PreToolUse (Bash) guard: refuse fleet-killing tmux commands.

Blocks a dispatched agent from destroying the maintainer's live tmux fleet
(the shared DEFAULT socket at /tmp/tmux-<uid>/default). Design + incident
basis: livespec repo plan/tmux-fleet-kill-prevention/research/*.md (L2-host,
work-item livespec-6dyst6). Version-carried in the vps-info repo.

Hazard class denied (with an explanatory message naming the safe alternative):
  (a) `tmux ... kill-server` NOT scoped to a non-default -L <name> / -S <path>.
      (TMUX_TMPDIR is deliberately NOT trusted to make a bare kill-server safe:
      an explicit non-default -L/-S is required. Directing the agent to `-L
      <name>` removes all env-resolution ambiguity and costs it one flag.)
  (b) A -L default / -S <fleet-socket-path> that reconstructs the fleet socket.
  (c) pkill / killall / kill targeting tmux.

Allowed (NOT blocked): scoped scratch usage, e.g. `tmux -L lc_e2e_x
kill-server`, `tmux -S /run/agent/sock kill-server`, `tmux kill-session -t x`,
and any non-destructive tmux use.

THE DESIGN RULE: scan EVERY token position for a command head, never just
position 0.

The first version of this guard peeled a closed allowlist of wrapper prefixes
(`env`, plus leading VAR=VAL assignments) and then inspected `tokens[0]`. That
shape is unfixable by extension: anything that displaces `tmux` off position 0
passes, and the set of things that can do so is open-ended — every prefix
nobody thought of is a live bypass. A 2026-07-19 adversarial probe demonstrated
23 of them against this file, including `env -i tmux kill-server` (which is
strictly MORE dangerous than the bare form, because clearing the environment
also clears any TMUX_TMPDIR the caller relied on), `command` / `exec` / `sudo`
/ `nice` / `nohup` / `stdbuf` / `timeout` / `mise exec --` prefixes, `sh -lc`,
`xargs tmux`, `eval`, subshell and brace grouping, a raw-newline separator, a
backslash line continuation, and four socket-path spellings of the fleet socket.

Scanning all positions inverts the burden. A wrapper no longer has to be KNOWN
to be defeated; it merely has to leave a recognizable `tmux` / `pkill` /
`killall` / `kill` token somewhere in the segment, which every wrapper does,
because leaving that token is what a wrapper is for.

Quoting is what keeps this from over-blocking. `echo 'tmux kill-server'` lexes
to ONE token whose value is the whole sentence, so no token's basename is
`tmux`; the same holds for a `git commit -m` message, a `grep` pattern, a
here-doc body, and a `python3 -c` string. The accepted cost is that an UNQUOTED
mention (`echo tmux kill-server`) denies — a bias toward the deny direction,
since the opposite bias is what killed the fleet.

Four further evasion routes are closed here:

  - **Grouping punctuation.** `(tmux kill-server)` and `{ tmux kill-server; }`
    fuse the paren or brace onto the adjacent token, so `(){}` is stripped from
    each token's edges before the basename test.
  - **Nested payloads.** `sh -lc '<payload>'`, `bash -ctmux' kill-server'`,
    `eval '<payload>'`, and `xargs tmux` move the hazard one level down. Each is
    unwrapped and re-classified, and exceeding the depth budget fails CLOSED —
    nothing legitimate nests five `bash -c` deep, so exhausting the budget is
    evidence of evasion rather than a reason to allow.
  - **Socket-path spellings.** `/tmp/tmux-1000//default`,
    `/tmp/tmux-1000/../tmux-1000/default`, `/tmp/./tmux-1000/./default`, and
    `/tmp/tmux-1000/default/` all name the fleet socket. `-S` values are
    normalized LEXICALLY (never `realpath`, which would touch the filesystem
    from a hook) before being judged.
  - **Scope-flag precedence.** tmux(1): "If -S is specified, the default socket
    directory is not used and any -L flag is ignored." So `-S` beats `-L` NO
    MATTER the order, and among repeats the last of a kind wins. A guard that
    stopped at the first scope flag it saw allowed
    `tmux -L scratch -S /tmp/tmux-1000/default kill-server`.

Fail-CLOSED: a `kill-server` reached through a command substitution the guard
cannot evaluate is denied, as is a hazard-shaped segment that will not tokenize
and a nesting depth past the budget. Fail-OPEN only when the command clearly
has no tmux/pkill/killall shape at all, so a parser hiccup never blocks
unrelated work.

Ported from the verified livespec driver-plugin classifier
(`livespec-driver-claude` `livespec/hooks/_tmux_hazard.py`, itself shared with
`livespec-driver-codex` `livespec/hooks/_footgun_tmux.py`) so all three guards
agree case-for-case rather than diverging into three hand-rolled classifiers.
The classification logic is a faithful port; what is local to this file is the
deny-message wording and the Claude Code hook output shape.

Self-contained by contract: the installer ships this file to ~/.claude/hooks/
to be run under bare system `python3` with no virtualenv and no third-party
packages, so every import here is standard library.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import sys

# --- classification constants ---------------------------------------------

_COMMAND_SUBSTITUTION = re.compile(r"\$\(|`")
# The fleet socket namespace: /tmp/tmux-<uid> and anything beneath it.
_DEFAULT_NAMESPACE = re.compile(r"^/tmp/tmux-\d+(?:/.*)?$")
_DEFAULT_SOCKET_NAME = "default"
_GROUPING = "(){}"
# Heredoc introducer: <<WORD / <<'WORD' / <<"WORD" / <<-WORD. The body that
# follows is stdin DATA, not executed commands, so it must be removed before
# scanning — else a command that merely MENTIONS the hazard phrase self-blocks.
_HEREDOC = re.compile(r"<<-?\s*['\"]?([A-Za-z_][A-Za-z0-9_]*)['\"]?")
_KILL_SERVER = re.compile(r"\bkill-server\b")
_LINE_CONTINUATION = re.compile(r"\\\n")
_MAX_DEPTH = 4
_PROCESS_KILLERS = frozenset({"kill", "killall", "pkill"})
_PROCESS_KILLER_WORD = re.compile(r"\b(?:pkill|killall)\b")
_SHELLS = frozenset({"bash", "sh", "zsh", "dash", "ksh"})
# `-c`, `-lc`, `-ic`, `-lic` — any clustered shell flag ending in `c`.
_SHELL_COMMAND_FLAG = re.compile(r"^-[a-zA-Z]*c$")
_TMUX_WORD = re.compile(r"\btmux\b")
_XARGS_FLAGS_WITH_ARG = (
    "-a",
    "-d",
    "-E",
    "-I",
    "-i",
    "-L",
    "-l",
    "-n",
    "-P",
    "-s",
    "--arg-file",
    "--delimiter",
    "--eof",
    "--max-args",
    "--max-chars",
    "--max-lines",
    "--max-procs",
    "--replace",
)

# Inline TMUX_TMPDIR value that resolves the socket dir back to the fleet
# namespace, and the env-clearing flags that do the same by erasing whatever
# TMUX_TMPDIR the caller had. Used ONLY to enrich the deny message, never to
# gate the block.
_ENV_ASSIGN = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$")
_FLEET_TMPDIR_RE = re.compile(r"^\s*$|^/tmp/?$")
_ENV_CLEARING_FLAGS = frozenset({"-i", "--ignore-environment"})
_HAZARD_HINT_RE = re.compile(r"kill-server|pkill|killall")

# --- deny messages ---------------------------------------------------------

_REASON_PROCESS_KILLER = (
    "BLOCKED: `pkill`/`killall` targeting tmux would kill the shared "
    "tmux server holding the maintainer's entire live fleet. Safe "
    "alternative: kill only your own session (`tmux kill-session -t "
    "<name>`) or your own scratch server (`tmux -L <name> kill-server`)."
)
_REASON_PARSE = (
    "BLOCKED: this command matched the tmux-fleet destruction guard "
    "but could not be parsed cleanly, so it is denied out of caution. "
    "If this is legitimate scoped scratch work, scope it to a private "
    "socket (`tmux -L <name> ...`) and simplify the command line."
)
_REASON_STDIN = (
    "BLOCKED: tmux-fleet guard could not process this command and "
    "denied it out of caution. Scope tmux work to a private socket "
    "(`tmux -L <name> ...`) and retry."
)


def _kill_server_reason(*, extra: str) -> str:
    return (
        "BLOCKED: `tmux kill-server` on the DEFAULT socket destroys the "
        "maintainer's entire live tmux fleet (every agent pane under "
        f"/tmp/tmux-<uid>/default){extra}. This exact command class killed "
        "the fleet twice on 2026-07-18. Safe alternative: scope to a "
        "PRIVATE scratch socket, e.g. `tmux -L my_scratch kill-server` "
        "(any -L name except `default`), or kill only your own session "
        "with `tmux kill-session -t <name>`. Never kill-server without an "
        "explicit non-default -L/-S."
    )


# --- token helpers ---------------------------------------------------------


def _basename(*, token: str) -> str:
    return token.rsplit("/", 1)[-1]


def _ungrouped(*, token: str) -> str:
    """Strip shell grouping punctuation fused onto a token's edges."""
    return token.strip(_GROUPING)


def _strip_heredoc_bodies(*, command: str) -> str:
    """Remove here-doc BODIES because they are stdin data, not executed shell."""
    lines = command.split("\n")
    out: list[str] = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        out.append(line)
        match = _HEREDOC.search(line)
        if match is None:
            i += 1
            continue
        terminator = match.group(1)
        i += 1
        while i < n and lines[i].strip() != terminator:
            i += 1
        if i < n:
            i += 1
    return "\n".join(out)


def _split_segments(*, command: str) -> list[str]:
    """Split into shell segments on unquoted `;` `&&` `||` `|` `&` and newline.

    QUOTING-AWARE by construction. A regex split cuts inside quoted strings, so
    `echo 'first; tmux kill-server'` would arrive as a segment beginning
    `tmux kill-server` — a false positive on text that is pure DATA.
    """
    found: list[str] = []
    current: list[str] = []
    quote = ""
    index = 0
    total = len(command)
    while index < total:
        char = command[index]
        if quote:
            current.append(char)
            if char == quote:
                quote = ""
            index += 1
            continue
        if char in "'\"":
            quote = char
            current.append(char)
            index += 1
            continue
        if char == "\\" and index + 1 < total:
            current.append(char)
            current.append(command[index + 1])
            index += 2
            continue
        if command[index : index + 2] in ("&&", "||"):
            found.append("".join(current))
            current = []
            index += 2
            continue
        if char in ";|&\n":
            found.append("".join(current))
            current = []
            index += 1
            continue
        current.append(char)
        index += 1
    found.append("".join(current))
    return [segment.strip() for segment in found if segment.strip()]


def _shell_payload(*, arguments: list[str]) -> str | None:
    """The inline script of a `sh -c` / `bash -lc` / `zsh -ic` invocation."""
    for index, token in enumerate(arguments):
        if _SHELL_COMMAND_FLAG.match(token):
            return arguments[index + 1] if index + 1 < len(arguments) else None
        if token.startswith("-c") and len(token) > 2:
            return token[2:]
    return None


# --- tmux scope analysis ---------------------------------------------------


def _socket_is_hazardous(*, socket: str) -> bool:
    """True when a `-S` value names the fleet socket or its namespace dir."""
    if not socket:
        return True
    if "/" not in socket:
        # A bare name resolves against the caller's cwd, which a hook cannot
        # know, so it can never be SHOWN to sit off the default namespace.
        return True
    # LEXICAL normalization only: collapses `//` and resolves `.`/`..` without
    # touching the filesystem, which a PreToolUse hook must never do.
    normalized = os.path.normpath(socket)
    if _basename(token=normalized) == _DEFAULT_SOCKET_NAME:
        return True
    return bool(_DEFAULT_NAMESPACE.match(normalized))


def _label_is_hazardous(*, label: str) -> bool:
    if not label:
        return True
    return _basename(token=os.path.normpath(label)) == _DEFAULT_SOCKET_NAME


def _flag_values(*, arguments: list[str], flag: str) -> list[str]:
    """Every value given for `flag`, in `-S x`, `-Sx`, and `-S=x` spellings."""
    values: list[str] = []
    index = 0
    total = len(arguments)
    while index < total:
        token = arguments[index]
        if token == flag:
            values.append(arguments[index + 1] if index + 1 < total else "")
            index += 2
            continue
        if token.startswith(f"{flag}="):
            values.append(token[len(flag) + 1 :])
        elif token.startswith(flag):
            values.append(token[len(flag) :])
        index += 1
    return values


def _scope_permits_kill(*, arguments: list[str]) -> bool:
    """True ONLY when the EFFECTIVE tmux scope is explicit and non-default."""
    sockets = _flag_values(arguments=arguments, flag="-S")
    if sockets:
        return not _socket_is_hazardous(socket=sockets[-1])
    labels = _flag_values(arguments=arguments, flag="-L")
    if labels:
        return not _label_is_hazardous(label=labels[-1])
    return False


def _xargs_target(*, arguments: list[str]) -> list[str]:
    """The command `xargs` would run, with xargs' own flags consumed."""
    index = 0
    total = len(arguments)
    while index < total:
        token = arguments[index]
        if token == "--":
            index += 1
            break
        if not token.startswith("-") or token == "-":
            break
        index += 2 if token in _XARGS_FLAGS_WITH_ARG else 1
    return arguments[index:]


def _targets_tmux_process(*, arguments: list[str]) -> bool:
    """True when any argument mentions tmux at all.

    Deliberately a SUBSTRING test over every token, flags included. A word-
    boundary test that skipped flag-shaped arguments allowed `pkill -f '^tmux'`,
    `pkill -ftmux`, and `pkill -f 'tmux: server'` — every one of which matches
    the live server.
    """
    return any("tmux" in argument for argument in arguments)


def _tmpdir_pierce_note(*, tokens: list[str]) -> str:
    """Message enrichment when the segment also defeats TMUX_TMPDIR scoping.

    Two shapes qualify: an inline `TMUX_TMPDIR=` assignment pointing back at the
    fleet namespace, and an `env -i` that clears the environment wholesale (so
    whatever TMUX_TMPDIR the caller had is gone). Cosmetic only — the block is
    already decided by the time this runs.
    """
    for index, token in enumerate(tokens):
        assignment = _ENV_ASSIGN.match(token)
        if assignment is not None and assignment.group(1) == "TMUX_TMPDIR":
            if _FLEET_TMPDIR_RE.match(assignment.group(2)):
                return (
                    " (TMUX_TMPDIR was reset to the default namespace, piercing "
                    "any agent-scoped socket dir)"
                )
        if _basename(token=token) == "env" and any(
            argument in _ENV_CLEARING_FLAGS for argument in tokens[index + 1 :]
        ):
            return (
                " (`env -i` clears the environment, wiping any TMUX_TMPDIR that "
                "scoped this shell to an agent-private socket dir)"
            )
    return ""


# --- the all-positions scan ------------------------------------------------


def _nested_hazard(*, command: str, arguments: list[str], depth: int) -> str | None:
    """Recurse into a payload this token hands to another interpreter."""
    if command in _SHELLS:
        payload = _shell_payload(arguments=arguments)
        if payload is not None:
            return _classify(command=payload, depth=depth + 1)
    if command == "eval" and arguments:
        return _classify(command=" ".join(arguments), depth=depth + 1)
    return None


def _direct_hazard(*, command: str, arguments: list[str], tokens: list[str]) -> str | None:
    """Is THIS token a tmux/process-killer command head reaching the hazard?"""
    if command == "xargs":
        target = _xargs_target(arguments=arguments)
        if target and _basename(token=target[0]) == "tmux":
            if not _scope_permits_kill(arguments=target[1:]):
                return _kill_server_reason(extra=_tmpdir_pierce_note(tokens=tokens))
    if command == "tmux" and "kill-server" in arguments:
        if not _scope_permits_kill(arguments=arguments):
            return _kill_server_reason(extra=_tmpdir_pierce_note(tokens=tokens))
    if command in _PROCESS_KILLERS and _targets_tmux_process(arguments=arguments):
        return _REASON_PROCESS_KILLER
    return None


def _tokens_are_hazard(*, tokens: list[str], depth: int) -> str | None:
    """Scan EVERY position for a hazardous command head."""
    for index, token in enumerate(tokens):
        command = _basename(token=token)
        arguments = tokens[index + 1 :]
        nested = _nested_hazard(command=command, arguments=arguments, depth=depth)
        if nested is not None:
            return nested
        direct = _direct_hazard(command=command, arguments=arguments, tokens=tokens)
        if direct is not None:
            return direct
    return None


def _looks_like_tmux_kill_hazard(*, seg: str) -> bool:
    return bool(
        _TMUX_WORD.search(seg) and (_KILL_SERVER.search(seg) or _PROCESS_KILLER_WORD.search(seg))
    )


def _segment_is_hazard(*, seg: str, depth: int) -> str | None:
    # A `kill-server` reached through a command substitution cannot be resolved
    # without executing it, so it fails CLOSED rather than tokenizing to a
    # harmless-looking leading word like `$(echo`.
    if _COMMAND_SUBSTITUTION.search(seg) and _KILL_SERVER.search(seg):
        return _REASON_PARSE
    try:
        tokens = shlex.split(seg, posix=True)
    except ValueError:
        return _REASON_PARSE if _looks_like_tmux_kill_hazard(seg=seg) else None
    return _tokens_are_hazard(tokens=[_ungrouped(token=token) for token in tokens], depth=depth)


def _classify(*, command: str, depth: int) -> str | None:
    """Deny reason for a whole command line, or None."""
    cleaned = _LINE_CONTINUATION.sub(" ", _strip_heredoc_bodies(command=command))
    # Fail-OPEN fast path: no hazard branch below can fire without the literal
    # string `tmux` surviving here-doc stripping, so a command that lacks it
    # cannot be a fleet hazard at any nesting depth. Checked BEFORE the depth
    # budget so a deep nest of unrelated work is never denied on depth alone.
    if "tmux" not in cleaned and "pkill" not in cleaned and "killall" not in cleaned:
        return None
    if depth > _MAX_DEPTH:
        # Out of budget with content still unexamined. Nothing legitimate nests
        # this deep, so exhaustion is evidence of evasion: fail CLOSED.
        return _REASON_PARSE
    for segment in _split_segments(command=cleaned):
        reason = _segment_is_hazard(seg=segment, depth=depth)
        if reason is not None:
            return reason
    return None


def classify(command: str) -> str | None:
    """Return a deny reason string if the command is fleet-hazardous, else None.

    Fails CLOSED: if the command mentions a destructive shape (kill-server /
    pkill / killall) but classification raises, deny with a generic reason
    rather than let a parser bug silently disable the guard."""
    try:
        return _classify(command=command, depth=0)
    except Exception:  # noqa: BLE001 — guard must never crash-to-allow
        return _REASON_PARSE if _HAZARD_HINT_RE.search(command) else None


# --- Claude Code hook boundary ---------------------------------------------


def _emit_deny(reason: str) -> None:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }
        )
    )


def main() -> int:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
        if payload.get("tool_name") != "Bash":
            return 0
        command = (payload.get("tool_input") or {}).get("command", "")
        if not isinstance(command, str) or not command:
            return 0
        reason = classify(command)
    except Exception:  # noqa: BLE001
        # Never crash-to-allow on a destructive-looking payload.
        if _HAZARD_HINT_RE.search(raw):
            _emit_deny(_REASON_STDIN)
        return 0
    if reason is not None:
        _emit_deny(reason)
    return 0


# --- self-test -------------------------------------------------------------
#
# This corpus IS the regression test for the guard: install.sh runs it and
# refuses to wire a guard that fails it, so a regression cannot reach
# ~/.claude/hooks/. It merges the original 2026-07-18 corpus with the full
# 2026-07-19 adversarial-probe corpus — the 23 demonstrated bypasses of the
# tokens[0] design, plus every allow-direction case used to prove the fix
# introduces no false positives.

_MUST_BLOCK = [
    # --- the two real 2026-07-18 kills (verbatim shape) ---
    "/usr/bin/tmux kill-server 2>/dev/null; /usr/bin/tmux new-session -d -s b2probe 'sleep 10'; /usr/bin/tmux list-sessions",
    "cd /tmp && TMUX_TMPDIR=/tmp /usr/bin/tmux kill-server 2>/dev/null; echo done",
    # --- original piercing / evasion variants ---
    "tmux -L default kill-server",
    "TMUX_TMPDIR=/tmp tmux kill-server",
    "bash -c 'tmux kill-server'",
    "env TMUX_TMPDIR=/tmp tmux kill-server",
    "tmux -S /tmp/tmux-1000/default kill-server",
    "tmux kill-server",
    "pkill tmux",
    "pkill -f tmux",
    "killall tmux",
    'sh -c "ls && tmux kill-server"',
    "tmux   kill-server",
    # DESIGN CALL: bare kill-server scoped only by a non-default TMUX_TMPDIR is
    # still denied — an explicit non-default -L/-S is required (TMUX_TMPDIR is
    # not trusted to allow a destructive op). Agent just adds `-L <name>`.
    "TMUX_TMPDIR=/run/user/1000/agent tmux kill-server",
    # --- wrapper prefixes that displace tmux off position 0 (2026-07-19) ---
    "env -i tmux kill-server",
    "command tmux kill-server",
    "exec tmux kill-server",
    "sudo tmux kill-server",
    "nice tmux kill-server",
    "nice -n 5 tmux kill-server",
    "nohup tmux kill-server",
    "stdbuf -o0 tmux kill-server",
    "timeout 5 tmux kill-server",
    "mise exec -- tmux kill-server",
    "./tmux kill-server",
    # --- indirection through another interpreter ---
    "echo kill-server | xargs tmux",
    "echo | xargs tmux kill-server",
    "sh -lc 'tmux kill-server'",
    "zsh -c 'tmux kill-server'",
    "bash -ctmux' kill-server'",
    "bash -c \"bash -c 'tmux kill-server'\"",
    "eval 'tmux kill-server'",
    "$(echo tmux) kill-server",
    # --- grouping / separators / continuations ---
    "(tmux kill-server)",
    "{ tmux kill-server; }",
    "echo hi\ntmux kill-server",
    "cd /tmp\ntmux kill-server",
    "tmux \\\n kill-server",
    "echo hi; tmux kill-server",
    "true | tmux kill-server",
    "false || tmux kill-server",
    "tmux kill-server &",
    # --- socket / label spellings that reach the fleet socket ---
    "tmux -S /tmp/tmux-1000//default kill-server",
    "tmux -S /tmp/tmux-1000/../tmux-1000/default kill-server",
    "tmux -S /tmp/./tmux-1000/./default kill-server",
    "tmux -S /tmp/tmux-1000/default/ kill-server",
    "tmux -S/tmp/tmux-1000/default kill-server",
    "tmux -S /tmp/tmux-agents-1000/default kill-server",
    "tmux -S default kill-server",
    "tmux -Ldefault kill-server",
    "tmux -L=default kill-server",
    "tmux kill-server -L default",
    # tmux(1): -S wins over -L regardless of order; last of a kind wins.
    "tmux -L scratch -S /tmp/tmux-1000/default kill-server",
    "tmux -S /tmp/tmux-1000/default -L scratch kill-server",
    # --- process killers ---
    "pkill -f '^tmux'",
    "pkill -ftmux",
    "pkill -x tmux",
    "pkill -f 'tmux -L default'",
    "pkill -f /usr/bin/tmux",
    "pkill -f 'tmux: server'",
    "killall -9 tmux",
    "kill -9 $(pgrep tmux)",
    # --- parse-hostile but hazard-shaped: must FAIL CLOSED ---
    "tmux kill-server '",
]

_MUST_ALLOW = [
    # --- scoped scratch work: the whole point of not over-blocking ---
    "tmux -L lc_e2e_x kill-server",
    "tmux -Llc_e2e_x kill-server",
    "tmux -L lc_e2e_1 kill-server",
    "tmux -Lscratch kill-server",
    "tmux -S /run/agent/scratch.sock kill-server",
    "tmux -S /tmp/scratch-x/sock kill-server",
    "tmux -S /tmp/scratch-abc/sock kill-server",
    # A scratch socket whose name merely CONTAINS "fleet" is not the fleet.
    "tmux -S /tmp/scratch/fleetwood kill-server",
    "tmux -L build_check kill-server && echo cleaned",
    "tmux -L foo kill-server",
    "tmux kill-server -L scratch99",
    "TMUX_TMPDIR=/tmp/tmux-agents-1000 tmux -L scratch kill-server",
    # --- non-destructive tmux use ---
    "tmux kill-session -t foo",
    "tmux -L scratch kill-session -t foo",
    "tmux new-session -d -s work",
    "tmux list-sessions",
    "tmux -L scratch new -d -s probe",
    # --- text that MENTIONS the hazard without invoking it ---
    'echo "tmux kill-server"',
    "echo 'tmux kill-server'",
    "echo 'first; tmux kill-server'",
    "echo 'do not run pkill -f tmux'",
    "grep -rn 'pkill tmux' .",
    "grep -r 'tmux kill-server' /data/projects",
    "git log --grep='tmux kill-server'",
    "git commit -m 'never run tmux kill-server'",
    "git commit -m 'guard blocks tmux kill-server'",
    "git commit -m 'fix the tmux launcher'",
    "python3 -c \"print('tmux kill-server')\"",
    "cat > /tmp/x <<'EOF'\ntmux kill-server\nEOF",
    "cat <<'EOF'\ntmux kill-server\nEOF",
    "git commit -F - <<'MSG'\nservices: mechanical `pkill|killall tmux` guard\nthat blocks tmux kill-server on the default socket\nMSG",
    # --- unrelated work must never be touched ---
    "echo hello && ls -la",
    "git status",
    "ls -la",
    "python3 -c 'print(1)'",
    "pkill -f myserver",
    # A benign unterminated quote is NOT hazard-shaped: fail OPEN.
    "echo 'unterminated",
]


def _selftest() -> int:
    failures = 0
    for cmd in _MUST_BLOCK:
        if classify(cmd) is None:
            print(f"FAIL (should BLOCK, allowed): {cmd!r}")
            failures += 1
    for cmd in _MUST_ALLOW:
        r = classify(cmd)
        if r is not None:
            print(f"FAIL (should ALLOW, blocked): {cmd!r}\n   -> {r[:80]}")
            failures += 1
    total = len(_MUST_BLOCK) + len(_MUST_ALLOW)
    print(
        f"\n{total - failures}/{total} cases pass "
        f"({len(_MUST_BLOCK)} block + {len(_MUST_ALLOW)} allow)."
    )
    return 1 if failures else 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        sys.exit(_selftest())
    sys.exit(main())
