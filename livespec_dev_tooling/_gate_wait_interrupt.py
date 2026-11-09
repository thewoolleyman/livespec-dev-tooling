"""Clean up a submitted gate Job when a signal stops the client's wait.

`gate-run.sh`'s stall window ends a silent gate with `kill -TERM`, and Python's
default TERM action exits without running `finally` blocks. A client killed that
way never reached its Job deletion, so the Job stayed queued and ran for no one
while each retry submitted another. The handler installed here runs the caller's
cleanup in the signal's own frame, then stops the wait with a typed error the
caller turns into the ordinary no-verdict ending.
"""

from __future__ import annotations

import signal
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from livespec_dev_tooling.gate_remote_invocation import GateStepFailed
from livespec_dev_tooling.gate_remote_job_status import Terminal

# `returns` is VENDORED, not installed; a bare import here would resolve only
# when some earlier import in the process happened to run first.
_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.result import Result  # noqa: E402  — vendor-path-aware import.

__all__: list[str] = [
    "GateWaitInterruptedError",
    "interrupted_wait_failure",
    "wait_with_interrupt_cleanup",
]

_AWAIT_STEP = "await-gate-terminal"


class GateWaitInterruptedError(Exception):
    """A signal stopped a wait after its caller cleaned up the submitted Job."""

    def __init__(self, *, job_name: str, signal_name: str) -> None:
        super().__init__(f"{job_name} wait interrupted by {signal_name}")
        self.job_name = job_name
        self.signal_name = signal_name


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


def wait_with_interrupt_cleanup(
    *,
    job_name: str,
    cleanup: Callable[[], None],
    wait: Callable[[], Result[Terminal, GateStepFailed]],
) -> Result[Terminal, GateStepFailed]:
    """Run `wait` while TERM and INT call `cleanup`, then raise `GateWaitInterruptedError`."""
    interrupted = _InterruptCleanup(job_name=job_name, cleanup=cleanup)
    previous_term = signal.signal(signal.SIGTERM, interrupted)
    previous_int = signal.signal(signal.SIGINT, interrupted)
    try:
        return wait()
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
            f"{interrupted.signal_name}; the client deleted that Job and its published "
            "mirror refs before exiting (a refused delete is reported separately)"
        ),
    )
