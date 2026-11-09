"""Isolation of a check target that runs under a deadline.

`_check_target_runner` uses this ONLY for a target with a deadline (the
expedited local hooks). A deadline must be able to kill a target's
descendants, so such a target gets its OWN session; everything here exists to
keep that isolation from leaking processes (livespec-dev-tooling-oqpw6t).

- When the target ends or reaches the deadline, its whole group is killed with
  SIGKILL BEFORE the leader is reaped, so the group id cannot have been reused.
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

__all__: list[str] = ["isolated_argv", "kill_group", "termination_raises", "wait_then_kill"]

_EXIT_POLL_SECONDS = 0.05


def kill_group(*, pid: int) -> None:
    """Kill an isolated target's whole session, including children ignoring SIGTERM."""
    with suppress(ProcessLookupError):
        os.killpg(pid, signal.SIGKILL)


def isolated_argv(*, argv: tuple[str, ...]) -> tuple[str, ...]:
    """Prefix the parent-death guard where the host has it."""
    setpriv = shutil.which("setpriv")
    return argv if setpriv is None else (setpriv, "--pdeathsig", "KILL", "--", *argv)


def wait_then_kill(*, process: subprocess.Popen[bytes], deadline_seconds: float) -> bool:
    """Wait up to the deadline, kill the group, then reap; True when it expired.

    WNOWAIT leaves the leader unreaped, so its id stays reserved while the group
    is killed; only then does `process.wait()` reap it.
    """
    expires = time.monotonic() + deadline_seconds
    timed_out = False
    while os.waitid(os.P_PID, process.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT) is None:
        if time.monotonic() >= expires:
            timed_out = True
            break
        time.sleep(_EXIT_POLL_SECONDS)
    kill_group(pid=process.pid)
    _ = process.wait()
    return timed_out


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
