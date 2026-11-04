"""Reject Codex plugin hooks the hook-cache reconciler cannot preserve."""

from __future__ import annotations

import json
import posixpath
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import cast

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

__all__: list[str] = []

CHECK_PURITY = "tree-pure"


_CHECK_ID = "codex_hook_reconcilable"
_FAIL_EXIT = 4
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


def _logger() -> structlog.stdlib.BoundLogger:
    """Build the structured stderr logger used by this check."""
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.EventRenamer(to="message", replace_by="hook_event"),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    return structlog.get_logger(_CHECK_ID)


def _tracked_tree(*, log: structlog.stdlib.BoundLogger) -> tuple[Path, frozenset[str]] | None:
    """Return the Git root plus tracked paths, or emit a graceful skip."""
    try:
        root = subprocess.run(
            ("git", "rev-parse", "--show-toplevel"), capture_output=True, check=False, text=True
        )
    except OSError:
        log.warning(
            "Codex hook reconciliation check skipped: git is unavailable", check_id=_CHECK_ID
        )
        return None
    if root.returncode != 0:
        log.info(
            "Codex hook reconciliation check skipped: not inside a Git working tree",
            check_id=_CHECK_ID,
        )
        return None
    try:
        paths = subprocess.run(
            ("git", "ls-files", "-z"),
            cwd=root.stdout.strip(),
            capture_output=True,
            check=False,
            text=True,
        )
    except OSError:
        log.warning(
            "Codex hook reconciliation check skipped: git is unavailable", check_id=_CHECK_ID
        )
        return None
    if paths.returncode != 0:
        log.warning(
            "Codex hook reconciliation check skipped: Git could not list tracked files",
            check_id=_CHECK_ID,
        )
        return None
    return Path(root.stdout.strip()), frozenset(filter(None, paths.stdout.split("\0")))


def _manifests(*, tracked: frozenset[str]) -> tuple[str, ...]:
    """Find every tracked manifest directly below a `.codex-plugin` directory."""
    return tuple(
        sorted(
            path
            for path in tracked
            if Path(path).name == "plugin.json" and Path(path).parent.name == ".codex-plugin"
        )
    )


def _relative_path(*, plugin_root: str, declared_path: str) -> str:
    """Resolve a plugin-relative declaration to a normalized repository path."""
    return posixpath.normpath(posixpath.join(plugin_root, declared_path))


def _payload_contains(*, tracked: frozenset[str], plugin_root: str, path: str, root: Path) -> bool:
    """Return whether `path` is a tracked regular file inside `plugin_root`."""
    prefix = f"{plugin_root}/" if plugin_root != "." else ""
    return path.startswith(prefix) and path in tracked and (root / path).is_file()


def _fail(
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
        check_id=_CHECK_ID,
        status="fail",
        hook_event=event,
        command=command,
        entrypoint=entrypoint,
        line=0,
        **finding,
    )


def _read_json(*, root: Path, path: str) -> tuple[object | None, bool]:
    """Read JSON from a tracked path, retaining parse/read failure separately."""
    try:
        return json.loads((root / path).read_text(encoding="utf-8")), True
    except (OSError, json.JSONDecodeError):
        return None, False


def _hooks_paths(
    *, root: Path, tracked: frozenset[str], manifest: str, log: structlog.stdlib.BoundLogger
) -> tuple[tuple[str, ...], int]:
    """Locate declared and default hooks files, reporting invalid manifests."""
    plugin_root = Path(manifest).parent.parent.as_posix()
    document, parsed = _read_json(root=root, path=manifest)
    failures = 0
    paths: set[str] = set()
    if not parsed:
        failures += 1
        _fail(
            log=log,
            failure_mode="unparseable_manifest",
            manifest=manifest,
            path=manifest,
            message=f"Codex plugin manifest {manifest} cannot be parsed as JSON",
            hint="repair the named manifest",
        )
    elif not isinstance(document, dict):
        failures += 1
        _fail(
            log=log,
            failure_mode="malformed_manifest",
            manifest=manifest,
            path=manifest,
            message=f"Codex plugin manifest {manifest} is not a JSON object",
            hint="repair the named manifest",
        )
    else:
        hooks_value = cast("dict[str, object]", document).get("hooks")
        if hooks_value is not None:
            if not isinstance(hooks_value, str) or not hooks_value:
                failures += 1
                _fail(
                    log=log,
                    failure_mode="malformed_manifest",
                    manifest=manifest,
                    path=manifest,
                    message=f"Codex plugin manifest {manifest} has a malformed hooks entry",
                    hint="repair the named manifest",
                )
            else:
                declared = _relative_path(plugin_root=plugin_root, declared_path=hooks_value)
                if _payload_contains(
                    tracked=tracked, plugin_root=plugin_root, path=declared, root=root
                ):
                    paths.add(declared)
                else:
                    failures += 1
                    _fail(
                        log=log,
                        failure_mode="hooks_file_missing",
                        manifest=manifest,
                        path=manifest,
                        entrypoint=declared,
                        message=(
                            f"Codex plugin manifest {manifest} names missing hooks file "
                            f"{declared}"
                        ),
                        hint="ship the named file in the plugin payload or correct the path",
                    )
    default = _relative_path(plugin_root=plugin_root, declared_path="hooks/hooks.json")
    if _payload_contains(tracked=tracked, plugin_root=plugin_root, path=default, root=root):
        paths.add(default)
    return tuple(sorted(paths)), failures


def _check_command(*, context: _HookContext, event: str, command: str) -> int:
    """Validate one command's reconciler-preservable entrypoint shape."""
    if _ROOT_TOKEN not in command:
        return 0
    match = _ENTRYPOINT.search(command)
    if match is None:
        _fail(
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
    entrypoint = _relative_path(plugin_root=context.plugin_root, declared_path=match.group(1))
    if _payload_contains(
        tracked=context.tracked,
        plugin_root=context.plugin_root,
        path=entrypoint,
        root=context.root,
    ):
        return 0
    _fail(
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
        _fail(
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
        _fail(
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
            _fail(
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


def _check_hooks_file(
    *,
    root: Path,
    tracked: frozenset[str],
    manifest: str,
    hooks_path: str,
    log: structlog.stdlib.BoundLogger,
) -> tuple[int, int]:
    """Validate one hooks declaration and every command it carries."""
    document, parsed = _read_json(root=root, path=hooks_path)
    if not parsed:
        _fail(
            log=log,
            failure_mode="unparseable_hooks_file",
            manifest=manifest,
            path=hooks_path,
            message=f"Codex hooks file {hooks_path} cannot be parsed as JSON",
            hint="repair the named file",
        )
        return 1, 0
    if not isinstance(document, dict):
        _fail(
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
        _fail(
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
            _fail(
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


def main() -> int:
    """Fail a release whose tracked Codex hooks cannot be reconciled safely."""
    log = _logger()
    tree = _tracked_tree(log=log)
    if tree is None:
        return 0
    root, tracked = tree
    manifests = _manifests(tracked=tracked)
    failures = 0
    commands_checked = 0
    for manifest in manifests:
        hooks_paths, manifest_failures = _hooks_paths(
            root=root, tracked=tracked, manifest=manifest, log=log
        )
        failures += manifest_failures
        for hooks_path in hooks_paths:
            hooks_failures, hooks_commands = _check_hooks_file(
                root=root, tracked=tracked, manifest=manifest, hooks_path=hooks_path, log=log
            )
            failures += hooks_failures
            commands_checked += hooks_commands
    if failures:
        return _FAIL_EXIT
    log.info(
        "Codex hook reconciliation check passed"
        if manifests
        else "repository ships no Codex plugin hooks",
        check_id=_CHECK_ID,
        manifests_checked=len(manifests),
        commands_checked=commands_checked,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
