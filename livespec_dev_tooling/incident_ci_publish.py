"""Publish a PASSED incident CI aggregate to the independent controller.

Two operations, both run from the released build, never the candidate tree:

- `query`, run in the incident CI job after its released aggregate PASSED, reads the
  pull request through the same authenticated forge read the entrance uses and writes
  the six-field retained arm query to the job output `query`.
- `publish`, run in the isolated publisher job of `reusable-incident-ci-publish.yml`
  (which holds only `id-token: write`), requests the job's forge-issued OIDC identity
  token and posts `query`, `aggregate` and `release` to the controller's
  `/ci/publish`. The token is sent only to the controller and never printed.

`publish` exits 0 when the controller answers `published` or `retained`, and when it
answers `identity-not-provisioned`: the installation has no CI identity policy yet,
the code goes to the step summary, and the job concludes on the aggregate alone. Any
other refusal, a conflict, an unreadable reply, and an unreachable controller exit 1
naming the cause, because an expedited run whose omissions are not recorded is
unaccounted work.
"""

from __future__ import annotations

import argparse
import http.client
import ipaddress
import json
import os
import socket
import ssl
import sys
import urllib.request
from collections.abc import Callable, Mapping
from contextlib import closing
from pathlib import Path
from typing import Any, cast
from urllib.parse import quote, urlsplit

from livespec_dev_tooling.incident_ci_event import observe_event
from livespec_dev_tooling.incident_ci_payload import decode_authority, query_for
from livespec_dev_tooling.incident_pr_run_records import NOT_PROVISIONED
from livespec_dev_tooling.incident_strict_json import IncidentJsonRefusalError, strict_json

__all__: list[str] = ["main", "publication_query", "publish", "request_identity_token"]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-bqnzcm.4
_URL_VARIABLE = "LIVESPEC_INCIDENT_OBSERVER_URL"
_CONNECT_VARIABLE = "LIVESPEC_INCIDENT_OBSERVER_CONNECT_ADDR"
_AUDIENCE_VARIABLE = "LIVESPEC_INCIDENT_CI_AUDIENCE"
_TIMEOUT_SECONDS = 120
_MAX_REPLY = 65536
_ACCEPTED = frozenset({"published", "retained"})
_FAILURES = (
    OSError,
    ValueError,
    TypeError,
    KeyError,
    RecursionError,
    IncidentJsonRefusalError,
    http.client.HTTPException,
)


def publication_query(*, environ: Mapping[str, str]) -> dict[str, Any] | None:
    """The retained arm query the pull request's incident block names, or None."""
    observed = observe_event(environ=environ)
    authority = None if observed is None else decode_authority(payload=observed[1])
    return None if authority is None else query_for(authority=authority)


def request_identity_token(*, environ: Mapping[str, str]) -> str:
    """The job's OIDC identity token, for the configured audience when one is set."""
    url = environ["ACTIONS_ID_TOKEN_REQUEST_URL"]
    audience = environ.get(_AUDIENCE_VARIABLE, "")
    if audience:
        url += "&audience=" + quote(audience, safe="")
    if urlsplit(url).scheme != "https":
        message = "identity token request URL is not https"
        raise ValueError(message)
    request = urllib.request.Request(  # noqa: S310 - the scheme is checked above.
        url, headers={"Authorization": "bearer " + environ["ACTIONS_ID_TOKEN_REQUEST_TOKEN"]}
    )
    with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:  # noqa: S310
        value = strict_json(text=response.read(_MAX_REPLY).decode(), limit=_MAX_REPLY)
    token = cast("dict[str, Any]", value).get("value") if isinstance(value, dict) else None
    if not isinstance(token, str) or not token:
        message = "identity token response carries no token"
        raise ValueError(message)
    return token


def send_publication(
    *, url: str, token: str, body: bytes, connect_to: str | None
) -> tuple[int, bytes]:
    """POST one publication to the controller with system TLS and no redirects."""
    parsed = urlsplit(url)
    host = parsed.hostname or ""
    if parsed.scheme != "https" or not host or parsed.query or parsed.fragment:
        message = _URL_VARIABLE + " is not an https URL"
        raise ValueError(message)
    port = parsed.port or http.client.HTTPS_PORT
    with closing(
        http.client.HTTPSConnection(host, port=port, timeout=_TIMEOUT_SECONDS)
    ) as connection:
        if connect_to is not None:
            # Dial the literal and verify the URL's host, as the entrance's reads do.
            raw = socket.create_connection((connect_to, port), timeout=_TIMEOUT_SECONDS)
            connection.sock = ssl.create_default_context().wrap_socket(raw, server_hostname=host)
        connection.request(
            "POST",
            parsed.path.rstrip("/") + "/ci/publish",
            body=body,
            headers={"Content-Type": "application/json", "Authorization": "Bearer " + token},
        )
        response = connection.getresponse()
        return response.status, response.read(_MAX_REPLY + 1)


def publish(
    *,
    environ: Mapping[str, str],
    release: str,
    aggregate: str,
    query: str,
    send: Callable[..., tuple[int, bytes]] = send_publication,
    token_source: Callable[..., str] = request_identity_token,
) -> tuple[int, str]:
    """Publish once; the exit code and the line naming what the controller answered."""
    try:
        value = strict_json(text=aggregate, limit=1_000_000)
        if not isinstance(value, dict) or cast("dict[str, Any]", value).get("status") != "passed":
            return 1, "the aggregate did not pass; nothing was published"
        body = json.dumps(
            {"query": strict_json(text=query, limit=65536), "aggregate": value, "release": release},
            sort_keys=True,
        ).encode()
        connect = environ.get(_CONNECT_VARIABLE, "")
        connect_to = str(ipaddress.ip_address(connect)) if connect else None
        status, raw = send(
            url=environ[_URL_VARIABLE],
            token=token_source(environ=environ),
            body=body,
            connect_to=connect_to,
        )
    except _FAILURES as error:
        return 1, f"the controller could not be reached or asked: {type(error).__name__}"
    return _answer(status=status, raw=raw)


def _answer(*, status: int, raw: bytes) -> tuple[int, str]:
    try:
        reply = strict_json(text=raw[:_MAX_REPLY].decode(), limit=_MAX_REPLY)
    except (ValueError, UnicodeError, IncidentJsonRefusalError, RecursionError):
        return 1, f"the controller answered HTTP {status} with an unreadable reply"
    data = cast("dict[str, Any]", reply) if isinstance(reply, dict) else {}
    answered, reason = data.get("status"), data.get("reason")
    if answered in _ACCEPTED:
        return 0, f"the controller {answered} aggregate {data.get('aggregate_digest')}"
    if answered == "refused" and reason == NOT_PROVISIONED:
        return 0, (
            "the controller answered identity-not-provisioned: its installation has no CI "
            "identity policy, so this run is recorded on the incident item as unpublished"
        )
    return 1, f"the controller answered HTTP {status}: {answered} {reason}"


def _append(*, environ: Mapping[str, str], name: str, text: str) -> None:
    if environ.get(name):
        with Path(environ[name]).open("a") as stream:
            _ = stream.write(text)


def main(*, argv: list[str] | None = None) -> int:
    """`query` writes the arm query output; `publish` posts the aggregate."""
    parser = argparse.ArgumentParser(description=__doc__)
    _ = parser.add_argument("operation", choices=("query", "publish"))
    args = parser.parse_args(argv)
    environ = dict(os.environ)
    if args.operation == "query":
        query = publication_query(environ=environ)
        if query is None:
            _ = sys.stdout.write("::error::incident-ci-publish: no retained arm query\n")
            return 2
        line = json.dumps(query, sort_keys=True)
        _append(environ=environ, name="GITHUB_OUTPUT", text="query=" + line + "\n")
        _ = sys.stdout.write(line + "\n")
        return 0
    code, text = publish(
        environ=environ,
        release=environ.get("INCIDENT_CI_RELEASE", ""),
        aggregate=environ.get("INCIDENT_CI_AGGREGATE", ""),
        query=environ.get("INCIDENT_CI_QUERY", ""),
    )
    _ = sys.stdout.write(
        ("::notice::" if code == 0 else "::error::") + "incident-ci-publish: " + text + "\n"
    )
    _append(
        environ=environ,
        name="GITHUB_STEP_SUMMARY",
        text="## incident-ci-publish\n\n" + text + ".\n",
    )
    return code


if __name__ == "__main__":
    raise SystemExit(main())
