"""Wait for Kueue admission before spending a delegated gate's run budget.

Kueue keeps a queued Job suspended. That wait is queueing, not execution, so it
has a bound of its own and does not consume the bound for the Job's terminal
state. Both waits use the existing `Sleeper` seam: their limits are poll
counts, never wall-clock reads in this client.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

from livespec_dev_tooling.gate_credential import with_gates_kubeconfig
from livespec_dev_tooling.gate_remote_invocation import (
    GateCommandRunner,
    GateStepFailed,
    Sleeper,
    require_success,
)
from livespec_dev_tooling.gate_remote_job_status import Terminal, terminal_condition, unreadable
from livespec_dev_tooling.gate_remote_request import GateRunRequest

# `returns` is VENDORED, not installed; a bare import here would resolve only
# when some earlier import in the process happened to run first.
_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.result import Failure, Result, Success  # noqa: E402  — vendor-path-aware import.

__all__: list[str] = ["await_terminal_state"]

_AWAIT_STEP = "await-gate-terminal"
_ADMITTED_CONDITIONS = frozenset({"Admitted", "Started"})
_ASSERTED = "True"


def await_terminal_state(
    *, request: GateRunRequest, runner: GateCommandRunner, sleeper: Sleeper, job_name: str
) -> Result[Terminal, GateStepFailed]:
    """Wait through admission, then poll the Job's independent terminal budget."""
    argv = [
        *with_gates_kubeconfig(argv=["kubectl"]),
        "--namespace",
        request.namespace,
        "get",
        "job",
        job_name,
        "--output",
        "json",
    ]
    admitted = _await_admission(
        argv=argv,
        request=request,
        runner=runner,
        sleeper=sleeper,
        job_name=job_name,
    )
    if isinstance(admitted, Failure):
        return Failure(admitted.failure())
    terminal = admitted.unwrap()
    if terminal is not None:
        return Success(terminal)
    return _await_terminal(
        argv=argv,
        request=request,
        runner=runner,
        sleeper=sleeper,
        job_name=job_name,
    )


def _await_admission(
    *,
    argv: list[str],
    request: GateRunRequest,
    runner: GateCommandRunner,
    sleeper: Sleeper,
    job_name: str,
) -> Result[Terminal | None, GateStepFailed]:
    """Wait for an admission signal, retaining a terminal state read during it."""
    polls = request.admission_poll_budget()
    for poll in range(polls):
        read = require_success(
            step=_AWAIT_STEP,
            argv=argv,
            outcome=runner(argv=argv, cwd=request.repo_root),
        )
        if isinstance(read, Failure):
            return Failure(read.failure())
        else:
            terminal = terminal_condition(
                argv=argv,
                payload=read.unwrap().stdout,
                step=_AWAIT_STEP,
            )
            if isinstance(terminal, Failure):
                return Failure(terminal.failure())
            ended = terminal.unwrap()
            if ended is not None:
                return Success(ended)
            if _admission_observed(payload=read.unwrap().stdout):
                return Success(None)
        if poll + 1 < polls:
            sleeper(seconds=request.poll_interval_seconds)
    return Failure(
        unreadable(
            step=_AWAIT_STEP,
            argv=argv,
            detail=(
                f"admission wait for {job_name} exceeded "
                f"{request.admission_timeout_seconds:g}s without admission"
            ),
        )
    )


def _await_terminal(
    *,
    argv: list[str],
    request: GateRunRequest,
    runner: GateCommandRunner,
    sleeper: Sleeper,
    job_name: str,
) -> Result[Terminal, GateStepFailed]:
    """Poll an admitted Job until it reports a terminal condition, or give up."""
    polls = request.poll_budget()
    for poll in range(polls):
        read = require_success(
            step=_AWAIT_STEP,
            argv=argv,
            outcome=runner(argv=argv, cwd=request.repo_root),
        )
        if isinstance(read, Failure):
            return Failure(read.failure())
        else:
            terminal = terminal_condition(
                argv=argv,
                payload=read.unwrap().stdout,
                step=_AWAIT_STEP,
            )
            if isinstance(terminal, Failure):
                return Failure(terminal.failure())
            ended = terminal.unwrap()
            if ended is not None:
                return Success(ended)
        if poll + 1 < polls:
            sleeper(seconds=request.poll_interval_seconds)
    gave_up = f"{job_name} reached no terminal condition within {request.poll_timeout_seconds:g}s"
    return Failure(unreadable(step=_AWAIT_STEP, argv=argv, detail=gave_up))


def _admission_observed(*, payload: str) -> bool:
    """Return whether Kueue or the Job itself reports that execution has begun."""
    document = cast("Mapping[str, Mapping[str, object]]", json.loads(payload))
    spec = document.get("spec", {})
    status = document.get("status", {})
    if spec.get("suspend") is False or isinstance(status.get("startTime"), str):
        admission_seen = True
        return admission_seen
    conditions = cast("Sequence[Mapping[str, str]]", status.get("conditions", ()))
    return any(
        condition.get("type") in _ADMITTED_CONDITIONS and condition.get("status") == _ASSERTED
        for condition in conditions
    )
