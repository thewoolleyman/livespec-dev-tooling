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
- no running process names the session id anywhere in its cwd, an open file,
  a memory map, its command line or its environment (a substring match, so
  `cd <dir> && ...`, `<dir>:...` and `--resume <id>` all count);
- nothing under it has been modified for `MOVER_MIN_AGE_SECONDS`.

When processes exist but not one of their environments can be read, no session
can be proven dead, so the pass keeps every session (`liveness-scan-failed`).

The references are read again just before each move, because a session may
resume between the scan and the move. The move itself first renames the
directory to a staging name in the same /tmp directory (atomic), reads the
references once more, and only then copies it to disk, so a process that still
holds the directory is caught before any byte is copied. A staging directory a
crashed pass left behind is renamed back at the start of the next pass.

The pass runs as root, so it never follows a symlink: the RAM root, the disk
root, the source project directory and the destination project directory must
each be a real directory, and the first three must belong to the RAM root's
owner, or the move is refused. An existing destination project directory is
given the source project directory's owner and mode.

The pass does nothing when the kill switch file exists, or when
`/tmp/claude-1000` is already a mount point (the bind is live, so the scratch is
already on disk). `MOVER_APPLY=0` reports what it would move and moves nothing.
Every decision is one JSON line on stdout, which systemd keeps in the journal.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from claude_scratch_mover_scan import (
    References,
    is_referenced,
    newest_mtime,
    read_references,
    real_dir,
    restore_staging,
    session_dirs,
    why_kept,
)

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

_DEFAULTS = {
    "MOVER_RAM_ROOT": "/tmp/claude-1000",  # noqa: S108 -- the tmpfs path this pass empties
    "MOVER_DISK_ROOT": "/var/tmp/claude-1000",  # noqa: S108 -- the on-disk bind source
    "MOVER_PROC_ROOT": "/proc",
    "MOVER_KILL_SWITCH": "/etc/livespec/claude-scratch-mover.disabled",
    "MOVER_MIN_AGE_SECONDS": "7200",
    "MOVER_APPLY": "1",
}


@dataclass(frozen=True, kw_only=True)
class Config:
    """One pass's inputs, read from the environment."""

    ram_root: Path
    disk_root: Path
    proc_root: Path
    kill_switch: Path
    min_age_seconds: float
    apply: bool


def _conform(*, directory: Path, like: Path) -> None:
    """Give a real directory the owner and mode of another (both idempotent)."""
    want = like.lstat()
    os.chown(directory, want.st_uid, want.st_gid, follow_symlinks=False)
    directory.chmod(stat.S_IMODE(want.st_mode))


def _refusal(*, source: Path, destination: Path, staging: Path, owner_uid: int) -> str | None:
    """Why a move must not start, after readying the destination project; or None."""
    project = source.parent
    if not real_dir(path=project, uid=owner_uid):
        return "unsafe-source"
    if not os.path.lexists(destination.parent):
        destination.parent.mkdir()
    elif not real_dir(path=destination.parent, uid=None):
        return "unsafe-destination"
    _conform(directory=destination.parent, like=project)
    if os.path.lexists(destination):
        return "destination-exists"
    if os.path.lexists(staging):
        return "staging-exists"
    return None


def move(
    *,
    source: Path,
    ram_root: Path,
    disk_root: Path,
    owner_uid: int,
    references: Callable[[], References],
) -> tuple[str, str | None]:
    """Stage, re-check and move one session directory: (event, detail)."""
    destination = disk_root / source.parent.relative_to(ram_root) / source.name
    staging = source.parent / f".{source.name}.moving"
    refusal = _refusal(source=source, destination=destination, staging=staging, owner_uid=owner_uid)
    if refusal is not None:
        return "move-failed", refusal
    source.rename(staging)
    fresh = references()
    if (
        fresh.scan_failed
        or source.name in fresh.sessions
        or is_referenced(directory=source, references=fresh)
    ):
        staging.rename(source)
        return "kept", "referenced-after-staging"
    completed = subprocess.run(  # noqa: S603 -- fixed argv, no shell
        ["mv", "-n", "-T", "--", str(staging), str(destination)],  # noqa: S607 -- coreutils mv
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0 or staging.exists():
        if staging.exists() and not source.exists():
            staging.rename(source)
        return "move-failed", completed.stderr.strip() or "move-incomplete"
    return "moved", None


def _emit(**fields: object) -> None:
    _ = sys.stdout.write(json.dumps(fields, sort_keys=True) + "\n")
    sys.stdout.flush()


def _preflight(*, config: Config, is_mount: Callable[[str], bool]) -> int | None:
    """The exit code when this pass must not run, or None to go ahead."""
    stop: int | None = None
    if config.kill_switch.exists():
        _emit(event="disabled", kill_switch=str(config.kill_switch))
        stop = 0
    elif not config.ram_root.exists():
        _emit(event="nothing-to-move", reason="ram-root-absent", ram_root=str(config.ram_root))
        stop = 0
    elif not real_dir(path=config.ram_root, uid=None):
        _emit(event="refused", reason="ram-root-unsafe", ram_root=str(config.ram_root))
        stop = 1
    elif is_mount(str(config.ram_root)):
        _emit(event="nothing-to-move", reason="ram-root-is-mounted", ram_root=str(config.ram_root))
        stop = 0
    elif not real_dir(path=config.disk_root, uid=config.ram_root.lstat().st_uid):
        _emit(event="refused", reason="disk-root-unsafe", disk_root=str(config.disk_root))
        stop = 1
    return stop


def _decide(
    *,
    directory: Path,
    snapshot: References,
    references: Callable[[], References],
    now: Callable[[], float],
    min_age_seconds: float,
) -> str | None:
    """Keep-reason from the snapshot, then from a fresh read; None to move."""
    reason = why_kept(
        directory=directory, references=snapshot, now=now(), min_age_seconds=min_age_seconds
    )
    if reason is None:
        # Read the processes again right before acting: a session may have
        # resumed since the snapshot.
        reason = why_kept(
            directory=directory, references=references(), now=now(), min_age_seconds=min_age_seconds
        )
    return reason


def run(
    *,
    config: Config,
    references: Callable[[], References],
    now: Callable[[], float],
    is_mount: Callable[[str], bool],
) -> int:
    """One pass. Returns 0, or 1 when any move failed or the pass was refused."""
    stop = _preflight(config=config, is_mount=is_mount)
    if stop is not None:
        return stop
    owner_uid = config.ram_root.lstat().st_uid
    for restored in restore_staging(ram_root=config.ram_root):
        _emit(event="restored-staging", path=str(restored))
    failures = 0
    moved = 0
    snapshot = references()
    for directory in list(session_dirs(ram_root=config.ram_root)):
        reason = _decide(
            directory=directory,
            snapshot=snapshot,
            references=references,
            now=now,
            min_age_seconds=config.min_age_seconds,
        )
        if reason is not None:
            _emit(event="kept", path=str(directory), reason=reason)
            continue
        if not config.apply:
            _emit(event="would-move", path=str(directory))
            continue
        event, detail = move(
            source=directory,
            ram_root=config.ram_root,
            disk_root=config.disk_root,
            owner_uid=owner_uid,
            references=references,
        )
        if event == "moved":
            moved += 1
            _emit(event="moved", path=str(directory), to=str(config.disk_root))
        elif event == "kept":
            _emit(event="kept", path=str(directory), reason=detail)
        else:
            failures += 1
            _emit(event="move-failed", path=str(directory), error=detail)
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
