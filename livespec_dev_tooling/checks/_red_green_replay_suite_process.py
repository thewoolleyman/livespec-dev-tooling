"""Progress-bounded subprocess execution for the suite-green replay leg.

The suite runs in its own process group so a stalled pytest invocation can
kill every xdist worker with its leader. Output is read as it arrives: every
chunk restarts the stall window, while an optional ceiling remains absolute.
"""

from __future__ import annotations

import codecs
import os
import selectors
import signal
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import IO, cast

__all__: list[str] = [
    "SuiteBound",
    "SuiteProgress",
    "SuiteRun",
    "kill_reason",
    "run_suite",
]

_KILL_GRACE_SECONDS: int = 30
_POLL_SECONDS: float = 1.0
_READ_BYTES: int = 65536


@dataclass(frozen=True, kw_only=True)
class SuiteRun:
    """Outcome of one bounded suite run; `returncode` is None when it was killed."""

    returncode: int | None
    output: str
    timed_out: bool
    kill_reason: str | None = None


@dataclass(frozen=True, kw_only=True)
class SuiteBound:
    """How long a suite may run: a stall window and optional total ceiling."""

    stall_seconds: int
    ceiling_seconds: int | None


@dataclass(kw_only=True)
class SuiteProgress:
    """The suite output so far, plus the instant at which its last chunk arrived."""

    clock: Callable[[], float]
    last: float = field(init=False)
    chunks: list[str] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        self.last = self.clock()

    @property
    def output(self) -> str:
        """Return all output received from the suite."""
        return "".join(self.chunks)

    def saw(self, *, chunk: str) -> None:
        """Record a chunk and restart the stall window, even for partial UTF-8."""
        self.chunks.append(chunk)
        self.last = self.clock()


def kill_reason(
    *, started: float, last_progress: float, now: float, bound: SuiteBound
) -> str | None:
    """Name the bound ending a run at `now`, if either bound has elapsed."""
    if bound.ceiling_seconds is not None and now - started >= bound.ceiling_seconds:
        return "ceiling"
    if now - last_progress >= bound.stall_seconds:
        return "stalled"
    return None


def _drain_available(
    *, stream: IO[bytes], decoder: codecs.IncrementalDecoder, progress: SuiteProgress
) -> bool:
    """Read one available pipe chunk; return False at EOF, which is not progress."""
    chunk = os.read(stream.fileno(), _READ_BYTES)
    if not chunk:
        return False
    progress.saw(chunk=decoder.decode(chunk))
    return True


def _drain_after_exit(
    *, stream: IO[bytes], decoder: codecs.IncrementalDecoder, progress: SuiteProgress
) -> None:
    """Drain the closed pipe, retaining a decoder's final partial character."""
    for chunk in iter(lambda: os.read(stream.fileno(), _READ_BYTES), b""):
        progress.saw(chunk=decoder.decode(chunk))
    trailing = decoder.decode(b"", final=True)
    if trailing:
        progress.saw(chunk=trailing)


def run_suite(
    *, argv: list[str], bound: SuiteBound, clock: Callable[[], float] = time.monotonic
) -> SuiteRun:
    """Run `argv` in its own process group and kill that group at either bound."""
    with subprocess.Popen(
        argv,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
        start_new_session=True,
    ) as proc:
        stream = cast("IO[bytes]", proc.stdout)
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        progress = SuiteProgress(clock=clock)
        started = progress.last
        reason: str | None = None
        with selectors.DefaultSelector() as selector:
            _ = selector.register(stream, selectors.EVENT_READ)
            while proc.poll() is None:
                reason = kill_reason(
                    started=started,
                    last_progress=progress.last,
                    now=clock(),
                    bound=bound,
                )
                if reason is not None:
                    os.killpg(proc.pid, signal.SIGKILL)
                    _ = proc.wait(timeout=_KILL_GRACE_SECONDS)
                    break
                for _key, _mask in selector.select(timeout=_POLL_SECONDS):
                    if not _drain_available(stream=stream, decoder=decoder, progress=progress):
                        _ = selector.unregister(stream)
        _drain_after_exit(stream=stream, decoder=decoder, progress=progress)
        return SuiteRun(
            returncode=None if reason is not None else proc.returncode,
            output=progress.output,
            timed_out=reason is not None,
            kill_reason=reason,
        )
