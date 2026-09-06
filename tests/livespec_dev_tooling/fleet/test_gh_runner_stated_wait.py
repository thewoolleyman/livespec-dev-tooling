"""The traversal must pace itself on GitHub's own terms, not only on a guess.

Two gaps remained after the sweep-wide cooldown landed, both named on
`livespec-dev-tooling-mmqe`:

1. **The backoff was guessed.** Its schedule was sized from ONE observation —
   job 91851854289, a `contents` read still refused 16s after `repo_metadata`
   had been — and a schedule sized from one observation is a guess about every
   other. GitHub states the wait when it throttles (`Retry-After` in seconds,
   or `x-ratelimit-reset` as a UNIX epoch) and the seam ignored both.

2. **Nothing bounded the REQUEST RATE of a healthy pass.** The measured cause
   was never a spent quota: a quiet period and a freshly minted token, with
   `core.remaining=5000`, still exited 4, and the LONGER traversal went blinder
   (`blind_rows` 2 in CI versus 12 direct). That is a limiter engaging PARTWAY
   THROUGH a single sequential pass — provoked by the pass's own burst. A
   cooldown is a reaction to a trip that has already happened; only a floor on
   the gap between requests keeps the pass from causing one.

⛔ THE STATED WAIT IS A MINIMUM. `Retry-After` says "not before"; it never says
"and no longer". Honoring it means never waiting LESS than GitHub asked — so a
header may lengthen a wait and must never shorten the measured schedule, which
would hand the limiter back the tight retry loop that schedule exists to
prevent.
"""

from __future__ import annotations

import importlib
import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from livespec_dev_tooling.fleet import _gh_runner

if TYPE_CHECKING:
    import pytest

__all__: list[str] = []


_MODULE_PATH = (
    Path(__file__).resolve().parents[3] / "livespec_dev_tooling" / "fleet" / "_throttle_signal.py"
)
_MODULE_NAME = "livespec_dev_tooling.fleet._throttle_signal"

_EPOCH_START = 1_800_000_000.0

# Longer than every step of the measured schedule, so honoring it is
# observable rather than masked by a backoff that was already larger.
_STATED_SECONDS = 47

_PLAIN_RATE_LIMITED = (
    "gh: API rate limit exceeded for installation ID 131208965. "
    "If you reach out to GitHub Support for help, please include the request ID "
    "8C30:2D9708:BB87665:C05B3F6:6A6FC1FC (HTTP 403)"
)
_WITH_RETRY_AFTER = f"{_PLAIN_RATE_LIMITED}\nRetry-After: {_STATED_SECONDS}\n"
_WITH_RESET = f"{_PLAIN_RATE_LIMITED}\nx-ratelimit-reset: {int(_EPOCH_START) + _STATED_SECONDS}\n"
_WITH_ABSURD_RESET = f"{_PLAIN_RATE_LIMITED}\nx-ratelimit-reset: {int(_EPOCH_START) + 3600}\n"
_WITH_TINY_RETRY_AFTER = f"{_PLAIN_RATE_LIMITED}\nRetry-After: 1\n"


class _Harness:
    """A fake clock plus an ordered log of what the seam DID.

    `sleep` advances the clock, because a wait that does not move time would
    let a cooldown never expire and would make the request-gap floor fire on
    every retry — both test artefacts rather than behaviours.
    """

    def __init__(self) -> None:
        self.events: list[tuple[str, float]] = []
        self._t = 1000.0
        self._epoch = _EPOCH_START
        self._script: list[tuple[int, str]] = [(0, "")]

    def script(self, *, script: list[tuple[int, str]]) -> None:
        self._script = script

    def monotonic(self) -> float:
        return self._t

    def epoch(self) -> float:
        return self._epoch

    def advance(self, seconds: float) -> None:
        """Move the clock without recording a wait the seam did not take."""
        self._t += seconds
        self._epoch += seconds

    @property
    def calls(self) -> int:
        return sum(1 for kind, _ in self.events if kind == "call")

    @property
    def waits(self) -> list[float]:
        return [seconds for kind, seconds in self.events if kind == "sleep"]

    def run(self, *args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        _ = args
        index = min(self.calls, len(self._script) - 1)
        returncode, stderr = self._script[index]
        self.events.append(("call", self._t))
        return subprocess.CompletedProcess(
            args=list(kwargs.get("args", [])) or ["gh"],
            returncode=returncode,
            stdout="" if returncode else "{}",
            stderr=stderr,
        )

    def sleep(self, seconds: float) -> None:
        self.events.append(("sleep", seconds))
        self.advance(seconds)


def _fixture(monkeypatch: pytest.MonkeyPatch) -> _Harness:
    harness = _Harness()
    monkeypatch.setattr(_gh_runner.shutil, "which", lambda _name: "/usr/bin/gh")
    monkeypatch.setattr(_gh_runner.subprocess, "run", harness.run)
    monkeypatch.setattr(time, "sleep", harness.sleep)
    monkeypatch.setattr(time, "monotonic", harness.monotonic)
    monkeypatch.setattr(time, "time", harness.epoch)
    return harness


def _gap() -> float:
    """The inter-request floor the seam must expose for a caller to reason about."""
    gap = getattr(_gh_runner, "MIN_REQUEST_GAP_SECONDS", None)
    assert gap is not None, (
        "the traversal needs a FLOOR on the gap between requests: the limiter "
        "engages partway through a single sequential pass, so a cooldown alone "
        "only reacts to a trip the pass itself caused"
    )
    return float(gap)


def _backoffs(*, harness: _Harness) -> list[float]:
    """Waits that are BACKOFFS, not the constant inter-request spacing floor."""
    return [seconds for seconds in harness.waits if seconds > _gap()]


def test_a_stated_retry_after_is_honored_over_the_guessed_schedule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GitHub states the wait; a schedule sized from one observation only guesses it."""
    harness = _fixture(monkeypatch)
    harness.script(script=[(1, _WITH_RETRY_AFTER), (0, "")])

    _ = _gh_runner.PacedGhRunner()(args=["api", "repos/o/n"])

    assert (
        max(_backoffs(harness=harness)) >= _STATED_SECONDS
    ), "waiting less than GitHub asked for is not honoring Retry-After"


def test_a_stated_reset_epoch_is_converted_to_a_delay_and_honored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`x-ratelimit-reset` is an epoch, not a duration; the seam must do the arithmetic."""
    harness = _fixture(monkeypatch)
    harness.script(script=[(1, _WITH_RESET), (0, "")])

    _ = _gh_runner.PacedGhRunner()(args=["api", "repos/o/n"])

    assert max(_backoffs(harness=harness)) >= _STATED_SECONDS


def test_a_stated_wait_beyond_the_ceiling_is_clamped(monkeypatch: pytest.MonkeyPatch) -> None:
    """A primary reset can be an hour out. A gate that sleeps an hour has hung, not waited."""
    harness = _fixture(monkeypatch)
    harness.script(script=[(1, _WITH_ABSURD_RESET)])

    _ = _gh_runner.PacedGhRunner()(args=["api", "repos/o/n"])

    assert harness.waits, "a throttled call must still back off"
    assert max(harness.waits) < 3600.0


def test_a_stated_wait_shorter_than_the_schedule_does_not_shorten_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Retry-After is a MINIMUM. Reading it as a replacement restores the tight loop."""
    harness = _fixture(monkeypatch)
    harness.script(script=[(1, _WITH_TINY_RETRY_AFTER)])

    _ = _gh_runner.PacedGhRunner()(args=["api", "repos/o/n"])

    assert (
        sum(harness.waits) >= 16.0
    ), "a 1-second header must not shrink a schedule sized from a 16s measured persistence"


def test_the_sweep_wide_cooldown_adopts_the_stated_wait(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The limiter's subject is the SEQUENCE, so a later row must wait what GitHub stated."""
    harness = _fixture(monkeypatch)
    harness.script(script=[(1, _WITH_RETRY_AFTER)])
    runner = _gh_runner.PacedGhRunner()
    _ = runner(args=["api", "repos/o/n"])

    boundary = len(harness.events)
    harness.script(script=[(0, "")])
    _ = runner(args=["api", "repos/o/m"])

    later = harness.events[boundary:]
    assert later[0][0] == "sleep", "a later row must wait the stated window out"


def test_a_healthy_pass_holds_a_floor_on_the_gap_between_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The trip is caused by the pass's own burst, so an UNTHROTTLED pass must be paced."""
    harness = _fixture(monkeypatch)
    harness.script(script=[(0, "")])
    runner = _gh_runner.PacedGhRunner()

    _ = runner(args=["api", "repos/o/n"])
    _ = runner(args=["api", "repos/o/m"])

    call_times = [when for kind, when in harness.events if kind == "call"]
    assert len(call_times) == 2
    assert call_times[1] - call_times[0] >= _gap(), (
        "two back-to-back reads with no gap between them are the burst that "
        "engages the secondary limiter"
    )
    assert _backoffs(harness=harness) == [], "a healthy pass must not pay a BACKOFF"


def test_the_gap_is_a_floor_and_not_a_tax(monkeypatch: pytest.MonkeyPatch) -> None:
    """A caller that already waited must not wait again — pacing is a rate, not a toll."""
    harness = _fixture(monkeypatch)
    harness.script(script=[(0, "")])
    runner = _gh_runner.PacedGhRunner()
    _ = runner(args=["api", "repos/o/n"])

    harness.advance(_gap() * 10)
    boundary = len(harness.events)
    _ = runner(args=["api", "repos/o/m"])

    assert [kind for kind, _ in harness.events[boundary:]] == ["call"]


def _stated_wait() -> Any:
    """The parser under test, imported INSIDE the body.

    A top-level import of a module that does not exist yet dies at COLLECTION,
    which proves only unimportability. Asserting the file first makes the Red a
    genuine assertion about a module that is missing.
    """
    assert _MODULE_PATH.is_file(), f"{_MODULE_PATH} carries the stated-wait parser"
    return importlib.import_module(_MODULE_NAME).stated_throttle_wait_seconds


def test_a_body_stating_no_wait_answers_none_rather_than_zero() -> None:
    """`gh` prints the error BODY; headers usually never reach it.

    An absent header and a stated zero must not collapse: the caller falls back
    to its measured schedule on the first and would skip the wait on the second.
    """
    stated_throttle_wait_seconds = _stated_wait()

    assert (
        stated_throttle_wait_seconds(
            stderr=_PLAIN_RATE_LIMITED, now_epoch=_EPOCH_START, ceiling_seconds=62.0
        )
        is None
    )


def test_retry_after_wins_over_a_reset_epoch_when_both_are_present() -> None:
    """`Retry-After` needs no clock, so it is immune to skew between GitHub's and ours."""
    stated_throttle_wait_seconds = _stated_wait()
    both = f"{_PLAIN_RATE_LIMITED}\nRetry-After: 7\nx-ratelimit-reset: {int(_EPOCH_START) + 40}\n"

    assert (
        stated_throttle_wait_seconds(stderr=both, now_epoch=_EPOCH_START, ceiling_seconds=62.0)
        == 7.0
    )


def test_a_reset_epoch_already_past_yields_zero_and_never_a_negative() -> None:
    """A negative delay would raise out of `time.sleep` and kill the sweep mid-pass."""
    stated_throttle_wait_seconds = _stated_wait()
    stale = f"{_PLAIN_RATE_LIMITED}\nx-ratelimit-reset: {int(_EPOCH_START) - 90}\n"

    assert (
        stated_throttle_wait_seconds(stderr=stale, now_epoch=_EPOCH_START, ceiling_seconds=62.0)
        == 0.0
    )
