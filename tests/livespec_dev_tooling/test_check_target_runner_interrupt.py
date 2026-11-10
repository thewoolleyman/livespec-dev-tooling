"""An interrupted run stops a target that shares the caller's process group.

Work-item livespec-dev-tooling-8o8e.16. A runner signalled on its own pid, not
its group, must not wait for a still-running target before it can unwind and
remove its coverage directories: the executor joins the thread waiting on that
target, so the runner asks the target to stop.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from livespec_dev_tooling._check_target_runner import TargetRun, run_targets

__all__: list[str] = []

_HOLD = 'echo $$ > "{pid}"; exec sleep 120'
_QUICK = 'while [ ! -s "{pid}" ]; do sleep 0.02; done'


def test_an_interrupt_stops_a_running_target_in_the_callers_group(tmp_path: Path) -> None:
    pid_file = tmp_path / "held.pid"

    def interrupt(**_: object) -> None:
        raise KeyboardInterrupt

    started = time.monotonic()
    with pytest.raises(KeyboardInterrupt):
        _ = run_targets(
            runs=[
                TargetRun(name="held", argv=("/bin/sh", "-c", _HOLD.format(pid=pid_file))),
                TargetRun(name="quick", argv=("/bin/sh", "-c", _QUICK.format(pid=pid_file))),
            ],
            cwd=tmp_path,
            max_workers=2,
            on_complete=interrupt,
        )
    assert time.monotonic() - started < 60
    with pytest.raises(ProcessLookupError):
        os.kill(int(pid_file.read_text()), 0)
