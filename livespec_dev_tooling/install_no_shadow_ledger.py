"""install_no_shadow_ledger — install the canonical neutral no-shadow-ledger hook body.

Writes the canonical no-shadow-ledger Stop-hook body to a consumer's
configured `neutral_hook_body_path` (a `[tool.livespec_dev_tooling]` role
key in the consuming repo's `pyproject.toml`). Mirrors
`install_commit_refuse_hooks` (Conformance-Pattern concern #1): a single
packaged carrier constant is the source of truth, so the neutral hook body
that BOTH livespec Driver plugins ship (livespec-driver-claude at
`.claude-plugin/hooks/`, livespec-driver-codex at `livespec/hooks/`) never
drifts between the two copies.

The canonical body ships as the module-level `CANONICAL_NO_SHADOW_LEDGER_BODY`
string constant in THIS module so it travels in the wheel, exactly as
`CANONICAL_HOOK_BODY` does in `install_commit_refuse_hooks`. It is byte-identical
to the seed hook body at `livespec-driver-codex`'s `livespec/hooks/no_shadow_ledger.py`,
with one surgical edit: the run-on-import tail (`try: warning = _warning() ...
sys.exit(0)`) is replaced with an importable `main() -> int`, so the body is
testable in-process (no Python subprocess spawn) for real per-file coverage
and so a Driver's `hooks.json` Stop entry can invoke it as
`python3 <path> && exit 0`-style wrapper without behavior change (fail-open,
WARN-only, never blocks the stop).

CLI:
    python -m livespec_dev_tooling.install_no_shadow_ledger
        Install (or idempotently re-install) the canonical body at the
        consumer's configured `neutral_hook_body_path`. No-ops (exit 0) when
        the role key is declared ABSENT — one of the four blessed inline
        tables — and the check-side counterpart
        (`checks/no_shadow_ledger_body_identical.py`) no-ops identically
        there, so a consumer that has declared the key absent sees neither
        installer nor verifier activity.

        The two DIVERGE when the key is UNDECLARED, and only the check is
        gated: this installer reads `role_path` directly and no-ops, while
        the check runs `role_absence_exit_code` first and hard-errors
        (exit 1) naming the key, because `neutral_hook_body_path` is a
        REQUIRED role key that every conformant consumer declares. Whether
        the installer should be gated likewise is an open question, not a
        settled asymmetry.

Output discipline: structlog JSON to stderr; no `print`, no
`sys.stdout.write` / `sys.stderr.write`.
"""

from __future__ import annotations

import sys
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

from livespec_dev_tooling.config import (  # noqa: E402
    load_config,
    role_path,
)

__all__: list[str] = [
    "CANONICAL_NO_SHADOW_LEDGER_BODY",
    "install_neutral_hook_body",
    "main",
]


# The canonical no-shadow-ledger Stop-hook body. Embedded here as the
# wheel-safe carrier (see the module docstring) — byte-identical to the
# seed body at `livespec-driver-codex`'s `livespec/hooks/no_shadow_ledger.py`
# apart from the run-on-import tail, which is replaced with an importable
# `main() -> int`.
CANONICAL_NO_SHADOW_LEDGER_BODY = r'''#!/usr/bin/env python3
"""
livespec no-shadow-ledger — Stop hook warning on planning artifacts that
embed a checkbox task queue instead of deriving status from the ledger.

Shipped BYTE-IDENTICALLY by both Drivers (livespec-driver-claude at
.claude-plugin/hooks/, livespec-driver-codex at livespec/hooks/) as the
single-sourced neutral body; each Driver's hooks.json Stop entry is the
thin per-runtime adapter that invokes it. Codex consumes the Claude Stop
hook I/O format, so this one body serves both runtimes.

Declared on the `Stop` event. Scans the agent's last turn (the transcript
entries after the last REAL user message — tool-result deliveries do NOT
reset the window) for file-persisting tool calls (Write / Edit /
MultiEdit) that wrote a PLANNING ARTIFACT — a handoff, or any markdown
file under a plan/ or prompts/ directory. When such an artifact's written
content carries markdown checkbox task-list items ([ ] / [x]) at or above
a mechanical threshold, it emits a `systemMessage` WARNING on stdout.

WARN-ONLY BY CONTRACT (livespec core non-functional-requirements
"No shadow ledger"; contracts.md): this hook NEVER blocks the stop — it never
emits a `decision` key and never exits non-zero — and it never auto-edits
anything. The mechanical detection internals (the planning-artifact path
predicate, the checkbox threshold, the persisting-tool set) are Driver
implementation detail and MAY be tuned without a core spec cycle, per the
contract, provided the WARN-only Stop posture holds.

Fail-open contract: ANY failure (no python3 on PATH, malformed stdin,
missing/unreadable transcript, malformed transcript lines) is a silent
pass-through with exit 0.
"""

import json
import re
import sys
from pathlib import Path
from typing import cast

# Mechanical "shadow-ledger smell" threshold: number of markdown checkbox
# task-list items in a single persisted planning artifact.
CHECKBOX_THRESHOLD = 3

# Tool calls that persist content to disk (NotebookEdit is excluded — a
# planning handoff is never a notebook).
PERSISTING_TOOLS = frozenset({"Write", "Edit", "MultiEdit"})

# A markdown task-list item: a list bullet followed by a [ ] / [x] box. The
# anchor at line start keeps inline prose like `[ ]` (e.g. a rule quoting
# the forbidden syntax) from matching — only real list items count.
_CHECKBOX_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+\[[ xX]\]")


def _is_real_user_entry(*, entry: dict[str, object]) -> bool:
    """A user entry typed by the human — NOT a tool_result delivery."""
    if entry.get("type") != "user":
        return False
    message = entry.get("message")
    if not isinstance(message, dict):
        return False
    content = cast("dict[str, object]", message).get("content")
    if isinstance(content, str):
        return bool(content.strip())
    if not isinstance(content, list):
        return False
    has_text = False
    for block in cast("list[object]", content):
        if not isinstance(block, dict):
            continue
        block_dict = cast("dict[str, object]", block)
        if block_dict.get("type") == "tool_result":
            return False
        if block_dict.get("type") == "text":
            has_text = True
    return has_text


def _written_text(*, name: str, tool_input: dict[str, object]) -> str:
    """The content a persisting tool call wrote, aggregated to one string."""
    if name == "Write":
        text = tool_input.get("content")
        return text if isinstance(text, str) else ""
    if name == "Edit":
        text = tool_input.get("new_string")
        return text if isinstance(text, str) else ""
    if name == "MultiEdit":
        edits = tool_input.get("edits")
        parts: list[str] = []
        if isinstance(edits, list):
            for edit in cast("list[object]", edits):
                if not isinstance(edit, dict):
                    continue
                new_string = cast("dict[str, object]", edit).get("new_string")
                if isinstance(new_string, str):
                    parts.append(new_string)
        return "\n".join(parts)
    return ""


def _last_turn_writes(*, entries: list[dict[str, object]]) -> list[tuple[str, str]]:
    """(path, written-text) pairs persisted after the last real user message."""
    start = 0
    for index, entry in enumerate(entries):
        if _is_real_user_entry(entry=entry):
            start = index + 1
    writes: list[tuple[str, str]] = []
    for entry in entries[start:]:
        if entry.get("type") != "assistant":
            continue
        message = entry.get("message")
        if not isinstance(message, dict):
            continue
        content = cast("dict[str, object]", message).get("content")
        if not isinstance(content, list):
            continue
        for block in cast("list[object]", content):
            if not isinstance(block, dict):
                continue
            block_dict = cast("dict[str, object]", block)
            if block_dict.get("type") != "tool_use":
                continue
            name = block_dict.get("name")
            if name not in PERSISTING_TOOLS:
                continue
            tool_input = block_dict.get("input")
            if not isinstance(tool_input, dict):
                continue
            tool_input_dict = cast("dict[str, object]", tool_input)
            path = tool_input_dict.get("file_path")
            if not isinstance(path, str) or not path:
                continue
            writes.append((path, _written_text(name=name, tool_input=tool_input_dict)))
    return writes


def _is_planning_artifact(*, path: str) -> bool:
    """A handoff, or any markdown file under a plan/ or prompts/ directory."""
    lowered = path.lower()
    if not lowered.endswith(".md"):
        return False
    name = lowered.rsplit("/", 1)[-1]
    if "handoff" in name:
        return True
    segments = lowered.split("/")
    return "plan" in segments or "prompts" in segments


def _checkbox_count(*, text: str) -> int:
    return sum(1 for line in text.splitlines() if _CHECKBOX_RE.match(line))


def _warning() -> str | None:
    """Return the systemMessage JSON, or None for a silent pass-through."""
    payload = json.load(sys.stdin)
    if not isinstance(payload, dict):
        return None
    payload_dict = cast("dict[str, object]", payload)
    if payload_dict.get("stop_hook_active"):
        return None
    transcript_path = payload_dict.get("transcript_path")
    if not isinstance(transcript_path, str) or not transcript_path:
        return None
    transcript = Path(transcript_path)
    if not transcript.is_file():
        return None
    entries: list[dict[str, object]] = []
    for line in transcript.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            parsed = json.loads(line)
        except ValueError:
            continue  # fail-open per line: skip malformed transcript lines
        if isinstance(parsed, dict):
            entries.append(cast("dict[str, object]", parsed))
    for path, text in _last_turn_writes(entries=entries):
        if not _is_planning_artifact(path=path):
            continue
        count = _checkbox_count(text=text)
        if count >= CHECKBOX_THRESHOLD:
            message = (
                "livespec no-shadow-ledger WARN: this turn wrote a planning "
                f"artifact ({path}) carrying {count} checkbox task items "
                "([ ]/[x]). The no-shadow-ledger rule (livespec "
                'non-functional-requirements §"Planning Lane guidance") '
                "requires a handoff to derive status from the work-item ledger "
                "as its first action: each checklist item is a session-local "
                "step OR a pointer to a real ledger id, never a parallel work "
                "queue that shadows the ledger. Replace the embedded checkbox "
                "queue with ledger-id pointers and a ledger-status query."
            )
            return json.dumps({"systemMessage": message})
    return None


def main() -> int:
    """Hook entry point: emit the shadow-ledger WARN, if any; always exit 0.

    Owns the stdout write at the hook boundary and catches every failure so
    the Stop hook stays fail-open by contract — it NEVER blocks the stop and
    NEVER exits non-zero. Importable (no work at module import) so the hook
    body is testable in-process for real per-file coverage.
    """
    try:
        warning = _warning()
    except Exception:  # noqa: BLE001 — sole fail-open hook boundary: silent pass-through, exit 0
        warning = None
    if warning is not None:
        _ = sys.stdout.write(warning + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


def _configure_logger() -> structlog.stdlib.BoundLogger:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    return structlog.get_logger("install_no_shadow_ledger")


def install_neutral_hook_body(*, cwd: Path, log: structlog.stdlib.BoundLogger) -> int:
    """Install the canonical neutral hook body at the consumer's configured path.

    Reads `neutral_hook_body_path` via `load_config(repo_root=cwd)`. When
    `role_path` resolves to `None` — the consumer declared the key absent via
    one of the four blessed inline tables, OR did not declare it at all —
    logs a structured info event and no-ops (returns 0). That mirrors the
    check-side counterpart for a DECLARED-ABSENT key only: this installer
    does not run `role_absence_exit_code`, so where the check hard-errors on
    an UNDECLARED required key, this no-ops. See the module docstring.
    Otherwise writes
    `CANONICAL_NO_SHADOW_LEDGER_BODY` to `cwd / neutral_hook_body_path`,
    creating parent directories as needed, and logs a structured info event.
    Idempotent: re-running overwrites with the identical canonical body.
    Returns 0 on success.
    """
    config = load_config(repo_root=cwd)
    neutral_hook_body_path = role_path(role=config.neutral_hook_body_path)
    if neutral_hook_body_path is None:
        log.info(
            "role key absent — installer no-ops",
            role="neutral_hook_body_path",
        )
        return 0
    target = cwd / neutral_hook_body_path
    target.parent.mkdir(parents=True, exist_ok=True)
    _ = target.write_text(CANONICAL_NO_SHADOW_LEDGER_BODY, encoding="utf-8")
    log.info(
        "installed canonical no-shadow-ledger hook body",
        path=str(target),
    )
    return 0


def main() -> int:
    log = _configure_logger()
    return install_neutral_hook_body(cwd=Path.cwd(), log=log)


if __name__ == "__main__":
    raise SystemExit(main())
