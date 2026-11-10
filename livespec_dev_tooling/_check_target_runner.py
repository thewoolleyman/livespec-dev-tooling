"""One process and parallelism policy for every runner of check targets.

The normal aggregate (`parallel_check_dispatcher`), the expedited local hook
gates (`incident_local_gates.execute_plan`) and the expedited CI entrance
(`incident_ci_entry.CiEntry.execute`) all launch their targets through
`run_targets`, so a target runs under the same rules whichever path chose it
(livespec-dev-tooling-oqpw6t):

- Targets run in a thread pool whose width `cap_workers` derives from the CPUs
  the process may use, capped at `DEFAULT_MAX_WORKERS` unless a caller asks.
- Each target runs with stdin closed and its merged stdout/stderr spooled to a
  temporary file, so it can neither read the caller's terminal nor block on a
  full pipe.
- A target may name an earlier target it must wait `after`: it starts only once
  that one completes with exit 0, and is reported `BLOCKED` otherwise. This is
  for a genuine read-after-write data dependency, not collision avoidance.
- An optional `admit` callback is asked immediately before each launch. A
  refusal reports that target `NOT_ADMITTED` and stops every later launch;
  targets already running finish and keep their honest outcomes.

A target's output is spooled until it ends, so a long-running target is silent
to whatever watches the run's output. The runner therefore renews the progress
stamp `gate-run.sh` exports (`LIVESPEC_GATE_RUN_PROGRESS_STAMP`), without
printing, on each `_PROGRESS_TICK_SECONDS` tick at which a running target's
spool has GROWN since the previous tick. That is progress, not mere liveness: a
working target writes into its spool, while a deadlocked one (the
rerunfailures-under-xdist deadlock) stays alive and writes nothing, so the gate
runner's stall window still ends it and the gate cannot hang
(livespec-dev-tooling-5tqyfb). With no stamp exported nothing is touched.

WITHOUT a deadline (the normal aggregate and the CI entrance) a target stays in
the caller's process group, exactly as before this runner existed, so a signal
or a SIGKILL sent to that group (Ctrl-C, `gate-run.sh`'s stall kill, an OOM or
harness group kill) takes every target with it.

WITH a deadline (the expedited local hooks) the target gets its own session so
the deadline can kill its descendants; `_check_target_isolation` holds that
mechanism and states its one residual risk.

Callers keep their own selection, environments, reporting and result shapes.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import IO

from livespec_dev_tooling._check_target_isolation import (
    isolated_argv,
    kill_group,
    termination_raises,
    wait_for_exit,
)

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
# Exported by gate-run.sh to the gate's process tree; touching it renews the
# runner's outer stall window.
_PROGRESS_STAMP_ENV = "LIVESPEC_GATE_RUN_PROGRESS_STAMP"
_PROGRESS_TICK_SECONDS = 1.0


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


def _renew_progress_stamp() -> None:
    """Touch the gate run's progress stamp, when this run was started by one."""
    stamp = os.environ.get(_PROGRESS_STAMP_ENV, "")
    if stamp:
        Path(stamp).touch()


class _Groups:
    """The live isolated groups of one run; closing it stops launches and may kill all."""

    def __init__(self, *, isolated: bool) -> None:
        self.isolated = isolated
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
                isolated_argv(argv=run.argv) if self.isolated else run.argv,
                cwd=cwd,
                env=None if run.env is None else dict(run.env),
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=subprocess.STDOUT,
                start_new_session=self.isolated,
            )
            if self.isolated:
                self._live.add(process.pid)
            return process

    def wait(
        self, *, process: subprocess.Popen[bytes], output: IO[bytes], deadline_seconds: float | None
    ) -> bool:
        """Wait for the target; True when its deadline expired. Never leaves a zombie."""
        if deadline_seconds is None:
            _wait_renewing_progress(process=process, output=output)
            return False
        timed_out = wait_for_exit(process=process, deadline_seconds=deadline_seconds)
        # Kill the group and leave the live set under the lock, BEFORE the reap:
        # `close` kills under the same lock, so it can never killpg a reaped pid.
        with self._lock:
            kill_group(pid=process.pid)
            self._live.discard(process.pid)
        _ = process.wait()
        return timed_out

    def close(self, *, kill: bool) -> None:
        with self._lock:
            self._closed = True
            for pid in tuple(self._live) if kill else ():
                kill_group(pid=pid)


def _wait_renewing_progress(*, process: subprocess.Popen[bytes], output: IO[bytes]) -> None:
    """Wait for the target to exit, renewing the progress stamp while its spool grows."""
    spooled = 0
    while True:
        try:
            _ = process.wait(timeout=_PROGRESS_TICK_SECONDS)
        except subprocess.TimeoutExpired:
            size = os.fstat(output.fileno()).st_size
            if size > spooled:
                spooled = size
                _renew_progress_stamp()
        else:
            return


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
        timed_out = groups.wait(process=process, output=output, deadline_seconds=deadline_seconds)
        _ = output.seek(0)
        captured = output.read().decode("utf-8", errors="replace")
    return TargetOutcome(
        name=run.name,
        status=TIMED_OUT if timed_out else COMPLETED,
        returncode=None if timed_out else process.returncode,
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


def run_targets(
    *,
    runs: Sequence[TargetRun],
    cwd: Path,
    max_workers: int,
    deadline_seconds: float | None = None,
    admit: Callable[[], bool] | None = None,
    on_complete: Callable[..., None] | None = None,
) -> tuple[TargetOutcome, ...]:
    """Run every target in parallel and return their outcomes in `runs` order.

    `on_complete(outcome=...)` sees each outcome as it lands, for live progress. A target's
    `after` is honoured only when an EARLIER run carries that name, so a waiting
    target can never hold a worker its prerequisite still needs.
    """
    groups = _Groups(isolated=deadline_seconds is not None)
    futures: list[Future[TargetOutcome]] = []
    by_name: dict[str, Future[TargetOutcome]] = {}
    finished = False
    with (
        termination_raises(isolated=groups.isolated),
        ThreadPoolExecutor(max_workers=max_workers) as pool,
    ):
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
                    on_complete(outcome=future.result())
            finished = True
        finally:
            # Reached unfinished only when the caller was interrupted; the
            # exception continues once every live isolated group is dead.
            if not finished:
                groups.close(kill=True)
                pool.shutdown(wait=False, cancel_futures=True)
    return tuple(future.result() for future in futures)
