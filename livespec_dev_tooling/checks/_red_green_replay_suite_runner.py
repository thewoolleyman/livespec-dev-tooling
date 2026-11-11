"""Progress-bounded process-group runner for the suite-green replay leg."""

from __future__ import annotations

import codecs
import contextlib
import errno
import os
import pty
import re
import signal
import subprocess
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

__all__: list[str] = [
    "CEILING_ENV",
    "DEFAULT_STALL_SECONDS",
    "PROGRESS_STAMP_ENV",
    "STALL_ENV",
    "SuiteBound",
    "SuiteProgress",
    "SuiteRun",
    "kill_reason",
    "run_suite",
    "suite_bound",
    "test_completion_summary",
]

DEFAULT_STALL_SECONDS: int = 900
STALL_ENV: str = "LIVESPEC_SUITE_GREEN_STALL_SECONDS"
CEILING_ENV: str = "LIVESPEC_SUITE_GREEN_TIMEOUT_SECONDS"
# Exported by gate-run.sh to the gate's process tree; touching it renews the
# runner's outer stall window.
PROGRESS_STAMP_ENV: str = "LIVESPEC_GATE_RUN_PROGRESS_STAMP"
_POLL_SECONDS: float = 1.0
_KILL_GRACE_SECONDS: int = 30
_READ_BYTES: int = 65536
_FREEZE_ROUNDS: int = 50


@dataclass(frozen=True, kw_only=True)
class SuiteBound:
    """A progress stall window and an optional total run ceiling."""

    stall_seconds: int
    ceiling_seconds: int | None


@dataclass(frozen=True, kw_only=True)
class SuiteRun:
    """Outcome of one bounded suite run; `returncode` is None when killed."""

    returncode: int | None
    output: str
    timed_out: bool
    kill_reason: str | None = None


@dataclass(kw_only=True)
class SuiteProgress:
    """The suite output and the clock reading of its latest received chunk."""

    clock: Callable[[], float]
    last: float = field(init=False)
    chunks: list[str] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        self.last = self.clock()

    @property
    def output(self) -> str:
        """The output accumulated in arrival order."""
        return "".join(self.chunks)

    def saw(self, *, chunk: str) -> None:
        """Record received output and renew the stall window, and gate-run.sh's too.

        The leg captures pytest's output, so under the detached gate runner its
        output.log stays silent while the suite works; the runner's progress
        stamp is the only signal of that work it can see (livespec-dev-tooling-54usvh).
        """
        self.chunks.append(chunk)
        self.last = self.clock()
        stamp = os.environ.get(PROGRESS_STAMP_ENV, "")
        if stamp:
            Path(stamp).touch()


def _positive_seconds(*, raw: str) -> int | None:
    """Return a positive integer duration, or None for an invalid setting."""
    value = raw.strip()
    return int(value) if value.isdigit() and int(value) > 0 else None


def suite_bound(*, environ: Mapping[str, str]) -> SuiteBound:
    """Read the default stall bound and optional operator-supplied ceiling."""
    return SuiteBound(
        stall_seconds=_positive_seconds(raw=environ.get(STALL_ENV, "")) or DEFAULT_STALL_SECONDS,
        ceiling_seconds=_positive_seconds(raw=environ.get(CEILING_ENV, "")),
    )


def kill_reason(
    *, started: float, last_progress: float, now: float, bound: SuiteBound
) -> str | None:
    """Return the reached bound, with the operator ceiling taking precedence."""
    if bound.ceiling_seconds is not None and now - started >= bound.ceiling_seconds:
        return "ceiling"
    if now - last_progress >= bound.stall_seconds:
        return "stalled"
    return None


def test_completion_summary(*, output: str) -> str:
    """Describe whether pytest output records a completed test before a timeout."""
    plain = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", output)
    completed = re.search(
        r"(?:\[gw\d+\].*\b(?:PASSED|FAILED|SKIPPED|ERROR)\b|(?:^|[\r\n])[.FEsxXR]+(?:\s|$))",
        plain,
    )
    return "at least one test had completed" if completed else "no test had completed"


def _drain(*, fd: int, progress: SuiteProgress) -> None:
    """Record every output chunk until the suite's terminal stream closes."""
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    while True:
        try:
            chunk = os.read(fd, _READ_BYTES)
        except OSError as error:
            if error.errno == errno.EIO:
                break
            raise
        if not chunk:
            break
        progress.saw(chunk=decoder.decode(chunk))
    progress.saw(chunk=decoder.decode(b"", final=True))


def _process_table() -> tuple[tuple[int, int, int, str], ...]:
    """Return (pid, ppid, pgid, command) for every process.

    `ps -axww -o` is shared by the Linux and macOS developer hosts, and leaves
    the command line after the three numeric fields for the stall record.
    """
    snapshot = subprocess.run(
        ["ps", "-axww", "-o", "pid=", "-o", "ppid=", "-o", "pgid=", "-o", "command="],
        check=False,
        capture_output=True,
        text=True,
    )
    rows: list[tuple[int, int, int, str]] = []
    for line in snapshot.stdout.splitlines():
        with contextlib.suppress(ValueError):
            pid, parent_pid, process_group, command = line.split(maxsplit=3)
            rows.append((int(pid), int(parent_pid), int(process_group), command))
    return tuple(rows)


def _signal_tree(*, signal_number: int, leader_pid: int, escaped: dict[int, int]) -> None:
    """Signal the suite's group, each escaper, and each group an escaper leads."""
    targets = [(os.killpg, leader_pid), *((os.kill, pid) for pid in escaped)]
    targets += [(os.killpg, pid) for pid, group in escaped.items() if group == pid]
    for send, target in targets:
        with contextlib.suppress(ProcessLookupError):
            send(target, signal_number)


def _end_session_escapers(*, leader_pid: int, progress: SuiteProgress) -> None:
    """Freeze the suite's whole tree, then kill every descendant outside its group.

    A subprocess can start a session of its own and escape `killpg`, and the
    suite keeps forking while it is signalled, so any single snapshot of the
    process table is stale before the signal lands. The tree is stopped first
    and the table re-read until a round finds nothing new and the tree stopped
    changing: a stopped process forks nothing, and SIGKILL reaches it. A process
    belongs to the tree when its parent does, or when it sits in the process
    group an escaper leads (a reparented orphan of an escaper).
    """
    escaped: dict[int, int] = {}
    previous_size = -1
    for _ in range(_FREEZE_ROUNDS):  # pragma: no branch
        _signal_tree(signal_number=signal.SIGSTOP, leader_pid=leader_pid, escaped=escaped)
        rows = _process_table()
        tree = {leader_pid, *escaped}
        groups = {leader_pid, *(pid for pid, group in escaped.items() if group == pid)}
        grown = True
        while grown:
            members = {
                pid for pid, parent_pid, group, _ in rows if parent_pid in tree or group in groups
            }
            grown = not members <= tree
            tree |= members
        discovered = [
            row for row in rows if row[0] in tree and row[2] != leader_pid and row[0] not in escaped
        ]
        for pid, _, group, command in discovered:
            escaped[pid] = group
            progress.saw(
                chunk=(
                    "\nsuite-green: ending escaped descendant outside the suite process group: "
                    f"pid {pid} command {command}\n"
                )
            )
        if not discovered and len(tree) == previous_size:
            break
        previous_size = len(tree)
    _signal_tree(signal_number=signal.SIGKILL, leader_pid=leader_pid, escaped=escaped)


def run_suite(
    *,
    argv: list[str],
    bound: SuiteBound,
    clock: Callable[[], float] = time.monotonic,
    cwd: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> SuiteRun:
    """Run in a process group and kill it only for a stall or configured ceiling.

    `cwd` and `environ` place the child in another tree: `environ` is layered
    over this process's environment, so a caller names only what differs.

    Pytest emits collection and xdist-startup status only when its output is a
    terminal. Giving it a pseudo-terminal makes those lifecycle updates
    visible before the first completed test renews the stall window.
    """
    master_fd, slave_fd = pty.openpty()
    try:
        proc = subprocess.Popen(
            argv,
            stdout=slave_fd,
            stderr=slave_fd,
            cwd=cwd,
            env={**os.environ, "PYTHONUNBUFFERED": "1", **(environ or {})},
            start_new_session=True,
        )
    finally:
        os.close(slave_fd)
    try:
        progress = SuiteProgress(clock=clock)
        started = progress.last
        reader = threading.Thread(
            target=_drain,
            kwargs={"fd": master_fd, "progress": progress},
            daemon=True,
        )
        reader.start()
        reason: str | None = None
        while proc.poll() is None:
            try:
                _ = proc.wait(timeout=_POLL_SECONDS)
            except subprocess.TimeoutExpired:
                reason = kill_reason(
                    started=started,
                    last_progress=progress.last,
                    now=clock(),
                    bound=bound,
                )
                if reason is not None:
                    _end_session_escapers(leader_pid=proc.pid, progress=progress)
                    _ = os.killpg(proc.pid, signal.SIGKILL)
                    _ = proc.wait(timeout=_KILL_GRACE_SECONDS)
        reader.join(timeout=_KILL_GRACE_SECONDS)
        return SuiteRun(
            returncode=None if reason is not None else proc.returncode,
            output=progress.output,
            timed_out=reason is not None,
            kill_reason=reason,
        )
    finally:
        os.close(master_fd)
