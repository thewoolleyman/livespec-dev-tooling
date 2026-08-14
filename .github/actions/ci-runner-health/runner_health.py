"""Fail-closed, bounded GitHub Actions self-hosted runner health probe.

This script is part of a composite Action rather than the installable package:
the reusable workflow must be able to run it before it has checked out or
installed a caller repository.  It deliberately makes ONE ``per_page=100``
read-only request.  A partial sample can select hosted capacity unnecessarily,
but can never send work to a runner that was not observed healthy.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

_RUNNERS_PATH = "/repos/{repository}/actions/runners?per_page=100"
_ACCEPT = "application/vnd.github+json"
_API_VERSION = "2022-11-28"


@dataclass(frozen=True)
class ProbeResult:
    """Safe result emitted to the calling reusable workflow.

    ``online_matching`` and ``waited_seconds`` default to 0 so a caller
    (e.g. a test double) that predates the saturation grace window can still
    construct a ``ProbeResult`` without naming every field.
    """

    healthy: bool
    idle_matching: int
    detail: str
    online_matching: int = 0
    waited_seconds: int = 0


def parse_labels(*, raw: str) -> frozenset[str]:
    """Parse one non-empty JSON string array of required labels."""
    try:
        decoded: object = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ValueError from error
    if not isinstance(decoded, list) or not decoded:
        raise ValueError
    if any(not isinstance(label, str) or not label.strip() for label in decoded):
        raise ValueError
    return frozenset(decoded)


def matching_runner_counts(
    *, runners: list[dict[str, Any]], required_labels: frozenset[str]
) -> tuple[int, int]:
    """Count runners carrying every required label, split online vs. idle.

    ``online_matching`` is every online runner with the required labels,
    regardless of busy state; ``idle_matching`` is the subset also not busy.
    The split is what lets a caller distinguish a true outage (zero online)
    from routine saturation (online but none idle).
    """
    online = 0
    idle = 0
    for runner in runners:
        raw_labels = runner.get("labels", [])
        labels = {
            label.get("name")
            for label in raw_labels
            if isinstance(label, dict) and isinstance(label.get("name"), str)
        }
        if runner.get("status") == "online" and required_labels.issubset(labels):
            online += 1
            if runner.get("busy") is False:
                idle += 1
    return online, idle


def idle_matching_runners(*, runners: list[dict[str, Any]], required_labels: frozenset[str]) -> int:
    """Count online, idle runners carrying every required label."""
    _, idle = matching_runner_counts(runners=runners, required_labels=required_labels)
    return idle


def _request_json(*, url: str, token: str) -> dict[str, Any]:
    request = Request(  # noqa: S310 -- GitHub API URL is runner-provided.
        url,
        headers={
            "Accept": _ACCEPT,
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": _API_VERSION,
        },
    )
    with urlopen(request, timeout=10) as response:  # noqa: S310 -- request URL is validated above.
        decoded: object = json.loads(response.read().decode("utf-8"))
    if not isinstance(decoded, dict):
        raise TypeError
    return decoded


def probe(
    *,
    repository: str,
    token: str,
    required_labels: frozenset[str],
    max_wait_seconds: int = 0,
    poll_interval_seconds: int = 15,
    **test_seams: Any,
) -> ProbeResult:
    """Read the bounded runner sample and return a safe health verdict.

    Distinguishes a true outage (zero online runners carrying every required
    label, or an API/parse error — routes hosted immediately, no waiting)
    from routine saturation (at least one online matching runner, but none
    idle — polls on ``poll_interval_seconds`` up to a bounded
    ``max_wait_seconds`` grace window, routing local the moment an idle
    runner is observed, or hosted with a ``saturated-timeout`` detail once
    the window elapses).

    ``opener``, ``sleep``, and ``clock`` are test-injection seams only
    (defaulting to the real HTTP call, ``time.sleep``, and
    ``time.monotonic``); folding them into ``**test_seams`` keeps the
    function under PLR0913's six-argument cap without dropping any of the
    five production-meaningful keyword arguments callers actually vary.
    """
    opener: Callable[..., dict[str, Any]] = test_seams.get("opener", _request_json)
    sleep: Callable[[float], None] = test_seams.get("sleep", time.sleep)
    clock: Callable[[], float] = test_seams.get("clock", time.monotonic)
    api_url = os.environ.get("GITHUB_API_URL", "https://api.github.com").rstrip("/")
    url = f"{api_url}{_RUNNERS_PATH.format(repository=repository)}"
    start = clock()
    while True:
        try:
            payload = opener(url=url, token=token)
            raw_runners = payload.get("runners")
            if not isinstance(raw_runners, list) or not all(
                isinstance(runner, dict) for runner in raw_runners
            ):
                return ProbeResult(
                    healthy=False,
                    idle_matching=0,
                    detail="runner-api-error",
                    waited_seconds=int(clock() - start),
                )
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            # Any expected API/parse failure must route hosted, never queue locally.
            return ProbeResult(
                healthy=False,
                idle_matching=0,
                detail="runner-api-error",
                waited_seconds=int(clock() - start),
            )
        online_matching, idle_matching = matching_runner_counts(
            runners=raw_runners, required_labels=required_labels
        )
        if idle_matching > 0:
            return ProbeResult(
                healthy=True,
                idle_matching=idle_matching,
                online_matching=online_matching,
                detail="idle-runner-observed",
                waited_seconds=int(clock() - start),
            )
        if online_matching == 0:
            # Zero online matching runners is a true outage: fail hosted now.
            return ProbeResult(
                healthy=False,
                idle_matching=0,
                online_matching=0,
                detail="no-online-matching-runner",
                waited_seconds=int(clock() - start),
            )
        # Saturation: at least one matching runner is online, none idle.
        # Routine, expected fleet behavior — worth a bounded wait rather
        # than an immediate spend on hosted capacity.
        elapsed = clock() - start
        remaining = max_wait_seconds - elapsed
        if remaining <= 0:
            return ProbeResult(
                healthy=False,
                idle_matching=0,
                online_matching=online_matching,
                detail="saturated-timeout",
                waited_seconds=int(elapsed),
            )
        sleep(min(poll_interval_seconds, remaining))


def _write_output(*, name: str, value: str) -> None:
    output_path = Path(os.environ["GITHUB_OUTPUT"])
    with output_path.open("a", encoding="utf-8") as output:
        output.write(f"{name}={value}\n")


def main() -> int:
    """Run the Action entry point without ever emitting a secret."""
    try:
        labels = parse_labels(raw=os.environ.get("CI_RUNNER_HEALTH_LABELS", ""))
        repository = os.environ["GITHUB_REPOSITORY"]
        token = os.environ["CI_RUNNER_HEALTH_TOKEN"]
        max_wait_seconds = int(os.environ.get("CI_RUNNER_HEALTH_MAX_WAIT_SECONDS", "0"))
        poll_interval_seconds = int(os.environ.get("CI_RUNNER_HEALTH_POLL_INTERVAL_SECONDS", "15"))
        result = probe(
            repository=repository,
            token=token,
            required_labels=labels,
            max_wait_seconds=max_wait_seconds,
            poll_interval_seconds=poll_interval_seconds,
        )
    except (KeyError, ValueError):
        # Malformed action input is also fail-closed.
        result = ProbeResult(healthy=False, idle_matching=0, detail="invalid-health-probe-input")
    _write_output(name="healthy", value=str(result.healthy).lower())
    _write_output(name="idle-matching", value=str(result.idle_matching))
    _write_output(name="online-matching", value=str(result.online_matching))
    _write_output(name="waited-seconds", value=str(result.waited_seconds))
    _write_output(name="detail", value=result.detail)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
