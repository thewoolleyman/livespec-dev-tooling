"""Read current incident authority through the protected query-only controller.

Hosted CI never receives a tenant credential or the arm/bind credential.
An older controller without fresh canonical-current support refuses this path.
"""

from __future__ import annotations

import http.client
import ipaddress
import json
import os
import re
import socket
import ssl
from contextlib import closing
from dataclasses import dataclass
from typing import Any, cast
from urllib.parse import urlsplit

from livespec_dev_tooling._incident_ordinary_action import ACCEPTED as _ACCEPTED
from livespec_dev_tooling._incident_ordinary_action import MAX_REPLY as _MAX_REPLY
from livespec_dev_tooling._incident_ordinary_action import (
    UNREADABLE,
    OrdinaryActionOwnership,
    read_ownership,
)
from livespec_dev_tooling._incident_ordinary_action import is_header_value as _is_header_value
from livespec_dev_tooling._incident_ordinary_action import refuse as _refuse
from livespec_dev_tooling.incident_strict_json import IncidentJsonRefusalError, strict_json

__all__: list[str] = [
    "UNREADABLE",
    "CiAuthorityBoundary",
    "ObserverTokenError",
    "ObserverUnreachableError",
    "OrdinaryActionOwnership",
]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-egy3ri
# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-zbzls2
# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-qeu4cx
# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-a6wgjz
# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-ariayn
# The reply bound, the 202 status, the header-value rule and the stderr refusal
# line are shared with the ordinary-action read in `_incident_ordinary_action`.
# The job's read ceiling. The observer answers /current only after its own
# reader pass, whose ceiling is incident_authority_client.AUTHORITY_CALL_CEILING_SECONDS
# (600 s, the one bound every authority call shares); this stays above that plus
# the observer's overhead so the job outwaits the pass instead of racing it
# (livespec-dev-tooling-ws2idp, 2026-11-06; livespec-dev-tooling-iezdmk).
_OBSERVER_READ_TIMEOUT_SECONDS = 630
# Where to open the TCP connection when the URL's hostname does not resolve to
# the observer from the runner. A runner pod resolves the observer's ts.net name
# through public DNS to Tailscale's Funnel ingress, where the tailnet port is not
# served, so each read hung to the ceiling (livespec-dev-tooling-ws2idp,
# 2026-11-06). The value is a validated IPv4 or IPv6 literal; the URL's hostname
# is still what the certificate is verified against and what the Host header
# names, so the trust boundary does not move. Unset keeps hostname dialing.
_CONNECT_ADDRESS_VARIABLE = "LIVESPEC_INCIDENT_OBSERVER_CONNECT_ADDR"
_ARM_FIELDS: dict[str, frozenset[str]] = {
    "text": frozenset({"repository"}),
    "int": frozenset({"pr_number"}),
    "digest": frozenset({"arm_id", "receipt_digest"}),
    "sha": frozenset({"base_sha", "head_sha"}),
}
_PROVENANCE_FIELDS: dict[str, frozenset[str]] = {
    "text": frozenset({"repository", "item_id", "attempt_id", "phase", "operation_id", "owner"}),
    "int": frozenset({"generation", "pr_number"}),
    "digest": frozenset(),
    "sha": frozenset({"base", "head", "commit_sha", "tree_sha"}),
}
_FIELDS = {"current": _ARM_FIELDS, "admitted": _ARM_FIELDS, "provenance": _PROVENANCE_FIELDS}


class ObserverUnreachableError(Exception):
    """The /provenance read failed on the wire, so the observer said nothing at all.

    Distinct from an answer that does not confirm the head: a caller reporting
    the refusal must not claim the observer's history lacks the commit when
    nobody read that history (livespec-dev-tooling-qeu4cx).
    """


class ObserverTokenError(Exception):
    """The configured query token cannot be sent as a header value, so nothing was sent.

    A local configuration fault: no request left the host and the observer's history
    was not read, so a caller must name neither an unreachable observer nor one that
    does not record the head (livespec-dev-tooling-a6wgjz).
    """


@dataclass(frozen=True, kw_only=True)
class CiAuthorityBoundary:
    """Authenticate exact read-only queries without following redirects."""

    observer_url: str
    observer_token: str

    def current(self, *, query: dict[str, Any]) -> bool:
        """Require a fresh canonical generation, separate from retained admission."""
        return self._query(route="current", query=query)

    def admitted(self, *, query: dict[str, Any]) -> bool:
        """Require the protected exact premerge arm before omitting work."""
        return self._query(route="admitted", query=query)

    def provenance(self, *, query: dict[str, Any]) -> bool:
        """Require the host's canonical history to record this exact attempt and commit.

        A token that cannot be a header value raises ObserverTokenError before any
        connection is opened. A transport failure (refused, timed out, TLS) raises
        ObserverUnreachableError after the usual stderr line; every other refusal,
        including a reply the observer did send but that does not parse or confirm,
        returns False.
        """
        if not _is_header_value(token=self.observer_token):
            raise ObserverTokenError
        return self._query(route="provenance", query=query)

    def ordinary_action(self, *, query: dict[str, Any]) -> OrdinaryActionOwnership:
        """Ask who owns the master-health reconciler's next step over its window.

        Never raises and never guesses: anything but the observer's exact answer
        is ``UNREADABLE`` with its cause named on stderr.
        """
        return read_ownership(
            url=self.observer_url,
            token=self.observer_token,
            query=query,
            exchange=self._exchange,
            connect_address=_connect_address,
            connect_variable=_CONNECT_ADDRESS_VARIABLE,
        )

    def _query(self, *, route: str, query: dict[str, Any]) -> bool:
        try:
            parsed = urlsplit(self.observer_url)
            host = parsed.hostname or ""
            port = parsed.port or http.client.HTTPS_PORT
            if (
                parsed.scheme != "https"
                or not host
                or parsed.username
                or parsed.password
                or parsed.query
                or parsed.fragment
                or not _is_header_value(token=self.observer_token)
                or set(query) != set[str]().union(*_FIELDS[route].values())
                or any(
                    type(query[key]) is not int or query[key] <= 0 for key in _FIELDS[route]["int"]
                )
                or not all(
                    isinstance(value, str)
                    for key, value in query.items()
                    if key not in _FIELDS[route]["int"]
                )
                or re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", query["repository"]) is None
                or any(
                    re.fullmatch(r"[0-9a-f]{64}", query[key]) is None
                    for key in _FIELDS[route]["digest"]
                )
                or any(
                    re.fullmatch(r"[0-9a-f]{40}", query[key]) is None
                    for key in _FIELDS[route]["sha"]
                )
            ):
                return False
        except (OSError, ValueError, TypeError, RecursionError, http.client.HTTPException):
            # The caller's own inputs; a bad URL, token or query says nothing.
            return False
        try:
            connect_to = _connect_address()
        except ValueError:
            return _refuse(
                detail=_CONNECT_ADDRESS_VARIABLE
                + " is not an IPv4 or IPv6 address literal; no connection was attempted"
            )
        where = " while reading /" + route + " from " + (connect_to or host) + ":" + str(port)
        where += " as " + host
        try:
            status, raw = self._exchange(
                route=route,
                query=query,
                connect_to=connect_to,
                timeout=_OBSERVER_READ_TIMEOUT_SECONDS,
            )
            return _accepts(status=status, raw=raw, route=route, query=query, where=where)
        except (
            OSError,
            ValueError,
            IncidentJsonRefusalError,
            TypeError,
            RecursionError,
            http.client.HTTPException,
        ) as error:
            refused = _refuse(detail=type(error).__name__ + where)
            if route == "provenance" and isinstance(error, OSError | http.client.HTTPException):
                raise ObserverUnreachableError(type(error).__name__ + where) from error
            return refused

    def _exchange(
        self, *, route: str, query: dict[str, Any], connect_to: str | None, timeout: float
    ) -> tuple[int, bytes]:
        """POST one validated query and return its status and bounded body."""
        parsed = urlsplit(self.observer_url)
        host = parsed.hostname or ""
        # System TLS verification; no redirect handler can forward the token.
        with closing(
            http.client.HTTPSConnection(host, port=parsed.port, timeout=timeout)
        ) as connection:
            if connect_to is not None:
                # Dial the literal, verify and name the URL's host: the socket is
                # handed to the connection, which then never dials by name.
                raw = socket.create_connection(
                    (connect_to, parsed.port or http.client.HTTPS_PORT), timeout=timeout
                )
                # A failing wrap raises into the caller's handler and refuses; the
                # unwrapped socket is released with `raw` when this frame unwinds.
                connection.sock = ssl.create_default_context().wrap_socket(
                    raw, server_hostname=host
                )
            connection.request(
                "POST",
                parsed.path.rstrip("/") + "/" + route,
                body=json.dumps(query, sort_keys=True).encode(),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": "Bearer " + self.observer_token,
                },
            )
            response = connection.getresponse()
            return response.status, response.read(_MAX_REPLY + 1)


def _accepts(*, status: int, raw: bytes, route: str, query: dict[str, Any], where: str) -> bool:
    """Accept only an exact bounded 202 reply; a non-202 status is named, never the body."""
    if status != _ACCEPTED:
        return _refuse(detail="HTTP " + str(status) + where)
    if len(raw) > _MAX_REPLY:
        return False
    value = strict_json(text=raw.decode(), limit=65536)
    reply = cast("dict[str, Any]", value) if isinstance(value, dict) else {}
    return (
        set(reply) == {"schema", "status", "query"}
        and type(reply.get("schema")) is int
        and reply.get("schema") == 1
        and reply.get("status") == route
        and json.dumps(reply.get("query"), sort_keys=True) == json.dumps(query, sort_keys=True)
    )


def _connect_address() -> str | None:
    """Return the override literal, or None when unset; an invalid value raises ValueError.

    Empty means unset: a workflow expression cannot leave a variable out, so a false
    condition or an undefined repository variable renders as the empty string.
    """
    value = os.environ.get(_CONNECT_ADDRESS_VARIABLE)
    if not value:
        return None
    return str(ipaddress.ip_address(value))
