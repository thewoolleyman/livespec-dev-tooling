#!/usr/bin/env python3
"""
livespec footgun guard — Claude Code PreToolUse hook (Bash).

Blocks ONLY patterns that are NEVER legitimate in the livespec family:
  - `git ... commit/push ... --no-verify`
  - `git ... config core.bare <true>`   (set; NOT --get/--unset/--list reads)
  - a leading `LEFTHOOK=0|false` env-assignment (the --no-verify equivalent)
each with an actionable deny message naming the correct alternative.

Detection is TOKEN/SEGMENT based, not substring based. A real footgun is the
EXECUTED leading command of a shell segment — e.g. `git config core.bare true`
or `... && LEFTHOOK=0 git commit`. The dangerous strings frequently appear as
DATA (a test fixture, an `echo`, a `git log --grep`, a here-doc body, a commit
message); those must NOT be blocked. So for each `&&`/`||`/`;`/`|`/newline
segment we strip leading env-assignments + `mise exec --` + `sudo`/`env`
wrappers, then inspect only the resulting git invocation. A segment whose
leading command is `echo`/`grep`/`python`/`cat`/etc. is never a footgun no
matter what string it carries.

Always exits 0; fails OPEN on any parse/tokenize error (a guard bug must never
block legitimate work — the commit-refuse hook + branch protection are the real
backstops; this guard is only a fast early warning).
"""

import json
import re
import shlex
import sys

__all__: list[str] = []

_NO_VERIFY_REASON = (
    "NEVER use --no-verify in the livespec family. The lefthook gates "
    "(commit-msg, pre-commit, pre-push, Red-Green-Replay trailers) are "
    "load-bearing. If a hook rejects a commit, READ the rejection and fix the "
    "ROOT CAUSE, or HALT and ask the user — do not bypass. "
    "(memory feedback_sub_agent_dispatch_no_verify_ban)"
)
_CORE_BARE_REASON = (
    "NEVER set core.bare=true. Epic li-unbare eliminated the bare flag; "
    "core.bare on a primary is a REGRESSION the doctor invariant "
    "(primary-checkout-commit-refuse-hook-installed) forbids. Do edits in a "
    "secondary worktree via `git -C <repo> worktree add "
    "~/.worktrees/<repo>/<branch> -b <branch> origin/master`. "
    "(memory feedback_bare_flag_use_git_show_not_filesystem)"
)
_LEFTHOOK_REASON = (
    "NEVER set LEFTHOOK=0/false — it disables lefthook, a --no-verify "
    "equivalent. Fix the failing hook's root cause or HALT and ask. "
    "(memory feedback_sub_agent_dispatch_no_verify_ban)"
)

_ENV_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_GIT_GLOBAL_OPTS_WITH_ARG = ("-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path")
_SEGMENT_SPLIT = re.compile(r"&&|\|\||;|\||\n")
_HEREDOC = re.compile(r"<<-?\s*['\"]?([A-Za-z_][A-Za-z0-9_]*)['\"]?")


def _strip_heredoc_bodies(*, command: str) -> str:
    """Remove here-doc BODIES (they are file data, not executed commands).

    `cat > f <<'EOF'\n...body...\nEOF` — the body lines are data; analyzing them
    as command segments causes false positives. Keep the introducing line, drop
    everything from the next line through the terminator line.
    """
    lines = command.split("\n")
    out: list[str] = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        out.append(line)
        m = _HEREDOC.search(line)
        if m:
            term = m.group(1)
            i += 1
            # Skip body until a line that is exactly the terminator (optionally
            # indented for <<-).
            while i < n and lines[i].strip() != term:
                i += 1
            # `i` now points at the terminator line (or EOF); skip it too.
            if i < n:
                i += 1
            continue
        i += 1
    return "\n".join(out)


def _segments(*, command: str) -> list[str]:
    cleaned = _strip_heredoc_bodies(command=command)
    return [s.strip() for s in _SEGMENT_SPLIT.split(cleaned) if s.strip()]


def _strip_leading_noise(*, tokens: list[str]) -> tuple[list[str], bool]:
    """Strip leading env-assignments and `mise exec [--] ` / `sudo` / `env`.

    Returns (remaining tokens, lefthook_disabled_seen).
    """
    lefthook_off = False
    i = 0
    n = len(tokens)
    # Leading VAR=val assignments (env for the command).
    while i < n and _ENV_ASSIGN.match(tokens[i]):
        if re.match(r"^LEFTHOOK=(?:0|false|off|no)$", tokens[i], re.IGNORECASE):
            lefthook_off = True
        i += 1
    # `mise exec [flags] [--]` wrapper (possibly repeated with sudo/env).
    changed = True
    while changed and i < n:
        changed = False
        base = tokens[i].rsplit("/", 1)[-1]
        if base in ("sudo", "env"):
            i += 1
            changed = True
            while i < n and _ENV_ASSIGN.match(tokens[i]):
                i += 1
            continue
        if base == "mise":
            j = i + 1
            # consume `exec`, any flags, and a `--` terminator
            while (j < n and tokens[j] != "--" and tokens[j] in ("exec", "x")) or (
                j < n and tokens[j].startswith("-")
            ):
                j += 1
            if j < n and tokens[j] == "--":
                j += 1
            if j > i:
                i = j
                changed = True
            continue
    return tokens[i:], lefthook_off


def _git_subcommand(*, tokens: list[str]) -> tuple[str | None, list[str]]:
    """If tokens is a git invocation, return (subcommand, args_after_subcommand)."""
    if not tokens:
        return None, []
    if tokens[0].rsplit("/", 1)[-1] != "git":
        return None, []
    i = 1
    n = len(tokens)
    while i < n:
        t = tokens[i]
        if t == "--":
            i += 1
            break
        if not t.startswith("-"):
            break
        i += 1
        if t in _GIT_GLOBAL_OPTS_WITH_ARG and i < n:
            i += 1
    if i >= n:
        return None, []
    return tokens[i], tokens[i + 1 :]


def _check_segment(*, seg: str) -> tuple[bool, str]:
    try:
        tokens = shlex.split(seg, posix=True)
    except ValueError:
        return False, ""  # unparseable → fail open
    if not tokens:
        return False, ""
    core, lefthook_off = _strip_leading_noise(tokens=tokens)
    if lefthook_off:
        return True, _LEFTHOOK_REASON
    sub, args = _git_subcommand(tokens=core)
    if sub is None:
        return False, ""  # leading command isn't git → not a footgun
    if sub in ("commit", "push") and "--no-verify" in args:
        return True, _NO_VERIFY_REASON
    if sub == "config":
        # Reads/removes are fine; only a SET of core.bare to a truthy value is the footgun.
        if any(a in ("--get", "--unset", "--list", "--get-all", "--unset-all") for a in args):
            return False, ""
        joined = " ".join(args)
        if re.search(r"\bcore\.bare\b", joined) and re.search(
            r"\b(?:true|1|yes|on)\b", joined, re.IGNORECASE
        ):
            return True, _CORE_BARE_REASON
        # also catches `config core.bare=true`
        if re.search(r"\bcore\.bare\s*=\s*(?:true|1|yes|on)\b", joined, re.IGNORECASE):
            return True, _CORE_BARE_REASON
    return False, ""


def _deny_payload(*, reason: str, command: str) -> str:
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                f"BLOCKED by livespec_footgun_guard.py\n\n{reason}\n\n"
                f"Command: {command}\n\n"
                "This block is NOT a transient/transport failure. Do NOT retry "
                "the same command. Use the named alternative, or stop and ask "
                "the user. If this is a FALSE positive, tighten "
                "~/.claude/hooks/livespec_footgun_guard.py."
            ),
        }
    }
    return json.dumps(payload)


def _decision(*, raw: str) -> str | None:
    """Return the deny payload for a footgun command, or None to allow.

    Raises `json.JSONDecodeError` on malformed hook input; `main`'s narrow
    seam catch turns that into the fail-open pass-through.
    """
    if not raw.strip():
        return None
    data = json.loads(raw)
    if data.get("tool_name", "") != "Bash":
        return None
    command = data.get("tool_input", {}).get("command", "")
    if not command:
        return None
    for seg in _segments(command=command):
        blocked, reason = _check_segment(seg=seg)
        if blocked:
            return _deny_payload(reason=reason, command=command)
    return None


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
