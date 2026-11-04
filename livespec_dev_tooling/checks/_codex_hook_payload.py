"""Validate one Codex hooks declaration for the hook-cache reconciliation check.

Private sibling of `codex_hook_reconcilable`. It owns the hooks-file concern:
the shape of the `hooks` object, each matcher group and entry, and each
command's reconciler-preservable `${CLAUDE_PLUGIN_ROOT}/` entrypoint. Its one
public entry point is `check_hooks_file`; discovery of manifests and hooks
files stays in the parent.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import cast

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

from livespec_dev_tooling.checks._codex_hook_support import (  # noqa: E402
    emit_failure,
    payload_contains,
    read_json,
    relative_path,
)

__all__: list[str] = [
    "check_hooks_file",
]


_ROOT_TOKEN = "CLAUDE_PLUGIN_ROOT"
_ENTRYPOINT = re.compile(r"\$\{CLAUDE_PLUGIN_ROOT\}/([^\s'\";|&]*)")


@dataclass(frozen=True, kw_only=True)
class _HookContext:
    """The immutable repository and declaration context for one hook command."""

    root: Path
    tracked: frozenset[str]
    plugin_root: str
    manifest: str
    hooks_path: str
    log: structlog.stdlib.BoundLogger


def _check_command(*, context: _HookContext, event: str, command: str) -> int:
    """Validate one command's reconciler-preservable entrypoint shape."""
    if _ROOT_TOKEN not in command:
        return 0
    match = _ENTRYPOINT.search(command)
    if match is None:
        emit_failure(
            log=context.log,
            failure_mode="no_plugin_root_path",
            manifest=context.manifest,
            path=context.hooks_path,
            event=event,
            command=command,
            message=(
                f"Codex plugin manifest {context.manifest} hook event {event} uses "
                "CLAUDE_PLUGIN_ROOT without a braced plugin-root path"
            ),
            hint=(
                "root the hook entrypoint at ${CLAUDE_PLUGIN_ROOT}/ so the reconciler "
                "can preserve it"
            ),
        )
        return 1
    entrypoint = relative_path(plugin_root=context.plugin_root, declared_path=match.group(1))
    if payload_contains(
        tracked=context.tracked,
        plugin_root=context.plugin_root,
        path=entrypoint,
        root=context.root,
    ):
        return 0
    emit_failure(
        log=context.log,
        failure_mode="entrypoint_missing",
        manifest=context.manifest,
        path=context.hooks_path,
        event=event,
        command=command,
        entrypoint=entrypoint,
        message=(
            f"Codex plugin manifest {context.manifest} hook event {event} command "
            f"{command!r} names missing payload entrypoint {entrypoint}"
        ),
        hint="ship the named file in the plugin payload or correct the path",
    )
    return 1


def _check_group(*, context: _HookContext, event: str, group: object) -> tuple[int, int]:
    """Validate a matcher group and its command-bearing entries."""
    if not isinstance(group, dict):
        emit_failure(
            log=context.log,
            failure_mode="malformed_hooks_file",
            manifest=context.manifest,
            path=context.hooks_path,
            message=f"Codex hooks file {context.hooks_path} has a malformed matcher group",
            hint="repair the named file",
        )
        return 1, 0
    entries = cast("dict[str, object]", group).get("hooks")
    if not isinstance(entries, list):
        emit_failure(
            log=context.log,
            failure_mode="malformed_hooks_file",
            manifest=context.manifest,
            path=context.hooks_path,
            message=f"Codex hooks file {context.hooks_path} has a malformed matcher group",
            hint="repair the named file",
        )
        return 1, 0
    failures = 0
    commands = 0
    for entry in cast("list[object]", entries):
        if not isinstance(entry, dict):
            emit_failure(
                log=context.log,
                failure_mode="malformed_hooks_file",
                manifest=context.manifest,
                path=context.hooks_path,
                message=f"Codex hooks file {context.hooks_path} has a non-object hook entry",
                hint="repair the named file",
            )
            failures += 1
            continue
        command = cast("dict[str, object]", entry).get("command")
        if isinstance(command, str):
            commands += 1
            failures += _check_command(context=context, event=event, command=command)
    return failures, commands


def check_hooks_file(
    *,
    root: Path,
    tracked: frozenset[str],
    manifest: str,
    hooks_path: str,
    log: structlog.stdlib.BoundLogger,
) -> tuple[int, int]:
    """Validate one hooks declaration and every command it carries."""
    document, parsed = read_json(root=root, path=hooks_path)
    if not parsed:
        emit_failure(
            log=log,
            failure_mode="unparseable_hooks_file",
            manifest=manifest,
            path=hooks_path,
            message=f"Codex hooks file {hooks_path} cannot be parsed as JSON",
            hint="repair the named file",
        )
        return 1, 0
    if not isinstance(document, dict):
        emit_failure(
            log=log,
            failure_mode="malformed_hooks_file",
            manifest=manifest,
            path=hooks_path,
            message=f"Codex hooks file {hooks_path} has no hooks object",
            hint="repair the named file",
        )
        return 1, 0
    hooks = cast("dict[str, object]", document).get("hooks")
    if not isinstance(hooks, dict):
        emit_failure(
            log=log,
            failure_mode="malformed_hooks_file",
            manifest=manifest,
            path=hooks_path,
            message=f"Codex hooks file {hooks_path} has no hooks object",
            hint="repair the named file",
        )
        return 1, 0
    context = _HookContext(
        root=root,
        tracked=tracked,
        plugin_root=Path(manifest).parent.parent.as_posix(),
        manifest=manifest,
        hooks_path=hooks_path,
        log=log,
    )
    failures = 0
    commands = 0
    for event, groups in cast("dict[str, object]", hooks).items():
        if not isinstance(groups, list):
            emit_failure(
                log=log,
                failure_mode="malformed_hooks_file",
                manifest=manifest,
                path=hooks_path,
                message=f"Codex hooks file {hooks_path} has non-list event {event}",
                hint="repair the named file",
            )
            failures += 1
            continue
        for group in cast("list[object]", groups):
            group_failures, group_commands = _check_group(context=context, event=event, group=group)
            failures += group_failures
            commands += group_commands
    return failures, commands
