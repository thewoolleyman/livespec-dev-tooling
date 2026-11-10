"""A SIGKILL of the caller's process group leaves no check target running.

Work-item livespec-dev-tooling-oqpw6t, review finding 2. `gate-run.sh`'s stall
kill, an OOM kill and a harness group kill all SIGKILL the caller's whole
process group, which no handler can intercept. Only a real caller process can
show what survives that, so these tests start one (allowlisted in
`subprocess_spawn_allowlist`; the child's coverage startup is scrubbed).

- Without a deadline (the normal aggregate) a target stays in the caller's
  group, so the group kill takes it.
- With a deadline (the expedited local hooks) a target is isolated in its own
  session, so the group kill cannot reach it; the parent-death guard
  (`setpriv --pdeathsig KILL`) kills it instead. The guard reaches the target
  process only, which is the residual risk `_check_target_isolation` states.
"""

from __future__ import annotations

import itertools
import os
import select
import signal
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from shutil import which

import pytest

__all__: list[str] = []

_ROOT = Path(__file__).resolve().parents[2]

_CALLER = """
import sys
from pathlib import Path
from livespec_dev_tooling._check_target_runner import TargetRun, run_targets
deadline = None if sys.argv[2] == "none" else float(sys.argv[2])
run_targets(
    runs=[TargetRun(name="held", argv=("/bin/sh", "-c", sys.argv[3]))],
    cwd=Path(sys.argv[1]),
    max_workers=1,
    deadline_seconds=deadline,
)
"""


def _caller_environment() -> dict[str, str]:
    environment = {
        key: value
        for key, value in os.environ.items()
        if key != "COVERAGE_PROCESS_START" and not key.startswith("COV_CORE_")
    }
    environment["PYTHONPATH"] = str(_ROOT)
    return environment


def _wait_for_ready(
    *,
    ready: Path,
    limit_s: float = 30,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> bool:
    """True once `ready` exists; False once `limit_s` has passed.

    The clock and sleep are injectable so a test fixes which lines run; the
    limit is only a guard against a hang.
    """
    started = clock()
    while not ready.exists():
        if clock() - started >= limit_s:
            return False
        sleep(0.05)
    return True


def _group_kill_leaves_no_holder(*, tmp_path: Path, deadline: str, script: str) -> bool:
    fifo = tmp_path / "lifetime.fifo"
    os.mkfifo(fifo)
    reader = os.open(fifo, os.O_RDONLY | os.O_NONBLOCK)
    try:
        caller = subprocess.Popen(
            [sys.executable, "-c", _CALLER, str(tmp_path), deadline, script.format(fifo=fifo)],
            cwd=_ROOT,
            env=_caller_environment(),
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
        ready = tmp_path / "ready"
        _ = _wait_for_ready(ready=ready)
        os.killpg(caller.pid, signal.SIGKILL)
        _ = caller.wait()
        readable, _, _ = select.select([reader], [], [], 5)
        return ready.exists() and readable == [reader] and os.read(reader, 1) == b""
    finally:
        os.close(reader)


def test_a_group_kill_of_the_normal_caller_takes_its_targets(tmp_path: Path) -> None:
    script = 'exec 3> "{fifo}"; sleep 30 & touch ready; wait'
    assert _group_kill_leaves_no_holder(tmp_path=tmp_path, deadline="none", script=script)


@pytest.mark.skipif(which("setpriv") is None, reason="the parent-death guard needs setpriv")
def test_a_group_kill_of_the_expedited_caller_takes_the_isolated_target(tmp_path: Path) -> None:
    script = 'exec 3> "{fifo}"; touch ready; exec sleep 30'
    assert _group_kill_leaves_no_holder(tmp_path=tmp_path, deadline="60", script=script)


def _fake_clock() -> Callable[[], float]:
    readings = itertools.count()
    return lambda: float(next(readings))


def test_the_ready_wait_returns_at_once_when_the_file_is_already_there(tmp_path: Path) -> None:
    ready = tmp_path / "ready"
    _ = ready.write_text("", encoding="utf-8")
    sleeps: list[float] = []
    assert _wait_for_ready(ready=ready, clock=_fake_clock(), sleep=sleeps.append)
    assert sleeps == []


def test_the_ready_wait_sleeps_until_the_file_appears(tmp_path: Path) -> None:
    ready = tmp_path / "ready"
    sleeps: list[float] = []

    def sleep_then_create_on_third(seconds: float) -> None:
        sleeps.append(seconds)
        if len(sleeps) == 3:
            _ = ready.write_text("", encoding="utf-8")

    assert _wait_for_ready(
        ready=ready, limit_s=100, clock=_fake_clock(), sleep=sleep_then_create_on_third
    )
    assert sleeps == [0.05] * 3


def test_the_ready_wait_gives_up_when_the_file_never_appears(tmp_path: Path) -> None:
    sleeps: list[float] = []
    assert not _wait_for_ready(
        ready=tmp_path / "never", limit_s=2, clock=_fake_clock(), sleep=sleeps.append
    )
    assert sleeps == [0.05]
