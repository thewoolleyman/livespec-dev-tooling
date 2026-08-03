"""Rate-shaping at the `gh` seam: a retryable rejection is retried, bounded.

`check-fleet-conformance` sweeps nine members through ONE seam
(`default_gh_runner`). GitHub's SECONDARY rate limiter trips partway through
that sequential pass — measured 2026-08-03: a quiet period and a freshly minted
installation token still exited 4, and the LONGER traversal went blinder
(`blind_rows` 2 in CI vs 12 direct), which is the signature of a limit engaging
mid-pass rather than a spent quota. Every row after the trip reads as blind, so
the gate red-lights with `own_failing_rows=[]` and `error_findings=0` — it
cannot look, and says so in a form indistinguishable from a real finding.

The repo already answers this shape for the credential probe
(`_credential_preflight.preflight_credential`: classify the cause, retry the
retryable ones with bounded backoff). That answer was never applied to the
member traversal, which is where the sweep actually spends its requests.

⚠️ THE WAIT IS OBSERVED BY PATCHING `time.sleep`, NOT BY AN INJECTED PARAMETER.
`default_gh_runner` implements the `GhRunner` Protocol
(`__call__(*, args, stdin=None)`), so widening its signature to take a sleeper
would widen the Protocol every seam consumer is typed against. `import time` +
`time.sleep(...)` resolves the attribute on the shared module object at CALL
time, so patching it here observes the wait without touching the seam's shape.
"""

from __future__ import annotations

import subprocess
import time
from typing import Any

import pytest
from returns.io import IOFailure, IOSuccess
from returns.unsafe import unsafe_perform_io

from livespec_dev_tooling.fleet import _gh_runner
from livespec_dev_tooling.fleet._gh_runner import GhResult, default_gh_runner

__all__: list[str] = []

_RATE_LIMITED_STDERR = (
    "gh: API rate limit exceeded for installation ID 131208965. "
    "If you reach out to GitHub Support for help, please include the request ID "
    "57C1:136940:1DEA138:63DA33E:6A70FCEE (HTTP 403)"
)


class _ScriptedGh:
    """Stand-in for `subprocess.run` returning a scripted sequence of results."""

    def __init__(self, *, script: list[tuple[int, str]]) -> None:
        self._script = script
        self.calls = 0

    def __call__(self, *args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        _ = args
        index = min(self.calls, len(self._script) - 1)
        returncode, stderr = self._script[index]
        self.calls += 1
        return subprocess.CompletedProcess(
            args=list(kwargs.get("args", [])) or ["gh"],
            returncode=returncode,
            stdout="" if returncode else "{}",
            stderr=stderr,
        )


class _RecordingSleep:
    def __init__(self) -> None:
        self.waits: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.waits.append(seconds)


@pytest.fixture
def slept(monkeypatch: pytest.MonkeyPatch) -> _RecordingSleep:
    """Observe every wait the seam takes, and take none of them for real."""
    recorder = _RecordingSleep()
    monkeypatch.setattr(time, "sleep", recorder)
    return recorder


@pytest.fixture(autouse=True)
def _gh_on_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_gh_runner.shutil, "which", lambda _name: "/usr/bin/gh")


def test_a_rate_limited_invocation_is_retried_and_can_succeed(
    monkeypatch: pytest.MonkeyPatch, slept: _RecordingSleep
) -> None:
    """Two 403s then a 200 must answer 200 — the sweep continues instead of going blind."""
    scripted = _ScriptedGh(script=[(1, _RATE_LIMITED_STDERR), (1, _RATE_LIMITED_STDERR), (0, "")])
    monkeypatch.setattr(_gh_runner.subprocess, "run", scripted)

    outcome = default_gh_runner(args=["api", "repos/o/n"])

    assert scripted.calls == 3, "a retryable rejection must be retried, not accepted as blind"
    assert isinstance(outcome, IOSuccess)
    result = unsafe_perform_io(outcome.unwrap())
    assert isinstance(result, GhResult)
    assert result.returncode == 0
    # Backoff must actually wait, and must not shrink — a tight retry loop
    # re-trips the same secondary limiter and is indistinguishable from not
    # retrying at all.
    assert len(slept.waits) == 2
    assert slept.waits == sorted(slept.waits)
    assert slept.waits[0] > 0


def test_retrying_is_bounded_and_returns_the_last_answer(
    monkeypatch: pytest.MonkeyPatch, slept: _RecordingSleep
) -> None:
    """A limiter that never yields must stop, and must not invent an outcome."""
    scripted = _ScriptedGh(script=[(1, _RATE_LIMITED_STDERR)])
    monkeypatch.setattr(_gh_runner.subprocess, "run", scripted)

    outcome = default_gh_runner(args=["api", "repos/o/n"])

    assert 1 < scripted.calls <= 6, "must retry, and must be bounded"
    # One wait BETWEEN each pair of attempts, and none after the last: waiting
    # after giving up would spend the caller's time buying nothing.
    assert len(slept.waits) == scripted.calls - 1
    assert isinstance(outcome, IOSuccess)
    result = unsafe_perform_io(outcome.unwrap())
    assert result.returncode == 1
    assert _RATE_LIMITED_STDERR in result.stderr


def test_a_non_retryable_rejection_is_not_retried(
    monkeypatch: pytest.MonkeyPatch, slept: _RecordingSleep
) -> None:
    """A 404 is an ANSWER. Retrying it burns budget on a settled question."""
    scripted = _ScriptedGh(script=[(1, "gh: Not Found (HTTP 404)")])
    monkeypatch.setattr(_gh_runner.subprocess, "run", scripted)

    outcome = default_gh_runner(args=["api", "repos/o/absent"])

    assert isinstance(outcome, IOSuccess)
    assert scripted.calls == 1
    assert slept.waits == []


def test_an_invocation_that_never_ran_is_not_retried(
    monkeypatch: pytest.MonkeyPatch, slept: _RecordingSleep
) -> None:
    """The failure track means "did not happen" — there is nothing to wait for."""

    def _unspawnable(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        _ = (args, kwargs)
        msg = "no fork"
        raise OSError(msg)

    monkeypatch.setattr(_gh_runner.subprocess, "run", _unspawnable)

    outcome = default_gh_runner(args=["api", "repos/o/n"])

    assert isinstance(outcome, IOFailure)
    assert slept.waits == []
