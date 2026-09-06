"""Pacing across the whole sweep, grounded in a MEASURED throttle duration.

PR #1218 added bounded PER-INVOCATION retry (5 attempts, ~14s). It reduced the
failure rate and did not eliminate it. Two independent occurrences AFTER it
landed:

    PR #1222   job 91851854289   23:58:23Z repo_metadata -> rate_limited
                                 23:58:39Z contents      -> rate_limited
    master d1e994c natural run, job 91850154313 -> check-fleet-conformance
                                 failed, ci-green consequential

The two PR timestamps are the whole argument: **sixteen seconds apart, across
two DIFFERENT operations, both throttled.** So

1. the throttle outlives a 14s per-call schedule, and
2. the second call rediscovered a throttle the first had already found —
   because nothing carried that knowledge between invocations.

Per-call retry cannot fix (2) however long its schedule: the limiter's subject
is the SEQUENCE, so once any row is throttled every later row starts throttled
and burns its own budget learning that. That is what makes a throttled run
slower without making it greener.

⛔ THE STATE MUST BE OWNED BY AN OBJECT, NOT BY THE MODULE. `check-global-writes`
bans `global`/`nonlocal` outright — "state flows down via parameters, up via
return values, never through scoped mutation" — so a module-level cooldown
mutated from a function is not available here, and evading that with a
module-level mutable container would satisfy the checker while breaking the
rule it enforces. `GhRunner` is a Protocol over `__call__`, so an INSTANCE
satisfies it and can own the cooldown. That also makes these tests
order-independent by construction: each builds its own runner, so no test can
leak a cooldown into any other.
"""

from __future__ import annotations

import subprocess
import time
from typing import Any

import pytest
from returns.io import IOSuccess

from livespec_dev_tooling.fleet import _gh_runner
from livespec_dev_tooling.fleet._gh_runner import GhOutcome, default_gh_runner

__all__: list[str] = []

# The measured persistence from job 91851854289. Any bounded schedule that gives
# up sooner is guaranteed to surrender while still throttled.
_MEASURED_THROTTLE_PERSISTENCE_SECONDS = 16.0

_RATE_LIMITED_STDERR = (
    "gh: API rate limit exceeded for installation ID 131208965. "
    "If you reach out to GitHub Support for help, please include the request ID "
    "57C1:136940:1DEA138:63DA33E:6A70FCEE (HTTP 403)"
)


class _Harness:
    """A fake clock plus an ordered log of what the seam DID."""

    def __init__(self) -> None:
        self.events: list[tuple[str, float]] = []
        self._t = 1000.0
        self._script: list[tuple[int, str]] = [(0, "")]

    def script(self, *, script: list[tuple[int, str]]) -> None:
        self._script = script

    def monotonic(self) -> float:
        return self._t

    def advance(self, seconds: float) -> None:
        """Move the clock without recording a wait the seam did not take."""
        self._t += seconds

    @property
    def calls(self) -> int:
        return sum(1 for kind, _ in self.events if kind == "call")

    @property
    def waits(self) -> list[float]:
        return [seconds for kind, seconds in self.events if kind == "sleep"]

    @property
    def backoffs(self) -> list[float]:
        """Waits that are BACKOFFS, apart from the constant inter-request floor.

        The seam holds a floor on the gap between requests as well as a cooldown
        on a throttle, and the two are different claims: a backoff says "GitHub
        refused", the floor says "this pass must not burst". A test asserting
        "no wait" would now conflate them and read a healthy paced sweep as a
        throttled one.
        """
        return [seconds for seconds in self.waits if seconds > _gh_runner.MIN_REQUEST_GAP_SECONDS]

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
        # A wait that does not advance the clock would let a cooldown never
        # expire, which is a test artefact rather than a behaviour.
        self._t += seconds


def _kinds_apart_from_the_floor(*, events: list[tuple[str, float]]) -> list[str]:
    """Event kinds over a SLICE of a run, with the inter-request floor removed.

    A free function rather than a harness property because every caller asks it
    about a slice — "what did the seam do AFTER this point" — and a property
    would have to be borrowed from a throwaway harness to answer that.
    """
    return [
        kind
        for kind, seconds in events
        if kind != "sleep" or seconds > _gh_runner.MIN_REQUEST_GAP_SECONDS
    ]


@pytest.fixture
def gh(monkeypatch: pytest.MonkeyPatch) -> _Harness:
    """Hermetic seam: fake `gh` and a fake clock. No shared pacing state to reset."""
    harness = _Harness()
    monkeypatch.setattr(_gh_runner.shutil, "which", lambda _name: "/usr/bin/gh")
    monkeypatch.setattr(_gh_runner.subprocess, "run", harness.run)
    monkeypatch.setattr(time, "sleep", harness.sleep)
    monkeypatch.setattr(time, "monotonic", harness.monotonic)
    return harness


def _paced_runner() -> Any:
    """A FRESH runner, so no test can inherit another's cooldown.

    Asserted rather than imported at module scope so this fails as a stated
    requirement instead of an ImportError.
    """
    factory = getattr(_gh_runner, "PacedGhRunner", None)
    assert factory is not None, (
        "cross-invocation pacing needs an OBJECT to own the cooldown: "
        "check-global-writes bans module-level mutable state"
    )
    return factory()


def test_the_default_runner_carries_the_pacing(gh: _Harness) -> None:
    """A paced runner nobody uses would fix nothing — the DEFAULT must be one."""
    _ = gh
    factory = getattr(_gh_runner, "PacedGhRunner", None)
    assert factory is not None, "the seam exposes no paced runner"
    assert isinstance(default_gh_runner, factory), (
        "default_gh_runner is what every FleetContext injects; if it is not the "
        "paced runner, the sweep gets none of this"
    )


def test_the_bounded_schedule_outlasts_the_measured_throttle(gh: _Harness) -> None:
    """Giving up before the throttle lifts guarantees surrendering while throttled."""
    runner = _paced_runner()
    gh.script(script=[(1, _RATE_LIMITED_STDERR)])

    outcome: GhOutcome = runner(args=["api", "repos/o/n"])

    assert isinstance(outcome, IOSuccess)
    assert sum(gh.waits) >= _MEASURED_THROTTLE_PERSISTENCE_SECONDS, (
        f"total bounded wait {sum(gh.waits)}s gives up before the throttle was "
        f"measured to persist ({_MEASURED_THROTTLE_PERSISTENCE_SECONDS}s)"
    )


def test_a_later_call_waits_out_a_throttle_an_earlier_one_hit(gh: _Harness) -> None:
    """The limiter's subject is the SEQUENCE, so the runner must carry what it learned.

    In job 91851854289 `contents` was thrown at GitHub 16s after `repo_metadata`
    had already been refused, and was refused in turn. Per-call retry cannot
    prevent that at ANY schedule length; only state outliving the call can.
    """
    runner = _paced_runner()
    gh.script(script=[(1, _RATE_LIMITED_STDERR)])
    _ = runner(args=["api", "repos/thewoolleyman/livespec"])

    boundary = len(gh.events)
    gh.script(script=[(0, "")])
    _ = runner(args=["api", "repos/thewoolleyman/livespec/contents/x"])

    later = gh.events[boundary:]
    assert later, "the second call did nothing at all"
    assert later[0][0] == "sleep", (
        "a later call must wait out a throttle the sweep already hit, instead "
        "of spending a request to rediscover it"
    )


def test_pacing_does_not_penalise_an_unthrottled_sweep(gh: _Harness) -> None:
    """A healthy sweep must not pay for a throttle that never happened.

    It DOES pay the inter-request floor, and that is a different claim: the
    limiter engages partway through a single sequential pass, so a healthy pass
    is exactly the one that must not burst. What it must never pay is a
    BACKOFF — the price of a refusal it never received.
    """
    runner = _paced_runner()
    gh.script(script=[(0, "")])

    _ = runner(args=["api", "repos/o/n"])
    _ = runner(args=["api", "repos/o/m"])

    assert gh.backoffs == []
    assert gh.calls == 2


def test_a_lifted_cooldown_does_not_delay_later_calls(gh: _Harness) -> None:
    """The cooldown must EXPIRE. A pause that never lifts is a stalled sweep."""
    runner = _paced_runner()
    gh.script(script=[(1, _RATE_LIMITED_STDERR)])
    _ = runner(args=["api", "repos/o/n"])

    gh.advance(600.0)
    boundary = len(gh.events)
    gh.script(script=[(0, "")])
    _ = runner(args=["api", "repos/o/m"])

    assert [kind for kind, _ in gh.events[boundary:]] == ["call"]


def test_a_server_error_retries_but_does_not_pace_the_sweep(gh: _Harness) -> None:
    """A 500 earns a retry; it does NOT earn a sweep-wide cooldown.

    Only `rate_limited` is a statement about the SEQUENCE. GitHub failing to
    answer one question says nothing about whether the next row would be
    refused, so pausing every later row on it would spend real time for nothing.
    """
    runner = _paced_runner()
    gh.script(script=[(1, "gh: Internal Server Error (HTTP 500)"), (0, "")])
    _ = runner(args=["api", "repos/o/n"])
    assert gh.calls == 2, "a server error is retryable"

    boundary = len(gh.events)
    gh.script(script=[(0, "")])
    _ = runner(args=["api", "repos/o/m"])

    assert _kinds_apart_from_the_floor(events=gh.events[boundary:]) == ["call"], (
        "a server error must not arm the sweep-wide cooldown (the inter-request "
        "floor is filtered out: it is paid by every pass, throttled or not)"
    )
