"""Reject Codex plugin hooks the hook-cache reconciler cannot preserve."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import cast

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

from livespec_dev_tooling.checks._codex_hook_payload import check_hooks_file  # noqa: E402
from livespec_dev_tooling.checks._codex_hook_support import (  # noqa: E402
    CHECK_ID,
    emit_failure,
    payload_contains,
    read_json,
    relative_path,
)

__all__: list[str] = []

CHECK_PURITY = "tree-pure"


_FAIL_EXIT = 4


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
    return structlog.get_logger(CHECK_ID)


def _tracked_tree(*, log: structlog.stdlib.BoundLogger) -> tuple[Path, frozenset[str]] | None:
    """Return the Git root plus tracked paths, or emit a graceful skip."""
    try:
        root = subprocess.run(
            ("git", "rev-parse", "--show-toplevel"), capture_output=True, check=False, text=True
        )
    except OSError:
        log.warning(
            "Codex hook reconciliation check skipped: git is unavailable", check_id=CHECK_ID
        )
        return None
    if root.returncode != 0:
        log.info(
            "Codex hook reconciliation check skipped: not inside a Git working tree",
            check_id=CHECK_ID,
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
            "Codex hook reconciliation check skipped: git is unavailable", check_id=CHECK_ID
        )
        return None
    if paths.returncode != 0:
        log.warning(
            "Codex hook reconciliation check skipped: Git could not list tracked files",
            check_id=CHECK_ID,
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


def _hooks_paths(
    *, root: Path, tracked: frozenset[str], manifest: str, log: structlog.stdlib.BoundLogger
) -> tuple[tuple[str, ...], int]:
    """Locate declared and default hooks files, reporting invalid manifests."""
    plugin_root = Path(manifest).parent.parent.as_posix()
    document, parsed = read_json(root=root, path=manifest)
    failures = 0
    paths: set[str] = set()
    if not parsed:
        failures += 1
        emit_failure(
            log=log,
            failure_mode="unparseable_manifest",
            manifest=manifest,
            path=manifest,
            message=f"Codex plugin manifest {manifest} cannot be parsed as JSON",
            hint="repair the named manifest",
        )
    elif not isinstance(document, dict):
        failures += 1
        emit_failure(
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
                emit_failure(
                    log=log,
                    failure_mode="malformed_manifest",
                    manifest=manifest,
                    path=manifest,
                    message=f"Codex plugin manifest {manifest} has a malformed hooks entry",
                    hint="repair the named manifest",
                )
            else:
                declared = relative_path(plugin_root=plugin_root, declared_path=hooks_value)
                if payload_contains(
                    tracked=tracked, plugin_root=plugin_root, path=declared, root=root
                ):
                    paths.add(declared)
                else:
                    failures += 1
                    emit_failure(
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
    default = relative_path(plugin_root=plugin_root, declared_path="hooks/hooks.json")
    if payload_contains(tracked=tracked, plugin_root=plugin_root, path=default, root=root):
        paths.add(default)
    return tuple(sorted(paths)), failures


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
            hooks_failures, hooks_commands = check_hooks_file(
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
        check_id=CHECK_ID,
        manifests_checked=len(manifests),
        commands_checked=commands_checked,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
