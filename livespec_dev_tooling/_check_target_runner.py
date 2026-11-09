"""One process and parallelism policy for every runner of check targets.

The normal aggregate (`parallel_check_dispatcher`), the expedited local hook
gates (`incident_local_gates.execute_plan`) and the expedited CI entrance
(`incident_ci_entry.CiEntry.execute`) all launch their targets through
`run_targets`, so a target runs under the same rules whichever path chose it
(livespec-dev-tooling-oqpw6t):

- Targets run in a thread pool whose width `cap_workers` derives from the CPUs
  the process may use, capped at `DEFAULT_MAX_WORKERS` unless a caller asks.
- Each target runs in its OWN session (`start_new_session`) with stdin closed
  and its merged stdout/stderr spooled to a temporary file, so a target can
  neither read the caller's terminal nor block on a full pipe.
- When a target ends, or reaches its optional deadline, its whole process group
  is killed with SIGKILL, so no descendant outlives the target that started it.
  A deadline expiry reports `TIMED_OUT` with no return code.
- A target may name an earlier target it must wait `after`: it starts only once
  that one completes with exit 0, and is reported `BLOCKED` otherwise. This is
  for a genuine read-after-write data dependency, not collision avoidance.
- An optional `admit` callback is asked immediately before each launch. A
  refusal reports that target `NOT_ADMITTED` and stops every later launch;
  targets already running finish and keep their honest outcomes.
- An interruption of the caller (an exception, Ctrl-C, or SIGTERM / SIGHUP
  delivered while the main thread is waiting) kills every live target group.
  The new session moves targets out of the caller's process group, so a signal
  sent to that group no longer reaches them; this restores that reach.

Callers keep their own selection, environments, reporting and result shapes.
"""

from __future__ import annotations

import os
import signal
import subprocess
import tempfile
import threading
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from pathlib import Path
from typing import IO

__all__: list[str] = [
    "BLOCKED",
    "COMPLETED",
    "DEFAULT_MAX_WORKERS",
    "LAUNCH_FAILED",
    "NOT_ADMITTED",
    "NOT_LAUNCHED",
    "TIMED_OUT",
    "TargetOutcome",
    "TargetRun",
    "cap_workers",
    "run_targets",
]

DEFAULT_MAX_WORKERS = 8

COMPLETED = "completed"
TIMED_OUT = "timed-out"
LAUNCH_FAILED = "launch-failed"
BLOCKED = "blocked"
NOT_ADMITTED = "not-admitted"
NOT_LAUNCHED = "not-launched"

_LAUNCH_FAILED_CODE = 127


@dataclass(frozen=True, kw_only=True)
class TargetRun:
    """One target to launch: its argv, its environment and its data prerequisite.

    `env` None inherits the caller's environment; a mapping replaces it whole.
    """

    name: str
    argv: tuple[str, ...]
    env: Mapping[str, str] | None = None
    after: str | None = None


@dataclass(frozen=True, kw_only=True)
class TargetOutcome:
    """What happened to one target; `returncode` is None unless it was measured."""

    name: str
    status: str
    returncode: int | None
    wall_time_s: float = 0.0
    output: str = ""


def cap_workers(*, requested: int | None, allowed: int) -> int:
    """Return the effective worker count: min(allowed CPUs, requested or DEFAULT)."""
    cap = requested if requested is not None else DEFAULT_MAX_WORKERS
    return max(1, min(allowed, cap))


def _kill_group(*, pid: int) -> None:
    """Kill a target's whole session, including children that ignore SIGTERM."""
    with suppress(ProcessLookupError):
        os.killpg(pid, signal.SIGKILL)


class _Groups:
    """The live target groups of one run; closing it stops launches and may kill all."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._live: set[int] = set()
        self._closed = False

    def launch(
        self, *, run: TargetRun, cwd: Path, output: IO[bytes]
    ) -> subprocess.Popen[bytes] | None:
        with self._lock:
            if self._closed:
                return None
            process = subprocess.Popen(  # noqa: S603 — caller-owned argv; never a shell string.
                run.argv,
                cwd=cwd,
                env=None if run.env is None else dict(run.env),
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            self._live.add(process.pid)
            return process

    def release(self, *, pid: int) -> None:
        _kill_group(pid=pid)
        with self._lock:
            self._live.discard(pid)

    def close(self, *, kill: bool) -> None:
        with self._lock:
            self._closed = True
            live = tuple(self._live)
        for pid in live if kill else ():
            _kill_group(pid=pid)


def _run_one(
    *, run: TargetRun, cwd: Path, deadline_seconds: float | None, groups: _Groups
) -> TargetOutcome:
    started = time.monotonic()
    if not run.argv:
        return TargetOutcome(
            name=run.name,
            status=LAUNCH_FAILED,
            returncode=_LAUNCH_FAILED_CODE,
            output="empty target command",
        )
    with tempfile.TemporaryFile() as output:
        try:
            process = groups.launch(run=run, cwd=cwd, output=output)
        except OSError as error:
            return TargetOutcome(
                name=run.name,
                status=LAUNCH_FAILED,
                returncode=_LAUNCH_FAILED_CODE,
                output=str(error),
            )
        if process is None:
            return TargetOutcome(name=run.name, status=NOT_LAUNCHED, returncode=None)
        try:
            code = process.wait(timeout=deadline_seconds)
        except subprocess.TimeoutExpired:
            code = None
        finally:
            groups.release(pid=process.pid)
            _ = process.wait()
        _ = output.seek(0)
        captured = output.read().decode("utf-8", errors="replace")
    return TargetOutcome(
        name=run.name,
        status=TIMED_OUT if code is None else COMPLETED,
        returncode=code,
        wall_time_s=time.monotonic() - started,
        output=captured,
    )


def _run_admitted(
    *,
    run: TargetRun,
    prerequisite: Future[TargetOutcome] | None,
    cwd: Path,
    deadline_seconds: float | None,
    admit: Callable[[], bool] | None,
    groups: _Groups,
) -> TargetOutcome:
    if prerequisite is not None:
        before = prerequisite.result()
        if before.status != COMPLETED or before.returncode != 0:
            return TargetOutcome(
                name=run.name,
                status=BLOCKED,
                returncode=None,
                output=f"BLOCKED: prereq '{before.name}' failed (exit {before.returncode})",
            )
    if admit is not None and not admit():
        groups.close(kill=False)
        return TargetOutcome(name=run.name, status=NOT_ADMITTED, returncode=None)
    return _run_one(run=run, cwd=cwd, deadline_seconds=deadline_seconds, groups=groups)


def _raise_exit(*, signum: int) -> None:
    raise SystemExit(128 + signum)


@contextmanager
def _termination_raises() -> Iterator[None]:
    """Turn SIGTERM / SIGHUP into an exception while the main thread waits.

    Only the main thread may install a handler; elsewhere the caller's own
    handling stands unchanged.
    """
    if threading.current_thread() is not threading.main_thread():
        yield
        return
    # The handler adapts Python's positional (signum, frame) handler convention.
    previous = {
        sig: signal.signal(sig, lambda signum, _frame: _raise_exit(signum=signum))
        for sig in (signal.SIGTERM, signal.SIGHUP)
    }
    try:
        yield
    finally:
        for sig, handler in previous.items():
            _ = signal.signal(sig, handler)


def run_targets(
    *,
    runs: Sequence[TargetRun],
    cwd: Path,
    max_workers: int,
    deadline_seconds: float | None = None,
    admit: Callable[[], bool] | None = None,
    on_complete: Callable[[TargetOutcome], None] | None = None,
) -> tuple[TargetOutcome, ...]:
    """Run every target in parallel and return their outcomes in `runs` order.

    `on_complete` sees each outcome as it lands, for live progress. A target's
    `after` is honoured only when an EARLIER run carries that name, so a waiting
    target can never hold a worker its prerequisite still needs.
    """
    groups = _Groups()
    futures: list[Future[TargetOutcome]] = []
    by_name: dict[str, Future[TargetOutcome]] = {}
    finished = False
    with _termination_raises(), ThreadPoolExecutor(max_workers=max_workers) as pool:
        try:
            for run in runs:
                future = pool.submit(
                    _run_admitted,
                    run=run,
                    prerequisite=None if run.after is None else by_name.get(run.after),
                    cwd=cwd,
                    deadline_seconds=deadline_seconds,
                    admit=admit,
                    groups=groups,
                )
                futures.append(future)
                _ = by_name.setdefault(run.name, future)
            for future in as_completed(futures):
                if on_complete is not None:
                    on_complete(future.result())
            finished = True
        finally:
            # Reached unfinished only when the caller was interrupted; the
            # exception continues once every live group is dead.
            if not finished:
                groups.close(kill=True)
                pool.shutdown(wait=False, cancel_futures=True)
    return tuple(future.result() for future in futures)
