"""Discover the processes a stalled suite created outside its process group."""

from __future__ import annotations

import subprocess
from pathlib import Path

__all__: list[str] = [
    "RUN_MARK_ENV",
    "marked_pids",
    "out_of_group_descendants",
    "process_table",
]

RUN_MARK_ENV: str = "LIVESPEC_SUITE_GREEN_RUN_MARK"
_PROCESS_COLUMNS: int = 4


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


def out_of_group_descendants(*, root_pid: int, mark: str) -> tuple[tuple[int, str], ...]:
    """Find live processes of the run that escaped the suite's original process group."""
    children: dict[int, list[int]] = {}
    records = process_table()
    for pid, (parent, _, _) in records.items():
        children.setdefault(parent, []).append(pid)
    escapees: dict[int, str] = {}
    frontier = [root_pid]
    while frontier:
        parent = frontier.pop()
        for pid in children.get(parent, []):
            _, group, command = records[pid]
            if group != root_pid:
                escapees[pid] = command
            frontier.append(pid)
    for pid in sorted(marked_pids(mark=mark)):
        record = records.get(pid)
        if record is not None and record[1] != root_pid:
            _ = escapees.setdefault(pid, record[2])
    return tuple(escapees.items())
