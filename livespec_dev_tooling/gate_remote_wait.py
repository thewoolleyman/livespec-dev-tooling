"""Bounded admission and runtime polling for submitted gate Jobs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from returns.result import Failure, Result, Success

from livespec_dev_tooling.gate_remote_invocation import (
    GateCommandRunner,
    GateStepFailed,
    Sleeper,
    require_success,
)
from livespec_dev_tooling.gate_remote_job_status import (
    Terminal,
    job_admitted,
    terminal_condition,
    unreadable,
)

__all__: list[str] = ["GateWaitRequest", "await_terminal_state"]

_AWAIT_STEP = "await-gate-terminal"


@dataclass(frozen=True, kw_only=True)
class GateWaitRequest:
    """The submitted Job and the two independent bounds that govern its wait."""

    kubectl: tuple[str, ...]
    repo_root: Path
    job_name: str
    poll_interval_seconds: float
    admission_timeout_seconds: float
    runtime_timeout_seconds: float


def await_terminal_state(
    *, request: GateWaitRequest, runner: GateCommandRunner, sleeper: Sleeper
) -> Result[Terminal, GateStepFailed]:
    """Wait separately for Kueue admission and the admitted Job's runtime."""
    argv = [*request.kubectl, "get", "job", request.job_name, "--output", "json"]
    admission_polls_left = max(
        1, int(request.admission_timeout_seconds // request.poll_interval_seconds)
    )
    runtime_polls_left = max(
        1, int(request.runtime_timeout_seconds // request.poll_interval_seconds)
    )
    admitted = False
    while True:
        lifted = require_success(
            step=_AWAIT_STEP, argv=argv, outcome=runner(argv=argv, cwd=request.repo_root)
        )
        if isinstance(lifted, Failure):
            return Failure(lifted.failure())
        condition = terminal_condition(argv=argv, payload=lifted.unwrap().stdout, step=_AWAIT_STEP)
        if isinstance(condition, Failure):
            return Failure(condition.failure())
        ended = condition.unwrap()
        if ended is not None:
            return Success(ended)
        if job_admitted(payload=lifted.unwrap().stdout):
            admitted = True
        if admitted:
            runtime_polls_left -= 1
            if runtime_polls_left == 0:
                return Failure(
                    unreadable(
                        step=_AWAIT_STEP,
                        argv=argv,
                        detail=(
                            f"{request.job_name} reached no terminal condition within "
                            f"{request.runtime_timeout_seconds:g}s after admission"
                        ),
                    )
                )
        else:
            admission_polls_left -= 1
            if admission_polls_left == 0:
                return Failure(
                    unreadable(
                        step=_AWAIT_STEP,
                        argv=argv,
                        detail=(
                            f"{request.job_name} was not admitted within "
                            f"{request.admission_timeout_seconds:g}s"
                        ),
                    )
                )
        sleeper(seconds=request.poll_interval_seconds)
