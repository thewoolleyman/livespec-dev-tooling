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
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from livespec_dev_tooling.checks._red_green_replay_process_cleanup import (
    out_of_group_descendants,
)

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
# Set by `run_suite` to a per-run value that the suite command and every process
# it starts inherit, so a stall can name a descendant that left the suite's
# ancestry by exiting its parent after starting a session of its own.
RUN_MARK_ENV: str = "LIVESPEC_SUITE_GREEN_RUN_MARK"
_POLL_SECONDS: float = 1.0
_KILL_GRACE_SECONDS: int = 30
_READ_BYTES: int = 65536


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


def is_alive(*, pid: int) -> bool:
    """Return whether `pid` is a runnable process this runner still needs to end."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        pass
    try:
        state = (
            (Path("/proc") / str(pid) / "stat")
            .read_text(encoding="utf-8")
            .rsplit(")", 1)[1]
            .lstrip()[0]
        )
    except (IndexError, OSError):
        return True
    return state != "Z"


def _live_escapees(*, proc: subprocess.Popen[bytes], mark: str) -> dict[int, str]:
    """Return the run's runnable processes that sit outside the suite's own group."""
    return {
        pid: command
        for pid, command in out_of_group_descendants(root_pid=proc.pid, mark=mark)
        if is_alive(pid=pid)
    }


def end_stalled_suite(
    *,
    proc: subprocess.Popen[bytes],
    mark: str,
    report: Callable[[str], None] | None = None,
) -> tuple[tuple[int, str], ...]:
    """End a stalled suite group and every process of the run outside it.

    An escapee can answer TERM by starting another process in a session of its
    own, so the run is rescanned until a scan finds nothing runnable left.
    """
    ended: dict[int, str] = {}

    def end_escapees(*, sig: signal.Signals) -> None:
        for pid, command in _live_escapees(proc=proc, mark=mark).items():
            first_sight = pid not in ended
            if first_sight:
                ended[pid] = command
                if report is not None:
                    report(
                        f"suite-green: ending out-of-group descendant pid={pid} cmdline={command}\n"
                    )
            if first_sight or sig is signal.SIGKILL:
                with contextlib.suppress(ProcessLookupError):
                    os.kill(pid, sig)

    end_escapees(sig=signal.SIGTERM)
    with contextlib.suppress(ProcessLookupError):
        os.killpg(proc.pid, signal.SIGTERM)
    deadline = time.monotonic() + _KILL_GRACE_SECONDS
    while time.monotonic() < deadline and (
        proc.poll() is None or any(is_alive(pid=pid) for pid in ended)
    ):
        time.sleep(0.1)
        end_escapees(sig=signal.SIGTERM)
    with contextlib.suppress(ProcessLookupError):
        os.killpg(proc.pid, signal.SIGKILL)
    deadline = time.monotonic() + _KILL_GRACE_SECONDS
    while True:
        end_escapees(sig=signal.SIGKILL)
        time.sleep(0.1)
        if not _live_escapees(proc=proc, mark=mark) or time.monotonic() >= deadline:
            break
    return tuple(ended.items())


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
    mark = uuid.uuid4().hex
    master_fd, slave_fd = pty.openpty()
    try:
        proc = subprocess.Popen(
            argv,
            stdout=slave_fd,
            stderr=slave_fd,
            cwd=cwd,
            env={
                **os.environ,
                "PYTHONUNBUFFERED": "1",
                **(environ or {}),
                RUN_MARK_ENV: mark,
            },
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
                    _ = end_stalled_suite(
                        proc=proc, mark=mark, report=lambda text: progress.saw(chunk=text)
                    )
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
