"""Tests for the dpkg frontend lock the Docker engine install guard's role holds.

Governing specification: `SPECIFICATION/non-functional-requirements.md`
section "Docker engine install guard", "Package fence". Governing design:
`docs/docker-engine-guard-design.md`, Mechanism 5's fence as amended by
R6 and F6: the package step runs with `DPKG_FRONTEND_LOCKED=1` and so
assumes the frontend lock is ALREADY HELD, by a helper whose lifetime
systemd owns rather than the controller's SSH session.

Nothing here touches a real host: the lock file is a path under
`tmp_path`, the clock is injected, and the signal is sent by this
process to its own thread. Two things ARE real, because a fake of
either would prove nothing about the only thing this helper does -- the
record lock, and the second process the refusal is measured against.
"""

from __future__ import annotations

import fcntl
import importlib
import os
import signal
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

__all__: list[str] = []

_APTLOCK_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_aptlock"
_APTLOCK_PATH = Path("livespec_dev_tooling/fleet/_docker_engine_guard_aptlock.py")


@dataclass(kw_only=True)
class _FakeClock:
    """An injected monotonic clock whose only motion is its own sleep.

    The bounded wait is the whole of the refusal below, so it is driven
    by a clock a test advances rather than by real time: a wait proven
    with `time.sleep` is a wait nobody can prove the bound of.
    """

    now: float = 0.0
    slept: list[float] = field(default_factory=list)

    def monotonic(self) -> float:
        """The current instant, which only `sleep` moves."""
        return self.now

    def sleep(self, *, seconds: float) -> None:
        """Advance the clock by `seconds`, recording the wait."""
        self.slept.append(seconds)
        self.now += seconds


def _aptlock() -> Any:
    """The helper module, asserted to be on disk before it is imported.

    The file check comes first on purpose: at Red the module does not
    exist, and a bare top-level import would make the Red a collection
    error that proves only unimportability.
    """
    assert _APTLOCK_PATH.is_file()
    return importlib.import_module(_APTLOCK_MODULE)


def test_the_frontend_lock_helper_publishes_its_pid_and_holds_until_sigterm(
    tmp_path: Path,
) -> None:
    """Design F6: the lock-holding helper, with a lifetime systemd owns.

    The role needs three things of it and this drives all three. It takes
    a POSIX RECORD lock, which is the kind dpkg itself takes — an
    `flock` would be granted alongside dpkg's lock rather than against
    it, so the helper would report holding a fence it did not hold. It
    publishes its PID where the role can read it, which is how the role
    ends the hold at all: the helper is started detached, so the PID is
    not something its caller already knows. And it holds the lock until
    SIGTERM arrives, then removes the ready file BEFORE releasing — a
    role that saw the file still there would believe the fence was still
    up.

    The real signal path runs in-process: SIGTERM is BLOCKED and then
    sent, so it is already PENDING when the hold waits for it and the
    wait returns at once. That is also why the helper waits for the
    signal rather than handling it — a blocked signal cannot be lost
    between the ready file appearing and the wait starting.

    It is sent to this THREAD with `pthread_kill` and never to the
    process with `os.kill`, which is measured rather than fastidious: a
    mask blocks a signal in the calling thread only, so a
    process-directed SIGTERM is delivered to whichever thread has not
    blocked it. Under the parallel test runner that is the worker's own
    execnet receiver thread, and the worker dies mid-run — which
    presents as a coverage report with missing workers rather than as a
    failing assertion.
    """
    aptlock = _aptlock()
    lock = tmp_path / "lock-frontend"
    ready = tmp_path / "aptlock.pid"
    published: list[str] = []
    clock = _FakeClock()

    held = aptlock.hold_frontend_lock(
        lock_file=lock,
        ready_file=ready,
        wait_seconds=30,
        clock=clock,
        await_termination=lambda: published.append(ready.read_text(encoding="utf-8")),
    )

    assert held == ""
    assert published == [str(os.getpid())]
    assert not ready.exists()
    assert clock.slept == []

    previous = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGTERM})
    try:
        signal.pthread_kill(threading.get_ident(), signal.SIGTERM)
        signalled = aptlock.hold_frontend_lock(
            lock_file=lock, ready_file=ready, wait_seconds=30, clock=clock
        )
    finally:
        _ = signal.pthread_sigmask(signal.SIG_SETMASK, previous)

    assert signalled == ""
    assert not ready.exists()
    assert str(aptlock.DEFAULT_LOCK_FILE) == "/var/lib/dpkg/lock-frontend"


@dataclass(kw_only=True)
class _Holder:
    """A real SECOND process holding the real record lock on the lock file."""

    pid: int
    release: int

    def stop(self) -> None:
        """Let the holder go, and reap it."""
        _ = os.write(self.release, b"go")
        _ = os.waitpid(self.pid, 0)


def _hold(*, lock: Path) -> _Holder:
    """Fork a process that takes the record lock and waits to be released.

    A second process is the only way to create the contention the
    refusal exists for: POSIX record locks are owned by a PROCESS, so a
    second `lockf` from THIS one would be GRANTED and would prove
    nothing. It is FORKED rather than spawned because no command-line
    tool takes a record lock -- `flock(1)` takes the other kind, which
    does not conflict with this one at all -- and it leaves through
    `os._exit`, so neither a pytest teardown nor a coverage write ever
    runs in it and nothing races the parallel runner's data file.
    """
    holding_read, holding_write = os.pipe()
    release_read, release_write = os.pipe()
    pid = os.fork()
    if pid == 0:  # pragma: no cover — the forked child, which reports to nobody
        held = os.open(lock, os.O_CREAT | os.O_RDWR, 0o660)
        fcntl.lockf(held, fcntl.LOCK_EX)
        _ = os.write(holding_write, b"held")
        _ = os.read(release_read, 2)
        os._exit(0)
    assert os.read(holding_read, 4) == b"held"
    return _Holder(pid=pid, release=release_write)


def test_the_frontend_lock_helper_refuses_and_names_a_lock_another_process_holds(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Design F6: a fence that was never taken is a REFUSAL, never a silent pass.

    The role starts this helper and then runs the guard's package step
    with `DPKG_FRONTEND_LOCKED=1`, which tells dpkg that its caller
    already holds the frontend lock. So a helper that failed to take the
    lock and said nothing would be the worst available outcome: the step
    would run with the fence believed up and dpkg's own frontend
    protection switched off, on a host where an unattended upgrade is
    still holding the very lock it was told to respect. It exits
    non-zero and names the lock instead, and leaves no ready file for
    the role to misread as readiness.

    The wait is BOUNDED, and the bound is asserted against the clock's
    own record rather than against the verdict alone: a wait that
    silently became unbounded would hold the role's transient unit to
    its whole budget and then be SIGKILLed with no verdict at all --
    which is not a refusal, and must never be read as one.

    The last stanza is the same invocation once the holder has gone, and
    it is what makes the refusal above mean something: the exit code is
    the ONLY thing the role reads, so a helper that exited non-zero
    whatever happened would be indistinguishable from this one.
    """
    aptlock = _aptlock()
    lock = tmp_path / "lock-frontend"
    ready = tmp_path / "aptlock.pid"
    clock = _FakeClock()
    argv = ["--ready-file", str(ready), "--wait-seconds", "1", "--lock-file", str(lock)]
    holder = _hold(lock=lock)
    try:
        refusal = aptlock.hold_frontend_lock(
            lock_file=lock, ready_file=ready, wait_seconds=1, clock=clock
        )

        assert str(lock) in refusal
        assert not ready.exists()
        assert clock.slept == [aptlock.POLL_SECONDS] * 4
        with caplog.at_level("ERROR"):
            refused = aptlock.main(argv=argv)
        assert refused == 1
        assert str(lock) in "\n".join(record.getMessage() for record in caplog.records)
        assert not ready.exists()
    finally:
        holder.stop()

    previous = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGTERM})
    try:
        signal.pthread_kill(threading.get_ident(), signal.SIGTERM)
        granted = aptlock.main(argv=argv)
    finally:
        _ = signal.pthread_sigmask(signal.SIG_SETMASK, previous)

    assert granted == 0
    assert not ready.exists()
