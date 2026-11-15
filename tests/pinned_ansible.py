"""Shared test-side support for every test that runs the pinned `ansible-core` through `uvx`.

`SPECIFICATION/non-functional-requirements.md`, "Load-independent concurrency
waits": a test's verdict must not depend on how fast the host runs it. ansible-core
2.21 starts its controller's in-process RPC server on a worker thread and waits for
it with a HARD-CODED `_server_ready.wait(5)` in `ansible/_internal/_rpc_host.py`,
then raises `TimeoutError("Local RPC server did not start.")`. There is no
configuration knob. A CPU-starved host takes longer than five seconds to schedule
that thread, and the play never starts (livespec-dev-tooling-biq757: three such
failures on master run 43543797308, one on a push gate before it).

The remedy is one `sitecustomize` (`fixtures/pinned_ansible_rpc_wait/`) that the
ansible interpreter loads from `PYTHONPATH`. It replaces that module's event with
one that waits for the shared hang guard (`tests/hang_guard.HANG_GUARD_SECONDS`)
and, on expiry, records a marker file and raises an error that names the wait.
`conftest.py` applies it to EVERY test through an autouse fixture, so a module
that runs `uvx --from ansible-core==<pin> ansible-playbook` inherits it without
asking, and a module added later cannot omit it. `fail_if_rpc_start_hung` turns
the marker into a test failure that names the wait.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

import pytest

from tests.hang_guard import HANG_GUARD_SECONDS

__all__: list[str] = [
    "RPC_START_HANG_MARKER_VARIABLE",
    "RPC_START_WAIT_SECONDS_VARIABLE",
    "RPC_WAIT_DIRECTORY",
    "fail_if_rpc_start_hung",
    "rpc_start_environment",
]

RPC_WAIT_DIRECTORY = Path(__file__).resolve().parent / "fixtures" / "pinned_ansible_rpc_wait"
RPC_START_WAIT_SECONDS_VARIABLE = "LIVESPEC_ANSIBLE_RPC_START_WAIT_SECONDS"
RPC_START_HANG_MARKER_VARIABLE = "LIVESPEC_ANSIBLE_RPC_START_HANG_MARKER"


def rpc_start_environment(*, base: Mapping[str, str], marker: Path) -> dict[str, str]:
    """`base` plus the variables that make an ansible interpreter wait for its RPC server patiently."""
    inherited = base.get("PYTHONPATH")
    return {
        "PYTHONPATH": (
            f"{RPC_WAIT_DIRECTORY}{os.pathsep}{inherited}" if inherited else str(RPC_WAIT_DIRECTORY)
        ),
        RPC_START_WAIT_SECONDS_VARIABLE: str(HANG_GUARD_SECONDS),
        RPC_START_HANG_MARKER_VARIABLE: str(marker),
    }


def fail_if_rpc_start_hung(*, marker: Path) -> None:
    """Fail the running test as a hang when an ansible run in it never got its RPC server started."""
    if marker.exists():
        pytest.fail(
            "HANG: the test was waiting for ansible-core's in-process RPC server to start "
            "(`_server_ready.wait` in `ansible/_internal/_rpc_host.py`), and it had not "
            f"started after {HANG_GUARD_SECONDS} s, the repository's hang guard "
            "(tests/hang_guard.py). This is a run that never started, not a slow one.",
            pytrace=False,
        )
