"""The repository's ONE hang guard for a test that waits on something.

`SPECIFICATION/non-functional-requirements.md`, "Load-independent concurrency
waits": a test's verdict must not depend on how fast the host runs it. A test
that waits for a child process, a worker thread, a barrier or an event waits
either with no wall-clock bound or under a hang guard, and the hang guard is one
value the repository defines once. This module is where it is defined. Import
`HANG_GUARD_SECONDS` from here; do not copy the number into a test file, and do
not define a second one.

WHY 900 SECONDS. The guard exists to end a run that will never finish, not to
judge how long a healthy one may take. On 2026-11-13 a 120 s per-call bound in
`tests/spec/test_homelab_worker_prove_vxlan_offload.py` refused a commit gate
under full-suite load (the call took 120.11 s), and the same unchanged
homelab-worker script tests were measured between 6.9 s and 101 s for one file
set as host contention moved (livespec-dev-tooling-uql3xe). The value is the
larger of 900 s and five times the slowest isolated run of a guarded call, and
900 s is the larger today: the slowest guarded call measured alone on the
loaded dev host was 54.94 s before its stub was fixed.

Expiry is reported as a HANG that names what the test was waiting for, never as
a bare `TimeoutExpired`, so a reader of a red run can tell "this never
finished" from "this was slow".
"""

from __future__ import annotations

import shlex
import subprocess
from collections.abc import Sequence
from os import PathLike
from typing import Any

import pytest

__all__: list[str] = [
    "HANG_GUARD_SECONDS",
    "run_under_hang_guard",
]

HANG_GUARD_SECONDS = 900


def run_under_hang_guard(
    args: Sequence[str | PathLike[str]],
    *,
    check: bool = False,
    **kwargs: Any,
) -> subprocess.CompletedProcess[Any]:
    """`subprocess.run(args, ...)` bounded only by the repository's hang guard.

    Every keyword `subprocess.run` takes is passed through, except `timeout`,
    which this function owns. When the guard expires the calling test FAILS as
    a hang, and the failure names the command that had not finished.
    """
    try:
        return subprocess.run(args, check=check, timeout=HANG_GUARD_SECONDS, **kwargs)
    except subprocess.TimeoutExpired:
        command = shlex.join(str(part) for part in args)
        pytest.fail(
            f"HANG: the test was waiting for `{command}` to finish, and it had not "
            f"finished after {HANG_GUARD_SECONDS} s, the repository's hang guard "
            "(tests/hang_guard.py). This is a run that never ended, not a slow one.",
            pytrace=False,
        )
