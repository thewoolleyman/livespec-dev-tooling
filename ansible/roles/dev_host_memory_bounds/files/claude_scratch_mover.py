"""Move dead Claude Code session scratch off the /tmp tmpfs onto disk.

Role `dev_host_memory_bounds` caps the /tmp tmpfs at 8G. Each Claude Code
session keeps its scratch under `/tmp/claude-1000/<project>/<session-id>/`,
which stays in RAM until the planned bind mount puts `/tmp/claude-1000` on disk
at the next reboot. Until then this pass, run by a timer, MOVES every session
directory that is provably dead to the same relative path under
`/var/tmp/claude-1000/`, which is where the bind will show it. It never deletes.

A session directory is moved only when ALL of these hold:

- its name is a session id;
- no running process carries that id in `CLAUDE_CODE_SESSION_ID`;
- no running process references the directory through its cwd, an open file,
  a memory map, its command line or its environment;
- nothing under it has been modified for `MOVER_MIN_AGE_SECONDS`.

The references are read again just before each move, because a session may
resume between the scan and the move.

The pass does nothing when the kill switch file exists, or when
`/tmp/claude-1000` is already a mount point (the bind is live, so the scratch is
already on disk). `MOVER_APPLY=0` reports what it would move and moves nothing.
Every decision is one JSON line on stdout, which systemd keeps in the journal.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path

__all__: list[str] = []

_SESSION_NAME = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_SESSION_ENV = re.compile(rb"(?:^|\x00)CLAUDE_CODE_SESSION_ID=([0-9a-f-]+)")
# A /proc/<pid>/maps line names a file in its sixth field.
_MAPS_FIELDS_WITH_PATH = 6

_DEFAULTS = {
    "MOVER_RAM_ROOT": "/tmp/claude-1000",  # noqa: S108 -- the tmpfs path this pass empties
    "MOVER_DISK_ROOT": "/var/tmp/claude-1000",  # noqa: S108 -- the on-disk bind source
    "MOVER_PROC_ROOT": "/proc",
    "MOVER_KILL_SWITCH": "/etc/livespec/claude-scratch-mover.disabled",
    "MOVER_MIN_AGE_SECONDS": "7200",
    "MOVER_APPLY": "1",
}


@dataclass(frozen=True, kw_only=True)
class References:
    """What the running processes point at: session ids and path strings."""

    sessions: frozenset[str]
    paths: frozenset[str]


@dataclass(frozen=True, kw_only=True)
class Config:
    """One pass's inputs, read from the environment."""

    ram_root: Path
    disk_root: Path
    proc_root: Path
    kill_switch: Path
    min_age_seconds: float
    apply: bool


def _read(*, path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError:
        return b""


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
    for process in proc_root.iterdir():
        if not process.name.isdigit():
            continue
        environ = _read(path=process / "environ")
        sessions.update(match.decode() for match in _SESSION_ENV.findall(environ))
        paths.add(_link(path=process / "cwd"))
        paths.update(_fd_targets(process=process))
        paths.update(_map_paths(process=process))
        for raw in (environ, _read(path=process / "cmdline")):
            paths.update(raw.decode(errors="replace").split("\x00"))
    paths.discard("")
    return References(sessions=frozenset(sessions), paths=frozenset(paths))


def is_referenced(*, directory: Path, references: References) -> bool:
    """True when a held path names the directory or anything under it."""
    pattern = re.compile(re.escape(str(directory)) + r"(?:/|$)")
    return any(pattern.search(path) for path in references.paths)


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


def session_dirs(*, ram_root: Path) -> Iterator[Path]:
    """Every `<project>/<session-id>` directory, symlinks never followed."""
    for project in sorted(ram_root.iterdir()):
        if project.is_symlink() or not project.is_dir():
            continue
        for session in sorted(project.iterdir()):
            if session.is_symlink() or not session.is_dir():
                continue
            if _SESSION_NAME.match(session.name):
                yield session


def why_kept(
    *, directory: Path, references: References, now: float, min_age_seconds: float
) -> str | None:
    """The reason a session directory must stay, or None when it may move."""
    if directory.name in references.sessions:
        return "session-running"
    if is_referenced(directory=directory, references=references):
        return "referenced"
    if now - newest_mtime(directory=directory) < min_age_seconds:
        return "recently-modified"
    return None


def move(*, source: Path, ram_root: Path, disk_root: Path) -> str | None:
    """Move one session directory under the disk root; return an error or None."""
    destination_parent = disk_root / source.parent.relative_to(ram_root)
    if (destination_parent / source.name).exists():
        return "destination-exists"
    if not destination_parent.exists():
        destination_parent.mkdir(parents=True)
        owner = source.parent.stat()
        os.chown(destination_parent, owner.st_uid, owner.st_gid)
        destination_parent.chmod(owner.st_mode & 0o7777)
    completed = subprocess.run(  # noqa: S603 -- fixed argv, no shell
        ["mv", "-n", "--", str(source), str(destination_parent) + "/"],  # noqa: S607 -- coreutils mv
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0 or source.exists():
        return completed.stderr.strip() or "source-still-present"
    return None


def _emit(**fields: object) -> None:
    _ = sys.stdout.write(json.dumps(fields, sort_keys=True) + "\n")
    sys.stdout.flush()


def run(
    *,
    config: Config,
    references: Callable[[], References],
    now: Callable[[], float],
    is_mount: Callable[[str], bool],
) -> int:
    """One pass. Returns 0, or 1 when any move failed."""
    if config.kill_switch.exists():
        _emit(event="disabled", kill_switch=str(config.kill_switch))
        return 0
    if not config.ram_root.is_dir():
        _emit(event="nothing-to-move", reason="ram-root-absent", ram_root=str(config.ram_root))
        return 0
    if is_mount(str(config.ram_root)):
        _emit(event="nothing-to-move", reason="ram-root-is-mounted", ram_root=str(config.ram_root))
        return 0
    failures = 0
    moved = 0
    snapshot = references()
    for directory in list(session_dirs(ram_root=config.ram_root)):
        reason = why_kept(
            directory=directory,
            references=snapshot,
            now=now(),
            min_age_seconds=config.min_age_seconds,
        )
        if reason is None:
            # Read the processes again right before acting: a session may have
            # resumed since the snapshot.
            reason = why_kept(
                directory=directory,
                references=references(),
                now=now(),
                min_age_seconds=config.min_age_seconds,
            )
        if reason is not None:
            _emit(event="kept", path=str(directory), reason=reason)
            continue
        if not config.apply:
            _emit(event="would-move", path=str(directory))
            continue
        error = move(source=directory, ram_root=config.ram_root, disk_root=config.disk_root)
        if error is None:
            moved += 1
            _emit(event="moved", path=str(directory), to=str(config.disk_root))
        else:
            failures += 1
            _emit(event="move-failed", path=str(directory), error=error)
    _emit(event="pass-complete", moved=moved, failed=failures, apply=config.apply)
    return 1 if failures else 0


def config_from(*, environ: Mapping[str, str]) -> Config:
    """Read the pass's inputs, each defaulting to the production value."""
    value = {key: environ.get(key, default) for key, default in _DEFAULTS.items()}
    return Config(
        ram_root=Path(value["MOVER_RAM_ROOT"]),
        disk_root=Path(value["MOVER_DISK_ROOT"]),
        proc_root=Path(value["MOVER_PROC_ROOT"]),
        kill_switch=Path(value["MOVER_KILL_SWITCH"]),
        min_age_seconds=float(value["MOVER_MIN_AGE_SECONDS"]),
        apply=value["MOVER_APPLY"] == "1",
    )


def main(*, environ: Mapping[str, str]) -> int:
    config = config_from(environ=environ)
    return run(
        config=config,
        references=lambda: read_references(proc_root=config.proc_root),
        now=time.time,
        is_mount=os.path.ismount,
    )


if __name__ == "__main__":
    sys.exit(main(environ=os.environ))
