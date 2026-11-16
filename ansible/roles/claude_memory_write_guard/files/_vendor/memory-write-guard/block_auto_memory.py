#!/usr/bin/env python3
"""
block_auto_memory (managed copy) — a Claude Code MANAGED-settings PreToolUse
hook that refuses writes into an agent memory directory in EVERY project, and
routes the content to where durable knowledge lives.

VENDORED from livespec-driver-claude `.claude-plugin/hooks/block_auto_memory.py`
at release v0.15.4, commit 4ac6370948d31798c36726caf167bf7039ea4867, together
with its unmodified siblings `_memory_write.py`, `_shell_io.py`, `_shell_lex.py`
and `_result.py`. That release carries the cd-relative fix
(livespec-driver-claude-ivftll, v0.15.3) and the heredoc false-positive fix
(livespec-driver-claude-zexdsh, v0.15.4). Re-vendor from the Driver when its
matcher changes; do not fork the matcher here.

The differences from the Driver copy are in this file, and in `_result.py`
(difference 5):

1. NO GOVERNED-PROJECT GATE. The Driver hook blocks only when
   `$CLAUDE_PROJECT_DIR` carries a `.livespec.jsonc` naming an impl-plugin.
   This copy is installed as managed policy on every interactive fleet host
   (livespec-dev-tooling-pik7f2) and acts in every project, so the
   `_livespec_project` resolver is not vendored.
2. The deny reason names no impl-plugin namespace: it routes durable guidance
   to the repository's AGENTS.md or a referenced `.ai/<topic>.md` by pull
   request, and trackable work to the repository's ledger.
3. `NotebookEdit` is judged as a file tool too, by its `notebook_path`.
4. The file-tool matcher is NARROWED to the Claude Code layout
   `<anything>/projects/<slug>/memory/*.md`, the same shape the Bash
   classifier requires. The Driver's own matcher refuses ANY `**/memory/*.md`,
   which is harmless behind its governed-project gate but would refuse tracked
   repository files such as `<repo>/.ai/memory/*.md` once this copy acts in
   every project.

5. `_result.py` is PYTHON 3.9 COMPATIBLE. The Driver copy imports
   `typing.TypeAlias` and evaluates `Success[_T] | Failure[_E]` at module scope,
   both 3.10+; on a Mac's system `/usr/bin/python3` (3.9.6) the import raises,
   Claude Code treats the hook error as non-blocking, and the guard silently
   refuses nothing (livespec-dev-tooling-i76rv2). The copy uses
   `typing.Union` instead. The same defect is in the Driver's shipped hooks
   under a bare system python3 3.9; it is filed against livespec-driver-claude.
   Re-vendoring from a Driver that fixed it drops this difference.

Everything else is the Driver's: a file tool is refused when the target is an
`.md` file whose parent directory is `memory` and whose great-grandparent is
`projects` (the Claude Code layout `~/.claude/projects/<slug>/memory/*.md`,
difference 4), or when the target lies
under the Codex store `~/.codex/memories/`; a `Bash` command is refused when
`_memory_write.writes_memory` POSITIVELY identifies it as writing into either
directory. Reads and `rm` pass.

Fail-open contract: ANY failure (malformed stdin, an unexpected exception) is
a silent pass-through with exit 0. The hook blocks only on a positive
identification and never exits non-zero.

Self-contained: it runs under bare system `python3` with no third-party
packages; every import is the standard library or a sibling module installed
beside it (Python puts the script's own directory first on `sys.path`).
"""

from __future__ import annotations

import json
import sys
from pathlib import PurePosixPath
from typing import cast

from _memory_write import writes_memory
from _result import Failure, Result, Success

__all__: list[str] = []

_FILE_TOOLS = frozenset({"Write", "Edit", "MultiEdit", "NotebookEdit"})
_CODEX_MEMORY_STORE = (".codex", "memories")

DENY_REASON = (
    "Local agent memory is not used on this fleet. Per-session memory files "
    "(~/.claude/projects/<slug>/memory/*.md, ~/.codex/memories/) are ephemeral, "
    "per-user and per-machine, outside GitOps and the ledger, and invisible to "
    "other agents and runtimes. Do NOT silently drop what you were about to "
    "write; route it by what it IS:\n"
    "  - Durable agent guidance, a learned preference or a convention -> the "
    "repository's AGENTS.md, or a .ai/<topic>.md file that AGENTS.md references, "
    "landed by pull request.\n"
    "  - Trackable work (task, bug, refactor, follow-up) or status -> the "
    "repository's ledger (in a livespec-governed repository, through its "
    "capture-work-item operation).\n"
    "  - A spec-level rule or behavior -> /livespec:propose-change.\n"
    "  - ONLY genuinely session-only notes that matter nowhere outside this "
    "session may be dropped."
)


def _as_object_dict(*, value: object) -> dict[str, object] | None:
    """Narrow an arbitrary JSON value to a string-keyed dict, else None."""
    if isinstance(value, dict):
        return cast("dict[str, object]", value)
    return None


def _is_memory_file(*, file_path: str) -> bool:
    """A Claude Code `projects/<slug>/memory/*.md` note, or any file under the Codex store."""
    target = PurePosixPath(file_path)
    if (
        target.suffix == ".md"
        and target.parent.name == "memory"
        and target.parent.parent.parent.name == "projects"
    ):
        return True
    parts = target.parent.parts
    width = len(_CODEX_MEMORY_STORE)
    return any(parts[i : i + width] == _CODEX_MEMORY_STORE for i in range(len(parts)))


def _memory_write(*, tool_name: object, tool_input: dict[str, object]) -> bool:
    """Whether this tool call writes into an agent memory directory."""
    if tool_name == "Bash":
        command = tool_input.get("command")
        return isinstance(command, str) and writes_memory(command=command)
    file_path = tool_input.get("file_path", tool_input.get("notebook_path"))
    return (
        tool_name in _FILE_TOOLS
        and isinstance(file_path, str)
        and _is_memory_file(file_path=file_path)
    )


def _block_decision(*, raw: str) -> str | None:
    """Return the block-decision JSON, or None for a pass-through."""
    payload = _as_object_dict(value=json.loads(raw))
    if payload is None:
        return None
    tool_input = _as_object_dict(value=payload.get("tool_input"))
    if tool_input is None or not _memory_write(
        tool_name=payload.get("tool_name"), tool_input=tool_input
    ):
        return None
    return json.dumps(
        {
            "decision": "block",
            "reason": DENY_REASON,
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": DENY_REASON,
            },
        }
    )


def _decision_result(*, raw: str) -> Result[str | None, Exception]:
    """Lift expected pass-through failures (`json.loads`' ValueError) onto the rail."""
    try:
        return Success(_block_decision(raw=raw))
    except ValueError as exc:
        return Failure(exc)


def main() -> int:
    """Hook entry point: emit the block decision, if any; always exit 0."""
    try:
        raw = sys.stdin.read()
        decision = _decision_result(raw=raw).value_or(default=None)
        if decision is not None:
            _ = sys.stdout.write(decision + "\n")
    except Exception:  # noqa: BLE001 — sole fail-open hook boundary: silent pass-through, exit 0
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
