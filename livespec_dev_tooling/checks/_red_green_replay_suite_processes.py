"""Process-table reads for the suite-green replay runner."""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

__all__: list[str] = [
    "RUN_MARK_ENV",
    "StalledCleanupSettings",
    "StalledCleanupTools",
    "end_stalled_cleanup",
    "is_alive",
    "marked_pids",
    "process_table",
]

RUN_MARK_ENV: str = "LIVESPEC_SUITE_GREEN_RUN_MARK"
_PROCESS_COLUMNS: int = 4


class ProcessGroupLeader(Protocol):
    """The process-group operations a stalled-suite cleanup needs."""

    pid: int

    def poll(self) -> int | None:
        """Return the leader's completion code, when it has one."""


@dataclass(frozen=True, kw_only=True)
class StalledCleanupTools:
    """The process-attribution seams a cleanup pass calls."""

    find_descendants: Callable[..., tuple[tuple[int, str], ...]]
    is_pid_alive: Callable[..., bool]


@dataclass(frozen=True, kw_only=True)
class StalledCleanupSettings:
    """The finite signal budget and waits of one cleanup."""

    grace_seconds: int
    poll_seconds: float
    signal_passes: int


def process_table() -> dict[int, tuple[int, int, str]]:
    """Return PID-indexed parent, group and command records from the host process table."""
    try:
        listing = subprocess.run(
            args=["ps", "-axo", "pid=,ppid=,pgid=,command="],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return {}
    if listing.returncode != 0:
        return {}
    records: dict[int, tuple[int, int, str]] = {}
    for line in listing.stdout.splitlines():
        fields = line.split(maxsplit=3)
        if len(fields) != _PROCESS_COLUMNS:
            continue
        pid, parent, group, command = fields
        if pid.isdigit() and parent.isdigit() and group.isdigit():
            records[int(pid)] = (int(parent), int(group), command)
    return records


def marked_pids(*, mark: str, proc_root: Path = Path("/proc")) -> frozenset[int]:
    """Return the pids whose readable environment carries this run's mark."""
    try:
        entries = list(proc_root.iterdir())
    except OSError:
        return frozenset()
    marked: set[int] = set()
    for entry in entries:
        if not entry.name.isdigit():
            continue
        try:
            environment = (entry / "environ").read_bytes()
        except OSError:
            continue
        if f"{RUN_MARK_ENV}={mark}".encode() in environment.split(b"\0"):
            marked.add(int(entry.name))
    return frozenset(marked)


def is_alive(*, pid: int) -> bool:
    """Return whether `pid` still accepts signals from this runner."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        pass
    return True


def _attributed(
    *,
    proc: ProcessGroupLeader,
    mark: str,
    find_descendants: Callable[..., tuple[tuple[int, str], ...]],
    known: dict[int, str],
    unavailable: set[int],
) -> tuple[tuple[int, str], ...]:
    found = find_descendants(root_pid=proc.pid, mark=mark)
    for pid, command in found:
        _ = known.setdefault(pid, command)
    return tuple((pid, command) for pid, command in found if pid not in unavailable)


def _send_term(
    *,
    proc: ProcessGroupLeader,
    targets: tuple[tuple[int, str], ...],
    report: Callable[[str], None] | None,
    reported: set[int],
    unavailable: set[int],
) -> None:
    for pid, command in targets:
        if report is not None and pid not in reported:
            report(f"suite-green: ending out-of-group descendant pid={pid} cmdline={command}\n")
            reported.add(pid)
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            unavailable.add(pid)
    with contextlib.suppress(ProcessLookupError):
        os.killpg(proc.pid, signal.SIGTERM)


def _wait_for_exit(
    *,
    proc: ProcessGroupLeader,
    targets: tuple[tuple[int, str], ...],
    is_pid_alive: Callable[..., bool],
    grace_seconds: int,
    poll_seconds: float,
) -> None:
    deadline = time.monotonic() + grace_seconds
    while time.monotonic() < deadline and (
        proc.poll() is None or any(is_pid_alive(pid=pid) for pid, _ in targets)
    ):
        time.sleep(poll_seconds)


def _send_kill(
    *,
    proc: ProcessGroupLeader,
    targets: tuple[tuple[int, str], ...],
    verified: tuple[tuple[int, str], ...],
) -> None:
    term_pids = {pid for pid, _ in targets}
    for pid, _ in verified:
        if pid not in term_pids:
            continue
        with contextlib.suppress(ProcessLookupError):
            os.kill(pid, signal.SIGKILL)
    with contextlib.suppress(ProcessLookupError):
        os.killpg(proc.pid, signal.SIGKILL)


def end_stalled_cleanup(
    *,
    proc: ProcessGroupLeader,
    mark: str,
    report: Callable[[str], None] | None,
    tools: StalledCleanupTools,
    settings: StalledCleanupSettings,
) -> tuple[tuple[int, str], ...]:
    """End a suite's group and descendants in bounded, reattributed signal passes."""
    known: dict[int, str] = {}
    reported: set[int] = set()
    unavailable: set[int] = set()
    for _ in range(settings.signal_passes):
        targets = _attributed(
            proc=proc,
            mark=mark,
            find_descendants=tools.find_descendants,
            known=known,
            unavailable=unavailable,
        )
        _send_term(
            proc=proc,
            targets=targets,
            report=report,
            reported=reported,
            unavailable=unavailable,
        )
        _wait_for_exit(
            proc=proc,
            targets=targets,
            is_pid_alive=tools.is_pid_alive,
            grace_seconds=settings.grace_seconds,
            poll_seconds=settings.poll_seconds,
        )
        verified = _attributed(
            proc=proc,
            mark=mark,
            find_descendants=tools.find_descendants,
            known=known,
            unavailable=unavailable,
        )
        _send_kill(proc=proc, targets=targets, verified=verified)
    survivors = _attributed(
        proc=proc,
        mark=mark,
        find_descendants=tools.find_descendants,
        known=known,
        unavailable=unavailable,
    )
    deadline = time.monotonic() + settings.grace_seconds
    while survivors and time.monotonic() < deadline:
        time.sleep(settings.poll_seconds)
        survivors = _attributed(
            proc=proc,
            mark=mark,
            find_descendants=tools.find_descendants,
            known=known,
            unavailable=unavailable,
        )
    if report is not None:
        for pid, command in survivors:
            detail = f"suite-green: unended out-of-group descendant pid={pid} cmdline={command} "
            report(f"{detail}after {settings.signal_passes} signalling passes\n")
    return tuple(known.items())
