#!/usr/bin/env python3
"""PreToolUse (Bash) guard: message another agent session with SendMessage,
never by typing into its terminal pane.

WHY. Typing text into a pane that hosts an agent session (`herdr pane
send-text`, `herdr pane run`, `herdr agent prompt`, `tmux send-keys <text>`)
lands in the same input line the maintainer is typing into, and interrupts
their direct interaction with that session. Claude Code's built-in
`SendMessage` delivers to the session's inbox instead -- across machines too,
through Remote Control, which the same managed-settings drop-in that wires
this hook turns on for every interactive session. Prose guidance does not
reach every session; a hook does. See livespec-dev-tooling
`.ai/distributed-sendmessage-protocol.md` and plan `distributed-sendmessage`.

DENIED (with a message naming SendMessage and ListAgents):
  - `herdr [--machine X|--remote X|--session X] pane send-text|run <pane> ...`
    when herdr reports a Claude agent in that pane -- a session SendMessage
    can reach. The lookup is
    `herdr [same globals] pane get <pane>`; when it cannot be made (herdr
    unreachable, unparseable answer, a pane id that is a shell expansion) the
    guard fails CLOSED.
  - `herdr ... agent prompt ...` -- unless its target is a non-Claude agent.
  - `tmux ... send-keys|send ...` carrying literal text: `-l`, or any key
    argument that is not a tmux key name. tmux is a retired transport here.

ALLOWED:
  - `herdr ... pane send-keys` / `agent send-keys` and key-name-only
    `tmux send-keys` (Escape, Enter, C-c, arrows, a single character): picker
    and dialog unblocking, which SendMessage cannot do.
  - send-text / run into the caller's OWN pane ($HERDR_PANE_ID, local herdr).
  - send-text / run into a pane with no agent (a fresh shell pane, e.g. to
    start a new session), and `herdr agent start`.
  - send-text / run / prompt into a NON-Claude agent (codex, pi, ...): those
    harnesses cannot receive SendMessage, so their pane is the only channel.
  - Everything that reads (`pane read`, `wait-output`, `agent read`).

Scope: a guardrail against the habit, not a sandbox. Raw `herdr api` socket
calls are out of scope. Every token position is scanned for a `herdr` / `tmux`
command head (the lesson of tmux-fleet-guard.py: wrappers such as `env`,
`sudo`, `timeout`, `sh -c` displace the head from position 0), and `sh -c` /
`bash -c` / `eval` payloads are re-classified one level down.

`--selftest` runs the regression corpus with an injected pane lookup and
exits non-zero on any mismatch; installers refuse to wire a failing guard.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys

PROTOCOL_URL = (
    "https://github.com/thewoolleyman/livespec-dev-tooling/blob/master/"
    ".ai/distributed-sendmessage-protocol.md"
)

_HERDR_GLOBALS_WITH_VALUE = {"--machine", "--remote", "--session"}
_SHELLS = {"sh", "bash", "zsh", "dash"}
_TMUX_SEND = {"send-keys", "send"}
_TMUX_FLAGS_WITH_VALUE = {"-t", "-N", "-c", "-F"}
_TMUX_KEY = re.compile(
    r"^(?:Enter|Escape|Esc|Tab|BTab|BSpace|Space|Up|Down|Left|Right|Home|End|"
    r"PageUp|PageDown|PgUp|PgDn|PPage|NPage|DC|IC|KP\w+|F\d{1,2}|"
    r"(?:[CMS]-)+\S+|\S)$"
)
_MAX_DEPTH = 4


def _deny_reason(what: str) -> str:
    return (
        f"BLOCKED: {what}. Typing into another agent session's pane interrupts "
        "the maintainer's direct interaction with it. Message the session with "
        "the SendMessage tool instead: run ListAgents to find its name (sessions "
        "on other machines appear labelled 'Remote Control'), then SendMessage "
        "to that name. Key-only input (pane send-keys: Escape, Enter, arrows) to "
        "unblock a picker is still allowed. Protocol: " + PROTOCOL_URL
    )


def _basename(token: str) -> str:
    return os.path.basename(token.strip("(){}"))


def _token_segments(command: str) -> list[list[str]]:
    """Quote-aware split into simple commands. Raises ValueError on bad quoting."""
    lexer = shlex.shlex(command.replace("\n", " ; "), posix=True, punctuation_chars=";&|()")
    lexer.whitespace_split = True
    segments: list[list[str]] = [[]]
    for tok in lexer:
        if tok and set(tok) <= set(";&|()"):
            segments.append([])
        else:
            segments[-1].append(tok)
    return [seg for seg in segments if seg]


def _lookup_agent(globals_: list[str], pane: str) -> str | None:
    """Return the agent name herdr reports in `pane`, '' when none.

    Raises LookupError when the answer cannot be obtained.
    """
    herdr = os.environ.get("HERDR_BIN_PATH") or "herdr"
    try:
        proc = subprocess.run(
            [herdr, *globals_, "pane", "get", pane],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
        data = json.loads(proc.stdout)
        return str(data["result"]["pane"].get("agent") or "")
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError) as exc:
        raise LookupError(str(exc)) from exc


def _classify_herdr(args: list[str], lookup) -> str | None:
    globals_: list[str] = []
    i = 0
    while i < len(args) and args[i].startswith("-"):
        flag = args[i]
        if "=" in flag:
            globals_.append(flag)
            i += 1
        elif flag in _HERDR_GLOBALS_WITH_VALUE and i + 1 < len(args):
            globals_.extend([flag, args[i + 1]])
            i += 2
        else:
            globals_.append(flag)
            i += 1
    rest = args[i:]
    if len(rest) < 2:
        return None
    group, verb = rest[0], rest[1]
    is_prompt = group == "agent" and verb == "prompt"
    if not is_prompt and (group != "pane" or verb not in {"send-text", "run"}):
        return None
    positionals = [a for a in rest[2:] if not a.startswith("-")]
    if not positionals:
        return None
    pane = positionals[0]
    remote = any(g.split("=")[0] in _HERDR_GLOBALS_WITH_VALUE for g in globals_)
    if not remote and pane == os.environ.get("HERDR_PANE_ID", "\0"):
        return None
    if "$" in pane or "`" in pane:
        return _deny_reason(
            f"`herdr {group} {verb}` into a pane id the guard cannot evaluate ({pane})"
        )
    try:
        agent = lookup(globals_, pane)
    except LookupError:
        return _deny_reason(
            f"`herdr {group} {verb}` into pane {pane}, whose occupant could not be "
            "checked (failing closed)"
        )
    if "claude" in agent.lower():
        return _deny_reason(
            f"`herdr {group} {verb}` would type into pane {pane}, which hosts a {agent} session"
        )
    return None


def _classify_tmux(args: list[str]) -> str | None:
    idx = next((n for n, a in enumerate(args) if a in _TMUX_SEND), None)
    if idx is None:
        return None
    keys: list[str] = []
    i = idx + 1
    while i < len(args):
        a = args[i]
        if a == "-l" or (a.startswith("-") and "l" in a[1:] and a[1:].isalpha()):
            return _deny_reason("`tmux send-keys -l` types literal text into a pane")
        if a in _TMUX_FLAGS_WITH_VALUE:
            i += 2
            continue
        if a.startswith("-") and len(a) > 1:
            i += 1
            continue
        keys.append(a)
        i += 1
    for key in keys:
        if not _TMUX_KEY.match(key):
            return _deny_reason(f"`tmux send-keys` types literal text ({key!r}) into a pane")
    return None


def classify(command: str, lookup=_lookup_agent, depth: int = 0) -> str | None:
    """Return a deny reason, or None to allow."""
    if depth > _MAX_DEPTH:
        return _deny_reason("a command nested too deeply to inspect")
    if not re.search(r"herdr|tmux", command):
        return None
    try:
        segments = _token_segments(command)
    except ValueError:
        if re.search(r"send-text|send-keys|\bsend\b|\brun\b|prompt", command):
            return _deny_reason("a pane-input-shaped command that does not tokenize")
        return None
    for tokens in segments:
        for n, tok in enumerate(tokens):
            base = _basename(tok)
            rest = tokens[n + 1 :]
            if base in _SHELLS and rest:
                for m, arg in enumerate(rest):
                    if arg.startswith("-") and "c" in arg[1:] and m + 1 < len(rest):
                        verdict = classify(rest[m + 1], lookup, depth + 1)
                        if verdict:
                            return verdict
                        break
            elif base == "eval" and rest:
                verdict = classify(" ".join(rest), lookup, depth + 1)
                if verdict:
                    return verdict
            elif base == "herdr":
                verdict = _classify_herdr(rest, lookup)
                if verdict:
                    return verdict
                break
            elif base == "tmux":
                verdict = _classify_tmux(rest)
                if verdict:
                    return verdict
                break
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    if payload.get("tool_name") not in (None, "Bash"):
        return 0
    command = (payload.get("tool_input") or {}).get("command") or ""
    reason = classify(command)
    if reason:
        sys.stdout.write(
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
    return 0


# (command, expected_blocked). The fake lookup: panes "w1:p1" and "m:p9" host
# claude, "w1:p3" hosts codex, "w1:p2" is a shell, "w9:p9" cannot be looked up; own pane is "w1:p5".
_CORPUS: list[tuple[str, bool]] = [
    ("herdr pane send-text w1:p1 'hello there'", True),
    ("herdr pane run w1:p1 'please rebase'", True),
    ("herdr --machine gamingpc pane send-text m:p9 hi", True),
    ("herdr --session main pane run w1:p1 ls", True),
    ("herdr agent prompt w1:p1 'do the thing'", True),
    ("herdr agent prompt w1:p3 'do the thing'", False),
    ("herdr pane send-text w1:p3 'codex seat: proceed'", False),
    ("herdr --machine m pane run w1:p3 go", False),
    ("env FOO=1 herdr pane send-text w1:p1 hi", True),
    ("sudo -u ubuntu herdr pane run w1:p1 hi", True),
    ("timeout 5 /home/ubuntu/.local/bin/herdr pane send-text w1:p1 hi", True),
    ("bash -lc 'herdr pane send-text w1:p1 hi'", True),
    ("sh -c \"herdr pane run w1:p1 'x y'\"", True),
    ("eval herdr pane send-text w1:p1 hi", True),
    ("echo ok && herdr pane send-text w1:p1 hi", True),
    ("(herdr pane send-text w1:p1 hi)", True),
    ("herdr pane send-text w9:p9 hi", True),
    ('herdr pane send-text "$PANE" hi', True),
    ("tmux send-keys -t seat 'git status' Enter", True),
    ("tmux send-keys -l -t seat hello", True),
    ("tmux -L x send -t seat hello Enter", True),
    ("herdr pane send-keys w1:p1 esc", False),
    ("herdr agent send-keys w1:p1 enter", False),
    ("herdr pane send-text w1:p2 'claude --name worker'", False),
    ("herdr pane run w1:p2 'cd ~/workspace && claude'", False),
    ("herdr pane send-text w1:p5 hi", False),
    ("herdr pane read w1:p1", False),
    ("herdr pane list", False),
    ("herdr agent start w1:p2", False),
    ("herdr pane wait-output w1:p1 --match done", False),
    ("tmux send-keys -t seat Escape", False),
    ("tmux send-keys -t seat C-c Enter", False),
    ("tmux send-keys -t seat 1", False),
    ("tmux list-panes", False),
    ("echo 'herdr pane send-text w1:p1 hi'", False),
    ("git commit -m 'stop using herdr pane send-text'", False),
    ("grep -rn 'tmux send-keys' docs/", False),
    ("ls -la", False),
]


def _fake_lookup(globals_: list[str], pane: str) -> str:
    table = {"w1:p1": "claude", "m:p9": "claude", "w1:p2": "", "w1:p3": "codex", "w1:p5": "claude"}
    if pane not in table:
        raise LookupError(pane)
    return table[pane]


def _selftest() -> int:
    os.environ["HERDR_PANE_ID"] = "w1:p5"
    failures = 0
    for command, expected in _CORPUS:
        blocked = classify(command, _fake_lookup) is not None
        if blocked != expected:
            failures += 1
            want = "block" if expected else "allow"
            sys.stderr.write(f"SELFTEST FAIL (want {want}): {command}\n")
    total = len(_CORPUS)
    print(f"pane-input-guard selftest: {total - failures}/{total} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        sys.exit(_selftest())
    sys.exit(main())
