"""Tests for `livespec_dev_tooling/fleet/_credential_preflight.py`.

`livespec-dev-tooling-z4qi`: ONE transient credential rejection surfaced as
NINE blind obligation rows and reddened master on a commit that changed
nothing. The token WAS minted — the run's own log shows
`actions/create-github-app-token` completing and exporting it — and the reads
failed ~3x FASTER than the passing re-run, which rules out a stall and points
at a freshly-minted App token being rejected outright for a few seconds.

The fix is to reach the "cannot see" verdict ONCE, deliberately, on a probe,
instead of as N downstream symptoms of one miss. What must NOT change, and is
asserted here: a genuinely unavailable credential still FAILS. No obligation
row is demoted to a warning and no skip lever exists — the escalation of blind
rows to error is a deliberate anti-vacuous-green ruling.
"""

from __future__ import annotations

from _gh_railway import lift_gh

from livespec_dev_tooling.fleet._context import FleetContext, GhResult, GhRunner
from livespec_dev_tooling.fleet._credential_preflight import preflight_credential

__all__: list[str] = []

_FORBIDDEN = GhResult(returncode=1, stdout="", stderr="gh: Resource not accessible (HTTP 403)")
_OK = GhResult(returncode=0, stdout='{"rate": {"remaining": 4999}}', stderr="")


def _scripted(*, results: list[GhResult], calls: list[int]) -> GhRunner:
    """A runner replaying `results` in order, then repeating the last one."""

    def run(*, args: list[str], stdin: str | None = None) -> GhResult:  # noqa: ARG001
        index = min(calls[0], len(results) - 1)
        calls[0] += 1
        return results[index]

    return lift_gh(run)


def _sleeps() -> tuple[list[float], object]:
    recorded: list[float] = []

    def fake_sleep(seconds: float) -> None:
        recorded.append(seconds)

    return recorded, fake_sleep


def test_a_transient_rejection_recovers_without_operator_intervention() -> None:
    """Rejected once, accepted on retry — the z4qi scenario, now a pass."""
    calls = [0]
    recorded, fake_sleep = _sleeps()
    ctx = FleetContext(
        owner="thewoolleyman", run_gh=_scripted(results=[_FORBIDDEN, _OK], calls=calls)
    )

    outcome = preflight_credential(ctx=ctx, sleep=fake_sleep)

    assert outcome.usable, f"a token accepted on retry must be usable; got {outcome!r}"
    assert calls[0] == 2, f"expected one retry, got {calls[0]} attempts"
    assert recorded, "a retry must back off rather than hammer the API"


def test_a_persistently_unavailable_credential_still_fails() -> None:
    """The gate is NOT relaxed: a real blind spot must still red the run."""
    calls = [0]
    _, fake_sleep = _sleeps()
    ctx = FleetContext(owner="thewoolleyman", run_gh=_scripted(results=[_FORBIDDEN], calls=calls))

    outcome = preflight_credential(ctx=ctx, sleep=fake_sleep)

    assert not outcome.usable, "a persistently rejected credential must not be reported usable"
    assert outcome.cause is not None, "the failure must name a cause, not just fail"
    assert outcome.cause.kind == "forbidden", f"got {outcome.cause.kind!r}"


def test_retries_are_bounded() -> None:
    """An outage must not spin: the verdict is reached in bounded time."""
    calls = [0]
    recorded, fake_sleep = _sleeps()
    ctx = FleetContext(owner="thewoolleyman", run_gh=_scripted(results=[_FORBIDDEN], calls=calls))

    _ = preflight_credential(ctx=ctx, sleep=fake_sleep)

    assert calls[0] <= 5, f"unbounded retry: {calls[0]} attempts"
    assert len(recorded) == calls[0] - 1, "one backoff between each pair of attempts"


def test_a_not_found_is_not_retried() -> None:
    """404 carries real information — the thing is absent — so retrying is wrong.

    This is exactly the distinction `livespec-dev-tooling-s22c5z` preserved the
    cause for. Retrying a 404 would burn the budget on a question already
    answered.
    """
    calls = [0]
    _, fake_sleep = _sleeps()
    not_found = GhResult(returncode=1, stdout="", stderr="gh: Not Found (HTTP 404)")
    ctx = FleetContext(owner="thewoolleyman", run_gh=_scripted(results=[not_found], calls=calls))

    outcome = preflight_credential(ctx=ctx, sleep=fake_sleep)

    assert not outcome.usable
    assert calls[0] == 1, f"a non-retryable cause must not be retried; got {calls[0]} attempts"


def test_a_usable_credential_probes_once_and_does_not_sleep() -> None:
    """The normal path costs one cheap authenticated call and no delay."""
    calls = [0]
    recorded, fake_sleep = _sleeps()
    ctx = FleetContext(owner="thewoolleyman", run_gh=_scripted(results=[_OK], calls=calls))

    outcome = preflight_credential(ctx=ctx, sleep=fake_sleep)

    assert outcome.usable
    assert calls[0] == 1, f"the happy path must probe once; got {calls[0]}"
    assert recorded == [], "the happy path must not sleep"
