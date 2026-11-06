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

from livespec_dev_tooling.incident_ci_payload import strict_json

__all__: list[str] = ["CiAuthorityBoundary"]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-egy3ri
_MAX_REPLY = 65536
_MAX_TOKEN = 4096
_MIN_TOKEN_CHARACTER = 33
_ACCEPTED = 202
# The job's read ceiling. The observer answers /current only after its own
# reader pass, whose ceiling is incident_observer_authority._READER_TIMEOUT_SECONDS
# (45 s); this stays above that plus the observer's overhead so the job
# outwaits the pass instead of racing it, and about five such reads happen
# per incident run (livespec-dev-tooling-ws2idp, 2026-11-06).
_OBSERVER_READ_TIMEOUT_SECONDS = 60
# Where to open the TCP connection when the URL's hostname does not resolve to
# the observer from the runner. A runner pod resolves the observer's ts.net name
# through public DNS to Tailscale's Funnel ingress, where the tailnet port is not
# served, so each read hung to the ceiling (livespec-dev-tooling-ws2idp,
# 2026-11-06). The value is a validated IPv4 or IPv6 literal; the URL's hostname
# is still what the certificate is verified against and what the Host header
# names, so the trust boundary does not move. Unset keeps hostname dialing.
_CONNECT_ADDRESS_VARIABLE = "LIVESPEC_INCIDENT_OBSERVER_CONNECT_ADDR"


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

    def _query(self, *, route: str, query: dict[str, Any]) -> bool:
        try:
            parsed = urlsplit(self.observer_url)
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.query
                or parsed.fragment
                or not self.observer_token
                or self.observer_token.strip() != self.observer_token
                or any(ord(c) < _MIN_TOKEN_CHARACTER for c in self.observer_token)
                or len(self.observer_token) > _MAX_TOKEN
                or set(query)
                != {"repository", "arm_id", "pr_number", "base_sha", "head_sha", "receipt_digest"}
                or type(query["pr_number"]) is not int
                or query["pr_number"] <= 0
                or not all(
                    isinstance(value, str) for key, value in query.items() if key != "pr_number"
                )
                or re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", query["repository"]) is None
                or any(
                    re.fullmatch(r"[0-9a-f]{64}", query[key]) is None
                    for key in ("arm_id", "receipt_digest")
                )
                or any(
                    re.fullmatch(r"[0-9a-f]{40}", query[key]) is None
                    for key in ("base_sha", "head_sha")
                )
            ):
                return False
            # An invalid literal raises ValueError here, before any connection exists,
            # and the handler below turns it into a refusal.
            connect_to = _connect_address()
            # System TLS verification; no redirect handler can forward the token.
            with closing(
                http.client.HTTPSConnection(
                    parsed.hostname, port=parsed.port, timeout=_OBSERVER_READ_TIMEOUT_SECONDS
                )
            ) as connection:
                if connect_to is not None:
                    # Dial the literal, verify and name the URL's host: the socket is
                    # handed to the connection, which then never dials by name.
                    raw = socket.create_connection(
                        (connect_to, parsed.port or 443), timeout=_OBSERVER_READ_TIMEOUT_SECONDS
                    )
                    # A failing wrap raises into the handler below and refuses; the
                    # unwrapped socket is released with `raw` when this frame unwinds.
                    connection.sock = ssl.create_default_context().wrap_socket(
                        raw, server_hostname=parsed.hostname
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
                raw = response.read(_MAX_REPLY + 1)
                if response.status != _ACCEPTED or len(raw) > _MAX_REPLY:
                    return False
                value = strict_json(text=raw.decode())
                reply = cast("dict[str, Any]", value) if isinstance(value, dict) else {}
                return (
                    set(reply) == {"schema", "status", "query"}
                    and type(reply.get("schema")) is int
                    and reply.get("schema") == 1
                    and reply.get("status") == route
                    and json.dumps(reply.get("query"), sort_keys=True)
                    == json.dumps(query, sort_keys=True)
                )
        except (OSError, ValueError, TypeError, RecursionError, http.client.HTTPException):
            return False


def _connect_address() -> str | None:
    """Return the override literal, or None when unset; an invalid value raises ValueError."""
    value = os.environ.get(_CONNECT_ADDRESS_VARIABLE)
    if value is None:
        return None
    return str(ipaddress.ip_address(value))
