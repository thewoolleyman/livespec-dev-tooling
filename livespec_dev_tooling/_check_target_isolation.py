"""Isolation of a check target that runs under a deadline.

`_check_target_runner` uses this ONLY for a target with a deadline (the
expedited local hooks). A deadline must be able to kill a target's
descendants, so such a target gets its OWN session; everything here exists to
keep that isolation from leaking processes (livespec-dev-tooling-oqpw6t).

- When the target ends or reaches the deadline, its whole group is killed with
  SIGKILL BEFORE the leader is reaped, so the group id cannot have been reused.
  Where CPython has no `os.waitid` (macOS), the wait polls `Popen.poll()`,
  which reaps the leader first; there a group id freed by that reap could in
  principle be reused before the kill, a window of one poll interval.
- On Linux the target is started under `setpriv --pdeathsig KILL`, so the
  target process dies if the thread that launched it dies, including by
  SIGKILL. RESIDUAL RISK: a parent-death signal reaches only that process, so a
  descendant it already started can outlive a SIGKILLed caller until it ends on
  its own; without `setpriv` (macOS), the target itself can too.
- While the main thread waits, SIGTERM and SIGHUP raise `SystemExit`, so the
  runner can kill every live isolated group. A handler the caller set to
  SIG_IGN (for example under `nohup`) is left alone.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager, suppress

__all__: list[str] = ["isolated_argv", "kill_group", "termination_raises", "wait_for_exit"]

_EXIT_POLL_SECONDS = 0.05


def kill_group(*, pid: int) -> None:
    """Kill an isolated target's whole session, including children ignoring SIGTERM."""
    with suppress(ProcessLookupError):
        os.killpg(pid, signal.SIGKILL)


def isolated_argv(*, argv: tuple[str, ...]) -> tuple[str, ...]:
    """Prefix the parent-death guard where the host has it."""
    setpriv = shutil.which("setpriv")
    return argv if setpriv is None else (setpriv, "--pdeathsig", "KILL", "--", *argv)


def _exited(*, process: subprocess.Popen[bytes]) -> bool:
    """Whether the leader has exited, leaving it UNREAPED where the host allows.

    WNOWAIT keeps the leader's id reserved, so the caller can kill the group
    before `process.wait()` reaps it.
    """
    if not hasattr(os, "waitid"):
        return process.poll() is not None
    return os.waitid(os.P_PID, process.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT) is not None


def wait_for_exit(*, process: subprocess.Popen[bytes], deadline_seconds: float) -> bool:
    """Wait up to the deadline for the leader to exit; True when the deadline expired.

    The caller kills the group, then reaps the leader.
    """
    expires = time.monotonic() + deadline_seconds
    while not _exited(process=process):
        if time.monotonic() >= expires:
            return True
        time.sleep(_EXIT_POLL_SECONDS)
    return False


def _raise_exit(*, signum: int) -> None:
    raise SystemExit(128 + signum)


@contextmanager
def termination_raises(*, isolated: bool) -> Iterator[None]:
    """Turn SIGTERM / SIGHUP into an exception while the main thread waits.

    Only for isolated targets, which a signal to the caller's group cannot
    reach. Only the main thread may install a handler, and a signal the caller
    ignores stays ignored; otherwise the caller's own handling stands.
    """
    if not isolated or threading.current_thread() is not threading.main_thread():
        yield
        return
    # The handler adapts Python's positional (signum, frame) handler convention.
    previous = {
        sig: signal.signal(sig, lambda signum, _frame: _raise_exit(signum=signum))
        for sig in (signal.SIGTERM, signal.SIGHUP)
        if signal.getsignal(sig) is not signal.SIG_IGN
    }
    try:
        yield
    finally:
        for sig, handler in previous.items():
            _ = signal.signal(sig, handler)
