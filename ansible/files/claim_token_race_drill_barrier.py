"""The barrier half of `claim_token_race_drill_probe.py`: the go signal and the paused client.

`wait_for_go` blocks on the drill's go FIFO until the instant it names arrives
on this host's clock. `BarrierClient` wraps the released package's client and
pauses once, at the first conditional close, so both writers reach the
compare-and-swap before either is released; every close and every successor it
sees is traced for the read-back.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

__all__: list[str] = ["BarrierClient", "BarrierMissedError", "wait_for_go"]

_BARRIER_TOLERANCE_SECONDS = 5.0


class BarrierMissedError(Exception):
    """The go signal named an instant already past when it was read."""


def wait_for_go(*, fifo: Path, clock: Callable[[], float] = time.time) -> float:
    """Block on the go FIFO; return once its instant arrives on this host's clock.

    The instant is compared on THIS host's clock, so a miss names three
    readings a second run can be diagnosed from: the instant the play named,
    this host's clock when the signal arrived, and the clock when it gave up.
    """
    opened_at = clock()
    signal = fifo.read_text(encoding="utf-8").strip()
    arrived_at = clock()
    if signal == "now":
        return arrived_at
    at = float(signal.split()[1])
    if arrived_at - at > _BARRIER_TOLERANCE_SECONDS:
        msg = (
            f"go signal named instant {at:.3f}; this host's clock read {arrived_at:.3f} when it "
            f"arrived ({arrived_at - at:.1f}s past the instant, tolerance "
            f"{_BARRIER_TOLERANCE_SECONDS:.0f}s); the FIFO was opened at {opened_at:.3f}; "
            f"gave up at {clock():.3f}"
        )
        raise BarrierMissedError(msg)
    while (remaining := at - clock()) > 0:
        time.sleep(min(remaining, 0.05))
    return clock()


class BarrierClient:
    """The package's client, paused once at its first conditional close.

    Every verb is the inner client's. The first `close_issue_without_verdict`
    — the compare-and-swap on the contested token — waits for the go signal,
    and every close plus every successor the writer creates is traced so the
    read-back can name the loser's attempted reason and discarded successor.
    """

    def __init__(self, *, inner: Any, barrier: Callable[[], float] | None, trace: dict[str, Any]):
        self._inner = inner
        self._barrier = barrier
        self._trace = trace
        trace.setdefault("closes", [])
        trace.setdefault("successors_created", [])

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def create_no_history_issue(self, *, title: str, description: str) -> str:
        created = self._inner.create_no_history_issue(title=title, description=description)
        self._trace["successors_created"].append(created)
        return created

    def close_issue_without_verdict(self, *, issue_id: str, reason: str) -> None:
        if not self._trace["closes"] and self._barrier is not None:
            self._trace["released_at"] = self._barrier()
        self._trace["closes"].append({"token": issue_id, "reason": reason, "at": time.time()})
        self._inner.close_issue_without_verdict(issue_id=issue_id, reason=reason)
