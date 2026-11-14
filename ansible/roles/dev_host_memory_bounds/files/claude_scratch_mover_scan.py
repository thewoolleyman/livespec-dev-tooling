"""Read-only helpers for the Claude scratch mover: process references and session scans.

Split out of `claude_scratch_mover.py` (role `dev_host_memory_bounds`) to keep
each file under the repository's file-size ceiling. Nothing here writes; the
mover's `move` and `run` act on what these report.
"""

from __future__ import annotations

import os
import re
import stat
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

__all__: list[str] = [
    "References",
    "is_referenced",
    "newest_mtime",
    "read_references",
    "real_dir",
    "restore_staging",
    "session_dirs",
    "why_kept",
]

_SESSION_NAME = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_SESSION_ENV = re.compile(rb"(?:^|\x00)CLAUDE_CODE_SESSION_ID=([0-9a-f-]+)")
_STAGING_NAME = re.compile(
    r"^\.([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\.moving$"
)
# A /proc/<pid>/maps line names a file in its sixth field.
_MAPS_FIELDS_WITH_PATH = 6


@dataclass(frozen=True, kw_only=True)
class References:
    """What the running processes point at: session ids and path strings."""

    sessions: frozenset[str]
    paths: frozenset[str]
    scan_failed: bool = False


def _read_or_none(*, path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except OSError:
        return None


def _read(*, path: Path) -> bytes:
    return _read_or_none(path=path) or b""


def _link(*, path: Path) -> str:
    try:
        return str(path.readlink())
    except OSError:
        return ""


def _fd_targets(*, process: Path) -> list[str]:
    try:
        names = os.listdir(process / "fd")
    except OSError:
        return []
    return [_link(path=process / "fd" / name) for name in names]


def _map_paths(*, process: Path) -> list[str]:
    lines = _read(path=process / "maps").decode(errors="replace").splitlines()
    return [
        parts[5]
        for parts in (line.split(None, 5) for line in lines)
        if len(parts) == _MAPS_FIELDS_WITH_PATH
    ]


def read_references(*, proc_root: Path) -> References:
    """Collect every session id and path string the running processes hold."""
    sessions: set[str] = set()
    paths: set[str] = set()
    seen = 0
    readable = 0
    for process in proc_root.iterdir():
        if not process.name.isdigit():
            continue
        seen += 1
        raw_environ = _read_or_none(path=process / "environ")
        readable += raw_environ is not None
        environ = raw_environ or b""
        sessions.update(match.decode() for match in _SESSION_ENV.findall(environ))
        paths.add(_link(path=process / "cwd"))
        paths.update(_fd_targets(process=process))
        paths.update(_map_paths(process=process))
        for raw in (environ, _read(path=process / "cmdline")):
            paths.update(raw.decode(errors="replace").split("\x00"))
    paths.discard("")
    return References(
        sessions=frozenset(sessions),
        paths=frozenset(paths),
        scan_failed=seen > 0 and readable == 0,
    )


def is_referenced(*, directory: Path, references: References) -> bool:
    """True when any held string names the session id, wherever it appears."""
    return any(directory.name in held for held in references.paths)


def real_dir(*, path: Path, uid: int | None) -> bool:
    """True for a real directory (never a symlink), owned by `uid` when given."""
    try:
        info = path.lstat()
    except OSError:
        return False
    return stat.S_ISDIR(info.st_mode) and (uid is None or info.st_uid == uid)


def newest_mtime(*, directory: Path) -> float:
    """The latest modification time of the directory or anything under it."""
    newest = directory.lstat().st_mtime
    for root, dirs, files in os.walk(directory):
        for name in (*dirs, *files):
            try:
                newest = max(newest, os.lstat(Path(root) / name).st_mtime)
            except OSError:
                continue
    return newest


def _projects(*, ram_root: Path) -> Iterator[Path]:
    for project in sorted(ram_root.iterdir()):
        if real_dir(path=project, uid=None):
            yield project


def restore_staging(*, ram_root: Path) -> list[Path]:
    """Rename back every staging directory a crashed pass left; return them."""
    restored: list[Path] = []
    for project in _projects(ram_root=ram_root):
        for entry in sorted(project.iterdir()):
            match = _STAGING_NAME.match(entry.name)
            if match and real_dir(path=entry, uid=None) and not (project / match[1]).exists():
                entry.rename(project / match[1])
                restored.append(project / match[1])
    return restored


def session_dirs(*, ram_root: Path) -> Iterator[Path]:
    """Every `<project>/<session-id>` directory, symlinks never followed."""
    for project in _projects(ram_root=ram_root):
        for session in sorted(project.iterdir()):
            if session.is_symlink() or not session.is_dir():
                continue
            if _SESSION_NAME.match(session.name):
                yield session


def why_kept(
    *, directory: Path, references: References, now: float, min_age_seconds: float
) -> str | None:
    """The reason a session directory must stay, or None when it may move."""
    if references.scan_failed:
        return "liveness-scan-failed"
    if directory.name in references.sessions:
        return "session-running"
    if is_referenced(directory=directory, references=references):
        return "referenced"
    if now - newest_mtime(directory=directory) < min_age_seconds:
        return "recently-modified"
    return None
