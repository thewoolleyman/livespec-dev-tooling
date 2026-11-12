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
_PROCESS_COLUMNS: int = 4


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


def out_of_group_descendants(*, root_pid: int) -> tuple[tuple[int, str], ...]:
    """Find live descendants that escaped the suite's original process group."""
    children: dict[int, list[int]] = {}
    records = process_table()
    for pid, (parent, _, _) in records.items():
        children.setdefault(parent, []).append(pid)
    escapees: list[tuple[int, str]] = []
    frontier = [root_pid]
    while frontier:
        parent = frontier.pop()
        for pid in children.get(parent, []):
            _, group, command = records[pid]
            if group != root_pid:
                escapees.append((pid, command))
            frontier.append(pid)
    return tuple(escapees)


def is_alive(*, pid: int) -> bool:
    """Return whether `pid` still accepts signals from this runner."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def end_stalled_suite(
    *, proc: subprocess.Popen[bytes], report: Callable[[str], None] | None = None
) -> tuple[tuple[int, str], ...]:
    """End a stalled suite group and its session-escaping descendants."""
    escapees = out_of_group_descendants(root_pid=proc.pid)
    for pid, command in escapees:
        if not is_alive(pid=pid):
            continue
        if report is not None:
            report(f"suite-green: ending out-of-group descendant pid={pid} cmdline={command}\n")
        with contextlib.suppress(ProcessLookupError):
            os.kill(pid, signal.SIGTERM)
    with contextlib.suppress(ProcessLookupError):
        os.killpg(proc.pid, signal.SIGTERM)
    deadline = time.monotonic() + _KILL_GRACE_SECONDS
    while (proc.poll() is None or any(is_alive(pid=pid) for pid, _ in escapees)) and (
        time.monotonic() < deadline
    ):
        time.sleep(_POLL_SECONDS)
    with contextlib.suppress(ProcessLookupError):
        os.killpg(proc.pid, signal.SIGKILL)
    for pid, _ in escapees:
        if is_alive(pid=pid):
            with contextlib.suppress(ProcessLookupError):
                os.kill(pid, signal.SIGKILL)
    return escapees


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
                    _ = end_stalled_suite(proc=proc, report=lambda text: progress.saw(chunk=text))
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
