"""Wait for Kueue admission before spending a delegated gate's run budget.

Kueue keeps a queued Job suspended. That wait is queueing, not execution, so it
has a bound of its own and does not consume the bound for the Job's terminal
state. Admission uses the existing `Sleeper` seam; terminal waiting instead
uses one bounded watch and re-arms it only after a transient watch failure.
"""

from __future__ import annotations

import json
import math
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

from livespec_dev_tooling._gate_wait_progress import reporting_sleeper
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
_WATCH_NO_TERMINAL_DETAIL = "Job watch ended before a terminal condition was observed"
_WATCH_TERMINAL_SCRIPT = r"""
set -eu
job_name=$1
namespace=$2
timeout=$3
kubectl --namespace "$namespace" get job "$job_name" --watch --output json --timeout "$timeout" |
python3 -c '
import json
import sys

decoder = json.JSONDecoder()
buffer = ""
while chunk := sys.stdin.read(1):
    buffer += chunk
    document_text = buffer.lstrip()
    if not document_text:
        buffer = ""
        continue
    try:
        document, end = decoder.raw_decode(document_text)
    except json.JSONDecodeError:
        continue
    buffer = document_text[end:]
    conditions = document.get("status", {}).get("conditions", ())
    if any(
        condition.get("status") == "True"
        and condition.get("type") in {"Complete", "Failed"}
        for condition in conditions
    ):
        print(json.dumps(document))
        raise SystemExit(0)
raise SystemExit("Job watch ended before a terminal condition was observed")
'
""".strip()


def await_terminal_state(
    *, request: GateRunRequest, runner: GateCommandRunner, sleeper: Sleeper, job_name: str
) -> Result[Terminal, GateStepFailed]:
    """Wait through admission, then watch the Job within its independent budget."""
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
    nap = reporting_sleeper(sleeper=sleeper, job_name=job_name)
    admitted = _await_admission(
        argv=argv,
        request=request,
        runner=runner,
        sleeper=nap,
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
        sleeper=nap,
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
    last_refusal: GateStepFailed | None = None
    polls = request.admission_poll_budget()
    for poll in range(polls):
        if poll:
            sleeper(seconds=request.poll_interval_seconds)
        read = require_success(
            step=_AWAIT_STEP,
            argv=argv,
            outcome=runner(argv=argv, cwd=request.repo_root),
        )
        if isinstance(read, Failure):
            last_refusal = read.failure()
        else:
            last_refusal = None
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
    if last_refusal is not None:
        return Failure(last_refusal)
    return Failure(
        unreadable(
            step=_AWAIT_STEP,
            argv=argv,
            detail=(
                f"admission wait for {job_name} exceeded "
                f"{request.admission_timeout_seconds:g}s: {job_name} was not admitted"
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
    """Watch an admitted Job, re-arming only after a transient watch failure."""
    last_refusal: GateStepFailed | None = None
    deadline = time.monotonic() + request.poll_timeout_seconds
    attempts = request.poll_budget()
    for attempt in range(attempts):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        watch_argv = [
            *with_gates_kubeconfig(argv=["sh", "-ceu", _WATCH_TERMINAL_SCRIPT]),
            "await-gate-terminal-watch",
            job_name,
            request.namespace,
            f"{max(1, math.ceil(remaining))}s",
        ]
        read = require_success(
            step=_AWAIT_STEP,
            argv=watch_argv,
            outcome=runner(argv=watch_argv, cwd=request.repo_root),
        )
        if isinstance(read, Failure):
            refusal = read.failure()
            last_refusal = None if refusal.detail.strip() == _WATCH_NO_TERMINAL_DETAIL else refusal
        else:
            terminal = terminal_condition(
                argv=watch_argv,
                payload=read.unwrap().stdout,
                step=_AWAIT_STEP,
            )
            if isinstance(terminal, Failure):
                return Failure(terminal.failure())
            ended = terminal.unwrap()
            if ended is not None:
                return Success(ended)
        if attempt + 1 < attempts and deadline > time.monotonic():
            sleeper(seconds=min(request.poll_interval_seconds, deadline - time.monotonic()))
    if last_refusal is not None:
        return Failure(last_refusal)
    gave_up = (
        f"{job_name} was admitted but reached no terminal condition "
        f"within {request.poll_timeout_seconds:g}s"
    )
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
