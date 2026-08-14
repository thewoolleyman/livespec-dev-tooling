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
    """Safe result emitted to the calling reusable workflow."""

    healthy: bool
    idle_matching: int
    detail: str


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


def idle_matching_runners(*, runners: list[dict[str, Any]], required_labels: frozenset[str]) -> int:
    """Count online, idle runners carrying every required label."""
    count = 0
    for runner in runners:
        raw_labels = runner.get("labels", [])
        labels = {
            label.get("name")
            for label in raw_labels
            if isinstance(label, dict) and isinstance(label.get("name"), str)
        }
        if (
            runner.get("status") == "online"
            and runner.get("busy") is False
            and required_labels.issubset(labels)
        ):
            count += 1
    return count


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
    opener: Callable[..., dict[str, Any]] = _request_json,
) -> ProbeResult:
    """Read the bounded runner sample and return a safe health verdict."""
    api_url = os.environ.get("GITHUB_API_URL", "https://api.github.com").rstrip("/")
    url = f"{api_url}{_RUNNERS_PATH.format(repository=repository)}"
    try:
        payload = opener(url=url, token=token)
        raw_runners = payload.get("runners")
        if not isinstance(raw_runners, list) or not all(
            isinstance(runner, dict) for runner in raw_runners
        ):
            return ProbeResult(healthy=False, idle_matching=0, detail="runner-api-error")
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        # Any expected API/parse failure must route hosted, never queue locally.
        return ProbeResult(healthy=False, idle_matching=0, detail="runner-api-error")
    idle_matching = idle_matching_runners(runners=raw_runners, required_labels=required_labels)
    if idle_matching == 0:
        return ProbeResult(healthy=False, idle_matching=0, detail="no-idle-matching-runner")
    return ProbeResult(healthy=True, idle_matching=idle_matching, detail="idle-runner-observed")


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
        result = probe(repository=repository, token=token, required_labels=labels)
    except (KeyError, ValueError):
        # Malformed action input is also fail-closed.
        result = ProbeResult(healthy=False, idle_matching=0, detail="invalid-health-probe-input")
    _write_output(name="healthy", value=str(result.healthy).lower())
    _write_output(name="idle-matching", value=str(result.idle_matching))
    _write_output(name="detail", value=result.detail)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
