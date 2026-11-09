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

import os
import select
import signal
import subprocess
import sys
import time
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
        started = time.monotonic()
        while not ready.exists() and time.monotonic() - started < 30:
            time.sleep(0.05)
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
