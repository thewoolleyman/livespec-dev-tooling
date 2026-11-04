"""Shared helpers for the Codex hook-reconciliation check and its payload validator.

Private sibling of `codex_hook_reconcilable` and `_codex_hook_payload`: the
finding emitter and the path/JSON primitives both of them need, in their own
module so neither has to import the other's private names.
"""

from __future__ import annotations

import json
import posixpath
import sys
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

__all__: list[str] = [
    "CHECK_ID",
    "emit_failure",
    "payload_contains",
    "read_json",
    "relative_path",
]


CHECK_ID = "codex_hook_reconcilable"


def relative_path(*, plugin_root: str, declared_path: str) -> str:
    """Resolve a plugin-relative declaration to a normalized repository path."""
    return posixpath.normpath(posixpath.join(plugin_root, declared_path))


def payload_contains(*, tracked: frozenset[str], plugin_root: str, path: str, root: Path) -> bool:
    """Return whether `path` is a tracked regular file inside `plugin_root`."""
    prefix = f"{plugin_root}/" if plugin_root != "." else ""
    return path.startswith(prefix) and path in tracked and (root / path).is_file()


def emit_failure(
    *,
    log: structlog.stdlib.BoundLogger,
    message: str,
    **finding: str,
) -> None:
    """Emit one complete structured failure finding."""
    event = finding.pop("event", "")
    command = finding.pop("command", "")
    entrypoint = finding.pop("entrypoint", "")
    log.error(
        message,
        check_id=CHECK_ID,
        status="fail",
        hook_event=event,
        command=command,
        entrypoint=entrypoint,
        line=0,
        **finding,
    )


def read_json(*, root: Path, path: str) -> tuple[object | None, bool]:
    """Read JSON from a tracked path, retaining parse/read failure separately."""
    try:
        return json.loads((root / path).read_text(encoding="utf-8")), True
    except (OSError, json.JSONDecodeError):
        return None, False
