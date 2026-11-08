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
from types import FrameType
from typing import TypeAlias

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
            waiting_state = "(queued for admission or running)"
            prefix = f":: gate: {self.job_name} not finished yet, waited {int(self.elapsed)}s "
            message = f"{prefix}{waiting_state}\n"
            _ = sys.stderr.write(message)


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


_SignalHandler: TypeAlias = Callable[[int, FrameType | None], object] | int | signal.Handlers | None
_SignalInstaller: TypeAlias = Callable[[int | signal.Signals, _SignalHandler], _SignalHandler]


def _await_terminal_state(*, context: GateWaitContext) -> Result[Terminal, GateStepFailed]:
    """Poll the Job until it reports a terminal condition, or give up."""
    argv = context.poll_argv
    last_refusal: GateStepFailed | None = None
    nap = reporting_sleeper(sleeper=context.sleeper, job_name=context.job_name)
    for poll in range(context.request.poll_budget()):
        if poll:
            nap(seconds=context.request.poll_interval_seconds)
        lifted = require_success(
            step="await-gate-terminal",
            argv=argv,
            outcome=context.runner(argv=argv, cwd=context.request.repo_root),
        )
        if isinstance(lifted, Failure):
            last_refusal = lifted.failure()
            continue
        condition = terminal_condition(
            argv=argv, payload=lifted.unwrap().stdout, step="await-gate-terminal"
        )
        if isinstance(condition, Failure):
            return Failure(condition.failure())
        ended = condition.unwrap()
        if ended is not None:
            return Success(ended)
    if last_refusal is not None:
        return Failure(last_refusal)
    detail = (
        f"{context.job_name} reached no terminal condition within "
        f"{context.request.poll_timeout_seconds:g}s"
    )
    return Failure(unreadable(step="await-gate-terminal", argv=argv, detail=detail))


def await_terminal_state_with_interrupt_cleanup(
    *,
    context: GateWaitContext,
    cleanup: Callable[[], None],
    signal_install: _SignalInstaller,
    term_signal: signal.Signals,
    int_signal: signal.Signals,
) -> Result[Terminal, GateStepFailed]:
    """Wait while TERM and INT clean up the submitted Job and its mirror refs."""

    def interrupted(*, signal_number: int) -> None:
        cleanup()
        signal_name = "SIGTERM" if signal_number == term_signal else "SIGINT"
        raise GateWaitInterruptedError(job_name=context.job_name, signal_name=signal_name)

    previous_term = signal_install(
        term_signal,
        lambda signal_number, _frame: interrupted(signal_number=signal_number),
    )
    previous_int = signal_install(
        int_signal,
        lambda signal_number, _frame: interrupted(signal_number=signal_number),
    )
    try:
        return _await_terminal_state(context=context)
    finally:
        _ = signal_install(term_signal, previous_term)
        _ = signal_install(int_signal, previous_int)


def interrupted_wait_failure(*, interrupted: GateWaitInterruptedError) -> GateStepFailed:
    """Render a terminated wait as the ordinary no-verdict failure."""
    return GateStepFailed(
        step="await-gate-terminal",
        argv=(),
        returncode=None,
        detail=(
            f"waiting for gate Job {interrupted.job_name} was terminated by "
            f"{interrupted.signal_name}; its Job and published mirror refs were deleted"
        ),
    )
