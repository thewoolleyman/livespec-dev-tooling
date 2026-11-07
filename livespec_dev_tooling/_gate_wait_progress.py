"""The delegated gate's once-a-minute progress line while it waits for its Job.

The detached gate runner ends a gate that prints nothing for its stall window
(900 s by default), and a Job queued for Kueue admission on a busy fleet prints
nothing of its own, so without this line the runner ended such a gate with no
verdict (livespec-dev-tooling-2f3yy). `gate_remote_client` sleeps between polls
through the sleeper this returns.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import dataclass

__all__: list[str] = ["reporting_sleeper"]

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
