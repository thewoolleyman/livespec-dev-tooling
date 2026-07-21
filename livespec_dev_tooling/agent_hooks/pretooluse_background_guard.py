"""pretooluse_background_guard — deny `run_in_background` for gate commands.

Per work-item livespec-dev-tooling-7us.2: the premature-turn-end
failure starts when an executor backgrounds a long gate command
(`just check`, the Red-Green-Replay commit hook, `git push`, the PR
handoff) because it exceeds the default foreground Bash timeout, then
ends its turn to "wait for the notification" — fatal in a one-shot
sub-agent. With the committed `BASH_DEFAULT_TIMEOUT_MS` raised, gates
always fit FOREGROUND, so backgrounding them is wrong in every
context. This Claude Code `PreToolUse` hook (matcher `Bash`) denies
any Bash call that combines `run_in_background` with a gate command.

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
non-gate commands is untouched, and gate commands have no legitimate
background use once the foreground timeout is raised.

Output discipline: structlog JSON to stderr (the deny reason the
agent reads IS the structured event); no `print`, no
`sys.stderr.write`. The vendored `structlog` under
`livespec_dev_tooling/_vendor` is added to `sys.path` at module
import time.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import cast

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

__all__: list[str] = []


# Gate-command shapes. Each pattern tolerates wrapper prefixes
# (`mise exec -- git commit`, `git -C <path> push`) by allowing
# non-separator filler between the binary and the subcommand; the
# filler class excludes shell separators so `git log && just build`
# does not bridge into a false match across commands.
_GATE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("just check", re.compile(r"\bjust\b[^\n;|&]*\bcheck")),
    ("git commit", re.compile(r"\bgit\b[^\n;|&]*\bcommit\b")),
    ("git push", re.compile(r"\bgit\b[^\n;|&]*\bpush\b")),
    ("gh pr", re.compile(r"\bgh\s+pr\b")),
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


def _matched_gate(*, command: str) -> str | None:
    """Return the gate label the command matches, or None."""
    for label, pattern in _GATE_PATTERNS:
        if pattern.search(command):
            return label
    return None


def _should_deny(*, tool_name: str, tool_input: dict[str, object]) -> str | None:
    """Pure deny decision — the matched gate label, or None to allow.

    Denies iff the call is a Bash tool call, `run_in_background` is
    literally true, and the command matches a gate pattern.
    """
    if tool_name != "Bash":
        return None
    if tool_input.get("run_in_background") is not True:
        return None
    command = tool_input.get("command")
    if not isinstance(command, str):
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
        "DENIED: backgrounding a gate command — run it FOREGROUND instead",
        check_id="pretooluse-background-guard-deny",
        gate=gate,
        command=tool_input.get("command"),
        hint=(
            "Gate commands (just check*, git commit, git push, gh pr ...) must run "
            "FOREGROUND: re-issue the same Bash call WITHOUT run_in_background and "
            "with a raised timeout (the committed BASH_DEFAULT_TIMEOUT_MS / "
            "BASH_MAX_TIMEOUT_MS give long gates room). A backgrounded gate plus a "
            "turn-end terminates a sub-agent mid-dispatch — nothing re-invokes it."
        ),
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
