"""Progress-bounded subprocess runner for the suite-green replay leg."""

from __future__ import annotations

import codecs
import os
import signal
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import IO, cast

__all__: list[str] = ["SuiteBound", "SuiteProgress", "SuiteRun", "kill_reason", "run_suite"]

_KILL_GRACE_SECONDS: int = 30
_POLL_SECONDS: float = 1.0
_READ_BYTES: int = 65_536


@dataclass(frozen=True, kw_only=True)
class SuiteRun:
    """Outcome of one bounded suite run; `returncode` is None when killed."""

    returncode: int | None
    output: str
    timed_out: bool
    kill_reason: str | None = None


@dataclass(frozen=True, kw_only=True)
class SuiteBound:
    """The progress stall window and optional wall-clock ceiling for a suite run."""

    stall_seconds: int
    ceiling_seconds: int | None


@dataclass(kw_only=True)
class SuiteProgress:
    """The suite output and monotonic timestamp of its latest output chunk."""

    clock: Callable[[], float]
    last: float = field(init=False)
    chunks: list[str] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        self.last = self.clock()

    @property
    def output(self) -> str:
        return "".join(self.chunks)

    def saw(self, *, chunk: str) -> None:
        self.chunks.append(chunk)
        self.last = self.clock()


def kill_reason(
    *, started: float, last_progress: float, now: float, bound: SuiteBound
) -> str | None:
    """Return the reached bound, giving an explicitly configured ceiling precedence."""
    if bound.ceiling_seconds is not None and now - started >= bound.ceiling_seconds:
        return "ceiling"
    if now - last_progress >= bound.stall_seconds:
        return "stalled"
    return None


def _drain(*, stream: IO[bytes], progress: SuiteProgress) -> None:
    """Record pipe output as it arrives, including a trailing partial code point."""
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    for chunk in iter(lambda: os.read(stream.fileno(), _READ_BYTES), b""):
        progress.saw(chunk=decoder.decode(chunk))
    tail = decoder.decode(b"", final=True)
    if tail:
        progress.saw(chunk=tail)


def run_suite(
    *, argv: list[str], bound: SuiteBound, clock: Callable[[], float] = time.monotonic
) -> SuiteRun:
    """Run `argv`; output progress resets its stall window and either bound kills its group."""
    with subprocess.Popen(
        argv,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
        start_new_session=True,
    ) as proc:
        stream = cast("IO[bytes]", proc.stdout)
        progress = SuiteProgress(clock=clock)
        started = progress.last
        reader = threading.Thread(
            target=_drain,
            kwargs={"stream": stream, "progress": progress},
            daemon=True,
        )
        reader.start()
        reason: str | None = None
        while reason is None:
            try:
                _ = proc.wait(timeout=_POLL_SECONDS)
                break
            except subprocess.TimeoutExpired:
                reason = kill_reason(
                    started=started,
                    last_progress=progress.last,
                    now=clock(),
                    bound=bound,
                )
        if reason is not None:
            os.killpg(proc.pid, signal.SIGKILL)
            _ = proc.wait(timeout=_KILL_GRACE_SECONDS)
        reader.join(timeout=_KILL_GRACE_SECONDS)
        return SuiteRun(
            returncode=None if reason is not None else proc.returncode,
            output=progress.output,
            timed_out=reason is not None,
            kill_reason=reason,
        )
