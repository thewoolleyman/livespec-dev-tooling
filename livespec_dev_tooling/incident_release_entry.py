"""Release and pin dispatch entrance: ask the observer's release screen before the effect.

A release or pin dispatch workflow step runs this immediately before its effect:

    python -m livespec_dev_tooling.incident_release_entry \\
        --observed-repository OWNER/REPO --repository OWNER/SOURCE \\
        --source-sha SHA --tag TAG

`LIVESPEC_INCIDENT_OBSERVER_URL` names the incident observer of
`--observed-repository`, and `LIVESPEC_INCIDENT_OBSERVER_QUERY_TOKEN` is its
read-only query credential. With no URL, or with a source repository that is
not the observed one, the entrance prints a no-op line and exits 0 without any
network call, so a dispatch with no incident observer runs exactly as before.

Once configured it fails closed. A named refusal from the observer
(`incident-release-recovery-retained`, `incident-release-source-unverifiable`),
an unreachable observer, a misconfiguration or a malformed reply each exit 1
and name why. The screen route itself is `incident_release_screen`.
"""

from __future__ import annotations

import argparse
import http.client
import json
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, cast
from urllib.parse import urlsplit

from livespec_dev_tooling.incident_release_screen import RELEASE_SCREEN_PATH

__all__: list[str] = ["ScreenRequest", "main", "screen"]

_URL = "LIVESPEC_INCIDENT_OBSERVER_URL"
_CREDENTIAL_VARIABLE = "LIVESPEC_INCIDENT_OBSERVER_QUERY_TOKEN"
_TIMEOUT_SECONDS = 60
_MAX_REPLY = 65536
_PROCEEDS = "dispatch proceeds as normal"


@dataclass(frozen=True, kw_only=True)
class ScreenRequest:
    """One exact release: the observed repository and the source being dispatched."""

    observed_repository: str
    repository: str
    source_sha: str
    tag: str


def screen(
    *,
    request: ScreenRequest,
    environ: Mapping[str, str],
    connect: Callable[..., http.client.HTTPSConnection],
) -> tuple[int, str]:
    """Return the exit code and the line that names the outcome."""
    url = environ.get(_URL, "")
    if not url:
        return 0, f"incident release screen: {_URL} is unset; {_PROCEEDS}"
    if request.repository != request.observed_repository:
        detail = f"{request.repository} is not observed here ({request.observed_repository})"
        return 0, f"incident release screen: {detail}; {_PROCEEDS}"
    parsed = urlsplit(url)
    token = environ.get(_CREDENTIAL_VARIABLE, "")
    if parsed.scheme != "https" or not parsed.hostname or not token:
        detail = f"{_URL} must be an https URL and {_CREDENTIAL_VARIABLE} must be set"
        return 1, f"incident-release-screen-misconfigured: {detail}"
    payload = {
        "repository": request.repository,
        "source_sha": request.source_sha,
        "tag": request.tag,
    }
    try:
        connection = connect(parsed.hostname, port=parsed.port, timeout=_TIMEOUT_SECONDS)
        try:
            connection.request(
                "POST",
                parsed.path.rstrip("/") + RELEASE_SCREEN_PATH,
                body=json.dumps(payload, sort_keys=True).encode(),
                headers={"Content-Type": "application/json", "Authorization": "Bearer " + token},
            )
            response = connection.getresponse()
            status, raw = response.status, response.read(_MAX_REPLY + 1)
        finally:
            connection.close()
    except (OSError, http.client.HTTPException) as error:
        detail = (
            f"{type(error).__name__} while reading {RELEASE_SCREEN_PATH} from {parsed.hostname}"
        )
        return 1, f"incident-release-screen-unreachable: {detail}"
    return _verdict(status=status, raw=raw, payload=payload)


def _verdict(*, status: int, raw: bytes, payload: dict[str, str]) -> tuple[int, str]:
    try:
        reply: object = json.loads(raw)
    except ValueError:
        reply = None
    if isinstance(reply, dict):
        answer = cast("dict[str, Any]", reply)
        if status == http.client.ACCEPTED and answer == {
            "schema": 1,
            "status": "clear",
            "query": payload,
        }:
            return 0, f"incident release screen: {payload['tag']} is clear; {_PROCEEDS}"
        reason = answer.get("reason")
        if answer.get("status") == "refused" and isinstance(reason, str) and reason:
            return 1, str(answer.get("detail") or reason)
    return 1, f"incident-release-screen-malformed-reply: HTTP {status} from the observer"


def main(*, argv: Sequence[str] | None = None) -> int:
    """Screen one release; exit 0 to proceed and 1 to refuse the dispatch."""
    parser = argparse.ArgumentParser(prog="incident-release-entry", description=__doc__)
    for name in ("observed-repository", "repository", "source-sha", "tag"):
        _ = parser.add_argument("--" + name, required=True)
    args = parser.parse_args(argv)
    request = ScreenRequest(
        observed_repository=str(args.observed_repository),
        repository=str(args.repository),
        source_sha=str(args.source_sha),
        tag=str(args.tag),
    )
    code, line = screen(request=request, environ=os.environ, connect=http.client.HTTPSConnection)
    _ = (sys.stdout if code == 0 else sys.stderr).write(line + "\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
