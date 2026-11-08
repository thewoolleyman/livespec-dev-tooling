"""The delegated gate's once-a-minute progress line while it waits for its Job.

The detached gate runner ends a gate that prints nothing for its stall window
(900 s by default), and a Job queued for Kueue admission on a busy fleet prints
nothing of its own, so without this line the runner ended such a gate with no
verdict (livespec-dev-tooling-2f3yy). `gate_remote_client` sleeps between polls
through the sleeper this returns.
"""

from __future__ import annotations

import signal
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

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

__all__: list[str] = [
    "GateWaitContext",
    "GateWaitInterruptedError",
    "await_terminal_state_with_interrupt_cleanup",
    "interrupted_wait_failure",
    "reporting_sleeper",
]

_AWAIT_STEP = "await-gate-terminal"

# Comfortably inside the runner's stall window.
_PROGRESS_EVERY_SECONDS = 60


@dataclass(kw_only=True)
class _WaitProgress:
    """Counts the seconds a wait has slept and says so once each minute."""

    job_name: str
    sleeper: Callable[..., None]
    elapsed: float = 0.0
    reported: int = 0

    def __call__(self, *, seconds: float) -> None:
        self.sleeper(seconds=seconds)
        self.elapsed += seconds
        minutes = int(self.elapsed // _PROGRESS_EVERY_SECONDS)
        if minutes > self.reported:
            self.reported = minutes
            _ = sys.stderr.write(
                f":: gate: {self.job_name} not finished yet, waited {int(self.elapsed)}s"
                " (queued for admission or running)\n"
            )


def reporting_sleeper(*, sleeper: Callable[..., None], job_name: str) -> Callable[..., None]:
    """Wrap `sleeper` so the wait it measures reports progress each minute."""
    return _WaitProgress(job_name=job_name, sleeper=sleeper)


@dataclass(frozen=True, kw_only=True)
class GateWaitContext:
    """The cluster-poll inputs whose lifetime is one submitted gate Job."""

    request: GateRunRequest
    runner: GateCommandRunner
    sleeper: Sleeper
    job_name: str
    poll_argv: list[str]


class GateWaitInterruptedError(Exception):
    """A signal stopped a wait after its caller cleaned up the submitted Job."""

    def __init__(self, *, job_name: str, signal_name: str) -> None:
        self.job_name = job_name
        self.signal_name = signal_name


def _await_terminal_state(*, context: GateWaitContext) -> Result[Terminal, GateStepFailed]:
    """Poll the Job until it reports a terminal condition, or give up.

    A refused read is not evidence that the Job stopped. Kubernetes credentials,
    API availability and the Job's state are independent, so a transient `get`
    refusal is retried within the existing poll budget. If every read is
    refused, the final refusal remains the plumbing failure the caller reports;
    it never authorizes collection of the Job's mirror refs.

    What comes back is the whole terminal STATUS rather than its condition type,
    because the reply that says a Job finished is also the reply that says when
    it ran. Reading those two facts out of one answer is not an economy: the Job
    this wait just watched end is collected after `ttlSecondsAfterFinished`, so
    a later `get` can legitimately find nothing.
    """
    request = context.request
    argv = context.poll_argv
    last_refusal: GateStepFailed | None = None
    polls = request.poll_budget()
    nap = reporting_sleeper(sleeper=context.sleeper, job_name=context.job_name)
    for poll in range(polls):
        if poll:
            nap(seconds=request.poll_interval_seconds)
        lifted = require_success(
            step=_AWAIT_STEP, argv=argv, outcome=context.runner(argv=argv, cwd=request.repo_root)
        )
        if isinstance(lifted, Failure):
            last_refusal = lifted.failure()
            continue
        condition = terminal_condition(argv=argv, payload=lifted.unwrap().stdout, step=_AWAIT_STEP)
        if isinstance(condition, Failure):
            return Failure(condition.failure())
        ended = condition.unwrap()
        if ended is not None:
            return Success(ended)
    if last_refusal is not None:
        return Failure(last_refusal)
    gave_up = (
        f"{context.job_name} reached no terminal condition within {request.poll_timeout_seconds:g}s"
    )
    return Failure(unreadable(step=_AWAIT_STEP, argv=argv, detail=gave_up))


@dataclass(frozen=True, kw_only=True)
class _InterruptCleanup:
    """The TERM/INT handler: cleans up, then stops the wait. The runtime calls it positionally."""

    job_name: str
    cleanup: Callable[[], None]

    def __call__(self, signal_number: int, _frame: object) -> None:
        self.cleanup()
        raise GateWaitInterruptedError(
            job_name=self.job_name, signal_name=signal.Signals(signal_number).name
        )


def await_terminal_state_with_interrupt_cleanup(
    *, context: GateWaitContext, cleanup: Callable[[], None]
) -> Result[Terminal, GateStepFailed]:
    """Wait while TERM and INT clean up the submitted Job and its mirror refs."""
    interrupted = _InterruptCleanup(job_name=context.job_name, cleanup=cleanup)
    previous_term = signal.signal(signal.SIGTERM, interrupted)
    previous_int = signal.signal(signal.SIGINT, interrupted)
    try:
        return _await_terminal_state(context=context)
    finally:
        _ = signal.signal(signal.SIGTERM, previous_term)
        _ = signal.signal(signal.SIGINT, previous_int)


def interrupted_wait_failure(*, interrupted: GateWaitInterruptedError) -> GateStepFailed:
    """Render a terminated wait as the ordinary no-verdict failure."""
    return GateStepFailed(
        step=_AWAIT_STEP,
        argv=(),
        returncode=None,
        detail=(
            f"waiting for gate Job {interrupted.job_name} was terminated by "
            f"{interrupted.signal_name}; its Job and published mirror refs were deleted"
        ),
    )
