"""How long GitHub SAID to wait, read out of a refused `gh` invocation.

The seam's backoff schedule was sized from ONE measurement — job 91851854289,
where a `contents` read was still refused 16 seconds after a `repo_metadata`
read had been — and a schedule sized from one observation is a guess about
every other. GitHub does not require the guess: when it throttles, it states
the wait, either as a `Retry-After` header in seconds or as an
`x-ratelimit-reset` UNIX epoch. `livespec-dev-tooling-mmqe` recorded the
consequence of ignoring both: "Honour `Retry-After` / `x-ratelimit-reset`
rather than guessing a backoff — GitHub states the required wait and the
current fix ignores it."

⛔ THE STATED WAIT IS A MINIMUM, NOT A REPLACEMENT. `Retry-After` says "not
before"; it never says "and no longer". The caller therefore takes the LONGER
of the stated wait and its own measured schedule, so a header can only ever
lengthen a wait. A reading that let a small stated value SHORTEN the schedule
would hand the limiter back the tight retry loop the schedule exists to
prevent.

This module is the parser alone — no clock of its own, no sleeping, no
knowledge of the schedule it informs. `now_epoch` and `ceiling_seconds` arrive
as data so the schedule stays declared in one place (`_gh_runner`) and this
stays testable without a clock.
"""

from __future__ import annotations

import re

__all__: list[str] = [
    "stated_throttle_wait_seconds",
]

# GitHub's DIRECT answer, already in seconds. Preferred when present because it
# needs no clock at all: an `x-ratelimit-reset` reading is only as good as the
# agreement between GitHub's clock and ours, and `Retry-After` is immune to
# that skew.
_RETRY_AFTER = re.compile(r"retry-after:\s*(\d+)", re.IGNORECASE)
# The UNIX epoch at which the current window rolls. Second choice, and a
# DELAY has to be derived from it.
_RESET_EPOCH = re.compile(r"x-ratelimit-reset:\s*(\d+)", re.IGNORECASE)


def _bounded(*, seconds: float, ceiling_seconds: float) -> float:
    """Clamp a stated wait into a range a CI job can actually spend.

    A primary-limit reset can be up to an hour away, and a gate that sleeps an
    hour has not honored anything — it has hung. Clamping keeps the honored
    wait bounded and lets the caller's attempt bound end the run loudly
    instead. The lower clamp matters too: a reset epoch already in the past
    yields a NEGATIVE delay, and a negative sleep raises.
    """
    return min(max(seconds, 0.0), ceiling_seconds)


def stated_throttle_wait_seconds(
    *, stderr: str, now_epoch: float, ceiling_seconds: float
) -> float | None:
    """The wait GitHub stated in `stderr`, or None when it stated none.

    `None` is the honest answer for the common case: `gh` prints the error
    BODY, and headers reach stderr only when the caller asked for them (a
    `-i` / verbose invocation) or GitHub echoed them into the message. The
    caller falls back to its measured schedule, which is why an absent header
    must be distinguishable from a stated zero.
    """
    retry_after = _RETRY_AFTER.search(stderr)
    if retry_after is not None:
        return _bounded(seconds=float(retry_after.group(1)), ceiling_seconds=ceiling_seconds)
    reset = _RESET_EPOCH.search(stderr)
    if reset is None:
        return None
    return _bounded(seconds=float(reset.group(1)) - now_epoch, ceiling_seconds=ceiling_seconds)
