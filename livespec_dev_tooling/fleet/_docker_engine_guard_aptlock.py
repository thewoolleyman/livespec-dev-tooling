"""The dpkg frontend lock, held for the Docker engine install guard's package step.

Governing specification: `SPECIFICATION/non-functional-requirements.md`
section "Docker engine install guard", "Package fence". Governing design:
`docs/docker-engine-guard-design.md`, Mechanism 5's fence as amended by
R6 and F6.

WHY THIS EXISTS AT ALL. The guard's package step issues `dpkg -i` with
`DPKG_FRONTEND_LOCKED=1`, which is the documented way for a frontend
that ALREADY HOLDS the lock to call dpkg -- so something has to be
holding it, from before the audit until after the install. Design F6
puts that something in its own transient unit rather than in the
controller's SSH session: a lock whose holder dies with an SSH
connection is a fence that disappears exactly when the connection drops,
which is the failure the whole guard exists to survive. If the unit
expires mid-install, dpkg still holds `/var/lib/dpkg/lock` itself, so
apt sees an ordinary lock failure rather than a concurrent write.

WHY IT LIVES HERE RATHER THAN IN THE ROLE. It is installed onto the
guarded host with the guard tree, and it is the one piece of the fence
with real logic in it -- a bounded wait, a record lock, a published PID,
a signal -- so it belongs where the gates and the tests are rather than
as an extension-less script beside a playbook.

STDLIB ONLY, and self-contained: unlike its siblings this module imports
nothing from the guard package, so the copy on the guarded host runs
against that host's bare interpreter with no package root on `sys.path`
at all. Expected failures are RETURNED as the reason an operator reads,
never raised, exactly as the rest of the guard's modules do.
"""

from __future__ import annotations

import argparse
import fcntl
import logging
import os
import signal
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final, Protocol

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

__all__: list[str] = [
    "DEFAULT_LOCK_FILE",
    "LOGGER_NAME",
    "POLL_SECONDS",
    "LockClock",
    "hold_frontend_lock",
    "main",
    "wait_for_sigterm",
]

# The lock apt and dpkg's own FRONTENDS take, and therefore the only one
# worth holding: `/var/lib/dpkg/lock` is taken by dpkg itself, per
# transaction, and is not what `DPKG_FRONTEND_LOCKED=1` refers to.
DEFAULT_LOCK_FILE: Final[str] = "/var/lib/dpkg/lock-frontend"

# How often the wait retries. Short enough that the helper publishes its
# readiness promptly once an unattended upgrade finishes, long enough
# that a several-minute wait is not a spin.
POLL_SECONDS: Final[float] = 0.25

LOGGER_NAME: Final[str] = "docker-engine-guard-aptlock"

# dpkg's own mode for this file, so a run that has to CREATE it -- a host
# whose dpkg has never run, or an acceptance host driven elsewhere --
# leaves behind what dpkg would have.
_LOCK_FILE_MODE: Final[int] = 0o660

_PROG: Final[str] = "docker-engine-guard-aptlock"
_DESCRIPTION: Final[str] = "Hold the dpkg frontend lock for the guard's package step."


class LockClock(Protocol):
    """The clock and the sleep the bounded wait reaches the world through.

    Documentation rides in comments rather than per-method docstrings for
    the reason the guard's host protocol records: a protocol method needs
    an `...` body, and an `...` below a docstring is a line no caller
    executes in a tree held to 100% per-file coverage.
    """

    # CLOCK_MONOTONIC seconds. The bound is against this clock and never
    # the wall clock, which an NTP step can move under a wait.
    def monotonic(self) -> float: ...

    # The wait between attempts on the lock.
    def sleep(self, *, seconds: float) -> None: ...


@dataclass(frozen=True, kw_only=True)
class _RealClock:
    """The clock the helper runs on against a real host."""

    def monotonic(self) -> float:
        """CLOCK_MONOTONIC seconds."""
        return time.monotonic()

    def sleep(self, *, seconds: float) -> None:
        """The one place this module blocks on the clock."""
        time.sleep(seconds)


_REAL_CLOCK: Final[_RealClock] = _RealClock()


def wait_for_sigterm() -> None:
    """Block until SIGTERM arrives, with no signal handler at all.

    The signal is BLOCKED and then waited for rather than handled, and
    both halves matter. Blocked, it cannot be lost in the window between
    the ready file appearing and the wait starting -- a SIGTERM
    delivered there would kill the helper outright and leave the ready
    file behind, which a role reads as a fence that is still up. And
    waited for rather than handled, the hold needs no flag a handler
    would have to set from a `(signum, frame)` signature this
    repository's keyword-only discipline cannot express.

    The mask reaches the CALLING THREAD only, which is all this helper
    needs: it runs as a single-threaded oneshot unit, so the thread that
    blocks the signal is the only one there is to deliver it to.
    """
    _ = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGTERM})
    _ = signal.sigwait({signal.SIGTERM})


def _locked(*, fd: int) -> bool:
    """Try once, without blocking, for the exclusive record lock on `fd`.

    `fcntl.lockf` and never `flock`: dpkg's frontends take a POSIX
    RECORD lock (`F_SETLK`) on this file, and the two kinds do not
    conflict with one another at all -- an `flock` here would be granted
    beside dpkg's lock, and the helper would report holding a fence it
    does not hold.
    """
    try:
        fcntl.lockf(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        # EAGAIN where another process holds it, EACCES on some kernels
        # for the same condition; both mean "not ours yet".
        return False
    return True


def _take_record_lock(*, lock_file: Path, wait_seconds: float, clock: LockClock) -> int | None:
    """Take the record lock within `wait_seconds`, or answer `None`.

    `O_CLOEXEC` is on the open because the whole point of this helper is
    that the lock goes when IT does: a child that inherited the
    descriptor would hold the fence past the process that took it. The
    descriptor is closed on expiry, so a refusal leaves nothing open.
    """
    expiry = clock.monotonic() + wait_seconds
    fd = os.open(lock_file, os.O_CREAT | os.O_RDWR | os.O_CLOEXEC, _LOCK_FILE_MODE)
    while not _locked(fd=fd):
        if clock.monotonic() >= expiry:
            os.close(fd)
            return None
        clock.sleep(seconds=POLL_SECONDS)
    return fd


def hold_frontend_lock(
    *,
    lock_file: Path,
    ready_file: Path,
    wait_seconds: float,
    clock: LockClock = _REAL_CLOCK,
    await_termination: Callable[[], None] = wait_for_sigterm,
) -> str:
    """Hold `lock_file` until SIGTERM, or answer why the fence could not go up.

    The PID goes into `ready_file` and not merely a marker, because that
    file is how the hold ENDS: the helper runs detached in its own unit,
    so the role does not already know the PID it has to signal. The file
    appearing is also the role's only evidence that the fence is up,
    which is why it is written once the lock is actually held and not
    before.

    On the way out the ready file is removed BEFORE the lock is
    released, and that order is the whole of its meaning: a role that
    saw the file still there would read the fence as still up. The
    removal is in a `finally`, so it also covers the way out nobody
    plans for.

    `await_termination` is injected for the same reason the clock is --
    so the hold can be driven and OBSERVED while it holds -- and
    defaults to the real signal wait.
    """
    fd = _take_record_lock(lock_file=lock_file, wait_seconds=wait_seconds, clock=clock)
    if fd is None:
        return (
            f"{lock_file} is still held by another process after {wait_seconds} seconds, "
            "so the package step's fence was never taken"
        )
    try:
        _ = ready_file.write_text(str(os.getpid()), encoding="utf-8")
        await_termination()
    finally:
        ready_file.unlink(missing_ok=True)
        os.close(fd)
    return ""


def main(*, argv: Sequence[str]) -> int:
    """Hold the frontend lock, as the role's own transient unit invokes this.

    The ready file and the wait are REQUIRED rather than defaulted: both
    are decided by the role step that starts this helper -- the first is
    where that step watches for readiness, the second is how long it is
    willing to wait for an unattended upgrade to finish -- and a default
    for either would be this module guessing at the fence it is part of.
    """
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    parser = argparse.ArgumentParser(prog=_PROG, description=_DESCRIPTION)
    _ = parser.add_argument("--ready-file", required=True)
    _ = parser.add_argument("--wait-seconds", type=float, required=True)
    _ = parser.add_argument("--lock-file", default=DEFAULT_LOCK_FILE)
    args = parser.parse_args(list(argv))
    refusal = hold_frontend_lock(
        lock_file=Path(args.lock_file),
        ready_file=Path(args.ready_file),
        wait_seconds=args.wait_seconds,
    )
    if refusal:
        logging.getLogger(LOGGER_NAME).error(refusal)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(argv=sys.argv[1:]))
