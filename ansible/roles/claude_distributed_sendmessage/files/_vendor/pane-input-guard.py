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
  - `tmux ... send-keys|send ...` carrying literal text (`-l`, or any key
    argument that is not a tmux key name) and `tmux paste-buffer`, into ANY
    pane. tmux is a retired transport here; Codex and pi seats are reached
    with `herdr pane send-text` then `herdr pane send-keys Enter`.

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

Also: a quoted payload that something executes (`sh -c '...'`, `ssh host
'...'`, `watch '...'`, `"$(...)"`, backticks) is classified as a command line;
pane input sent through `ssh` fails CLOSED (the remote pane cannot be seen --
use `herdr --machine`, which the guard can check); heredoc bodies are data
unless they feed a shell; a herdr/tmux token counts only at a command position
(so `echo herdr ...`, `grep`, commit messages pass); `agent prompt` targets are
resolved by `herdr agent get` (names or pane ids); an internal guard error
ALLOWS (stderr note) rather than blocking every Bash call.

Scope: a guardrail against the habit, not a sandbox. Raw `herdr api` socket
calls, and pane input issued from another language (`python3 -c
"subprocess.run(['herdr', ...])"`), are out of scope. A `claude -p` child
inherits its parent's HERDR_PANE_ID and so may type into that one pane. Every token position is scanned for a `herdr` / `tmux`
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
_TMUX_PASTE = {"paste-buffer", "pasteb"}
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


_WRAPPERS = {
    "env",
    "sudo",
    "doas",
    "nice",
    "nohup",
    "timeout",
    "command",
    "exec",
    "stdbuf",
    "time",
    "watch",
    "xargs",
    "setsid",
    "chronic",
    "ionice",
    "mise",
    "uv",
    "uvx",
    "run",
    "--",
    # shell keywords that precede a command
    "do",
    "then",
    "else",
    "elif",
    "if",
    "while",
    "until",
    "{",
    "!",
}
_EXECUTORS = _SHELLS | {
    "ssh",
    "watch",
    "eval",
    "su",
    "sudo",
    "doas",
    "xargs",
    "timeout",
    "nohup",
    "setsid",
    "env",
    "nice",
    "runuser",
    "parallel",
    "script",
    "flock",
}
_SSH_FLAGS_WITH_VALUE = set("pilo JFLRDWbcEemOQSw".replace(" ", ""))
_HEREDOC = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")
_UNTOKENIZABLE_HAZARD = re.compile(
    r"\bherdr\b.*\b(pane\s+(send-text|run)|agent\s+prompt)\b"
    r"|\btmux\b.*\b(send(-keys)?|paste-buffer|pasteb)\b"
)


def _strip_heredocs(command: str) -> str:
    """Drop heredoc BODIES (data, e.g. a commit message), unless the heredoc
    feeds a shell, in which case the body is commands and is kept."""
    lines = command.split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        out.append(line)
        match = _HEREDOC.search(line)
        i += 1
        if not match:
            continue
        head = line[: match.start()].strip().split()
        feeds_shell = bool(head) and _basename(head[0]) in (_SHELLS | {"eval", "ssh"})
        delimiter = match.group(2)
        body: list[str] = []
        while i < len(lines) and lines[i].strip() != delimiter:
            body.append(lines[i])
            i += 1
        if feeds_shell:
            out.extend(body)
        if i < len(lines):
            out.append(lines[i])
            i += 1
    return "\n".join(out)


def _token_segments(command: str) -> list[list[str]]:
    """Quote-aware split into simple commands. Raises ValueError on bad quoting.

    Backtick bodies become their own segments; `$(` opens one through the
    `(` punctuation."""
    text = _strip_heredocs(command).replace("`", " ; ").replace("\n", " ; ")
    lexer = shlex.shlex(text, posix=True, punctuation_chars=";&|()")
    lexer.whitespace_split = True
    segments: list[list[str]] = [[]]
    for tok in lexer:
        if tok and set(tok) <= set(";&|()"):
            segments.append([])
        else:
            segments[-1].append(tok)
    return [seg for seg in segments if seg]


def _lookup_agent(globals_: list[str], kind: str, target: str) -> str:
    """Return the agent herdr reports for `target` ('' when none).

    kind "pane" reads `herdr pane get` (pane ids); kind "agent" reads
    `herdr agent get` (agent names and pane ids; not-found means no agent).
    Raises LookupError when the answer cannot be obtained.
    """
    herdr = os.environ.get("HERDR_BIN_PATH") or "herdr"
    try:
        proc = subprocess.run(
            [herdr, *globals_, kind, "get", target],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
        data = json.loads(proc.stdout.strip() or proc.stderr)
        if kind == "agent" and (data.get("error") or {}).get("code") == "agent_not_found":
            return ""
        record = data["result"][kind]
        return str(record.get("agent") or "")
    except Exception as exc:
        raise LookupError(str(exc)) from exc


def _classify_herdr(args: list[str], lookup, via_ssh: bool) -> str | None:
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
    positionals = [a for a in rest[2:] if a != "--" and not a.startswith("-")]
    if not positionals:
        return None
    target = positionals[0]
    what = f"`herdr {group} {verb}`"
    if via_ssh:
        return _deny_reason(
            f"{what} run through ssh, where the guard cannot see what the remote "
            "pane hosts (failing closed). For a Codex or pi pane on another "
            "machine use `herdr --machine <m> ...`, which the guard can check"
        )
    remote = any(g.split("=")[0] in _HERDR_GLOBALS_WITH_VALUE for g in globals_)
    if not remote and target == os.environ.get("HERDR_PANE_ID", "\0"):
        return None
    if "$" in target:
        return _deny_reason(f"{what} into a target the guard cannot evaluate ({target})")
    try:
        agent = lookup(globals_, "agent" if is_prompt else "pane", target)
    except LookupError:
        return _deny_reason(
            f"{what} into {target}, whose occupant could not be checked (failing closed)"
        )
    if "claude" in agent.lower():
        return _deny_reason(f"{what} would type into {target}, which hosts a {agent} session")
    return None


def _classify_tmux(args: list[str]) -> str | None:
    if any(a in _TMUX_PASTE for a in args):
        return _deny_reason(
            "`tmux paste-buffer` pastes text into a pane (tmux is a retired transport)"
        )
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
    printable = [k for k in keys if len(k) == 1]
    if len(printable) > 1:
        return _deny_reason(
            "`tmux send-keys` spells out text one character at a time "
            "(tmux is a retired transport)"
        )
    for key in keys:
        if not _TMUX_KEY.match(key):
            return _deny_reason(
                f"`tmux send-keys` types literal text ({key!r}) into a pane "
                "(tmux is a retired transport)"
            )
    return None


def _at_command_position(tokens: list[str], n: int) -> bool:
    """True when tokens[n] can be a command head: segment start, or after a
    wrapper, an option, a bare number (timeout 5) or a VAR=value."""
    if n == 0:
        return True
    prev = tokens[n - 1]
    return (
        _basename(prev) in _WRAPPERS
        or prev.startswith("-")
        or bool(re.fullmatch(r"\d+(\.\d+)?[smhd]?", prev))
        or ("=" in prev and not prev.startswith("="))
        # an option's value: `sudo -u ubuntu herdr`, `timeout -s KILL 5 tmux`
        or (n >= 2 and tokens[n - 2].startswith("-") and _basename(tokens[0]) in _WRAPPERS)
    )


def _ssh_remainder(rest: list[str]) -> str | None:
    i = 0
    while i < len(rest) and rest[i].startswith("-"):
        flag = rest[i]
        i += 2 if (len(flag) == 2 and flag[1] in _SSH_FLAGS_WITH_VALUE) else 1
    if i >= len(rest):
        return None
    remainder = rest[i + 1 :]
    return " ".join(remainder) if remainder else None


def classify(
    command: str, lookup=_lookup_agent, depth: int = 0, via_ssh: bool = False
) -> str | None:
    """Return a deny reason, or None to allow."""
    if depth > _MAX_DEPTH:
        return _deny_reason("a command nested too deeply to inspect")
    if not re.search(r"herdr|tmux", command):
        return None
    try:
        segments = _token_segments(command)
    except ValueError:
        if _UNTOKENIZABLE_HAZARD.search(command):
            return _deny_reason("a pane-input-shaped command that does not tokenize")
        return None
    for tokens in segments:
        for n, tok in enumerate(tokens):
            # A quoted payload is re-classified as a command line of its own
            # when something EXECUTES it: it follows an executor (sh -c '...',
            # ssh host '...', watch '...', sudo ...) or it carries a "$(...)".
            # A quoted argument to echo, grep or git commit -m is data.
            if not (re.search(r"\s", tok) and re.search(r"\b(herdr|tmux)\b", tok)):
                continue
            executed = "$(" in tok or any(_basename(t) in _EXECUTORS for t in tokens[:n])
            if executed:
                verdict = classify(tok, lookup, depth + 1, via_ssh)
                if verdict:
                    return verdict
        for n, tok in enumerate(tokens):
            base = _basename(tok)
            rest = tokens[n + 1 :]
            if not _at_command_position(tokens, n):
                continue
            if base == "ssh":
                remainder = _ssh_remainder(rest)
                if remainder:
                    verdict = classify(remainder, lookup, depth + 1, via_ssh=True)
                    if verdict:
                        return verdict
                break
            if base == "eval" and rest:
                verdict = classify(" ".join(rest), lookup, depth + 1, via_ssh)
                if verdict:
                    return verdict
                break
            if base == "herdr":
                verdict = _classify_herdr(rest, lookup, via_ssh)
                if verdict:
                    return verdict
                break
            if base == "tmux":
                verdict = _classify_tmux(rest)
                if verdict:
                    return verdict
                break
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        if payload.get("tool_name") not in (None, "Bash"):
            return 0
        command = (payload.get("tool_input") or {}).get("command") or ""
        reason = classify(command)
    except Exception as exc:  # noqa: BLE001
        # A guard bug must not take every Bash call down with it: allow, and
        # say so on stderr (shown in the transcript as a hook error).
        sys.stderr.write(f"pane-input-guard: internal error, allowing: {exc!r}\n")
        return 0
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
    ("tmux paste-buffer -b sup -t seat", True),
    ("tmux load-buffer -b sup /tmp/msg.txt", False),
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
    # agent prompt resolves names through `herdr agent get`
    ("herdr agent prompt codex-seat 'go'", False),
    ("herdr agent prompt claude-seat 'go'", True),
    ("herdr agent prompt no-such-agent 'go'", False),
    # nested and quoted payloads
    ('x="$(herdr pane send-text w1:p1 hi)"', True),
    ("echo `herdr pane send-text w1:p1 hi`", True),
    ("bash --norc -c 'herdr pane send-text w1:p1 hi'", True),
    ("watch -n1 'herdr pane send-text w1:p1 hi'", True),
    ("ssh gamingpc 'herdr pane send-text w1:p2 hi'", True),
    ("ssh -p 22 gamingpc herdr pane run w1:p2 ls", True),
    ("ssh gamingpc 'herdr pane read w1:p1'", False),
    ("herdr pane send-text -- w1:p1 hi", True),
    ("herdr --machine=m pane send-text m:p9 hi", True),
    # heredoc bodies are data unless they feed a shell
    ("git commit -F - <<'EOF'\nfix: guard denies herdr pane send-text w1:p1 hi\nEOF", False),
    ("git commit -F - <<'EOF'\nfix: don't run tmux send-keys anymore\nEOF", False),
    ("cat > notes.md <<'EOF'\nUse herdr pane send-keys, don't use tmux\nEOF", False),
    ("bash <<'EOF'\nherdr pane send-text w1:p1 hi\nEOF", True),
    ("git commit -m 'fix herdr pane send-text bug'", False),
    ("echo herdr pane send-text w1:p1 hi", False),
    ("for p in w1:p1; do herdr pane send-text $p hi; done", True),
    ("if true; then herdr pane run w1:p1 ls; fi", True),
    ("tmux send-keys -t seat g i t Enter", True),
]


def _fake_lookup(globals_: list[str], kind: str, target: str) -> str:
    table = {"w1:p1": "claude", "m:p9": "claude", "w1:p2": "", "w1:p3": "codex", "w1:p5": "claude"}
    if kind == "agent":
        names = {"codex-seat": "codex", "claude-seat": "claude"}
        if target in names:
            return names[target]
        if target in table:
            return table[target]
        return ""
    if target not in table:
        raise LookupError(target)
    return table[target]


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
