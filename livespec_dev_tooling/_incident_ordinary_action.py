"""The master-health reconciler's ownership read, behind `CiAuthorityBoundary`.

`CiAuthorityBoundary.ordinary_action` is the public entrance; this module holds
its validation, reply grammar and refusal naming, plus the header-value and
refusal helpers the boundary's other routes share. Every way of not getting the
observer's exact answer comes back as `UNREADABLE` with its cause named, so the
caller can fail closed without guessing `ordinary` (livespec-dev-tooling-ariayn).
"""

from __future__ import annotations

import http.client
import json
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast
from urllib.parse import urlsplit

from livespec_dev_tooling.incident_strict_json import IncidentJsonRefusalError, strict_json

__all__: list[str] = [
    "ACCEPTED",
    "MAX_REPLY",
    "UNREADABLE",
    "OrdinaryActionOwnership",
    "is_header_value",
    "read_ownership",
    "refuse",
]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-ariayn
MAX_REPLY = 65536
ACCEPTED = 202
UNREADABLE = "unreadable"
_MAX_TOKEN = 4096
# An RFC 7230 field-value the client can encode: visible ASCII and latin-1 obs-text.
# No whitespace, control character or character beyond latin-1 can be sent as the
# Authorization header, so http.client would fail while encoding it, before any dial.
_HEADER_VALUE = re.compile(r"[\x21-\x7e\x80-\xff]+")
# A read that fails on the wire says why on stderr. The drill's refusals carried
# no trace of the host the client had dialed or how the dial failed, because
# every error became a bare False (livespec-dev-tooling-ws2idp, 2026-11-06).
# The detail names the error class, the route, the dialed address:port and the
# verified hostname, never the token or the reply.
_REFUSAL_PREFIX = "incident-ci: observer read refused: "
# The observer answers this route under its repository fence with a bounded
# wait, so the read needs no reader-pass ceiling; a minute per socket operation
# is already generous.
_ROUTE = "ordinary-action"
_TIMEOUT_SECONDS = 60
_QUERY_FIELDS = frozenset({"repository", "action", "window_shas"})
_REPLY_FIELDS = frozenset({"schema", "status", "reason", "receipt", "query"})
_MAX_WINDOW_SHAS = 128
_BAD_URL = "the observer URL is not an https URL with a host and no credentials, query or fragment"


@dataclass(frozen=True, kw_only=True)
class OrdinaryActionOwnership:
    """The observer's ownership answer for one reconciler step, or why there is none.

    ``status`` is ``incident-owned`` or ``ordinary`` when the observer answered
    exactly, and ``UNREADABLE`` when it did not. ``reason`` then names the cause,
    never the token or the reply. ``receipt`` is the observer's receipt for the
    one ordinary step it lets run, and ``None`` otherwise.
    """

    status: str
    reason: str
    receipt: str | None = None


def read_ownership(
    *,
    url: str,
    token: str,
    query: dict[str, Any],
    exchange: Callable[..., tuple[int, bytes]],
    connect_address: Callable[[], str | None],
    connect_variable: str,
) -> OrdinaryActionOwnership:
    """Validate, send through ``exchange`` and read back one exact ownership answer."""
    cause = _input_refusal(url=url, token=token, query=query)
    if cause is not None:
        return _unreadable(detail=cause + "; no connection was attempted")
    parsed = urlsplit(url)
    host = parsed.hostname or ""
    try:
        connect_to = connect_address()
    except ValueError:
        return _unreadable(
            detail=connect_variable
            + " is not an IPv4 or IPv6 address literal; no connection was attempted"
        )
    where = " while reading /" + _ROUTE + " from " + (connect_to or host) + ":"
    where += str(parsed.port or http.client.HTTPS_PORT) + " as " + host
    try:
        status, raw = exchange(
            route=_ROUTE, query=query, connect_to=connect_to, timeout=_TIMEOUT_SECONDS
        )
    except (OSError, ValueError, TypeError, RecursionError, http.client.HTTPException) as error:
        return _unreadable(detail=type(error).__name__ + where)
    return _answer(status=status, raw=raw, query=query, where=where)


def is_header_value(*, token: str) -> bool:
    """Whether the token is non-empty, bounded and encodable as an Authorization value."""
    return len(token) <= _MAX_TOKEN and _HEADER_VALUE.fullmatch(token) is not None


def refuse(*, detail: str) -> bool:
    """Name the refusal on stderr; the token never appears in the detail."""
    _ = sys.stderr.write(_REFUSAL_PREFIX + detail + "\n")
    return False


def _input_refusal(*, url: str, token: str, query: dict[str, Any]) -> str | None:
    """Name what is wrong with the caller's own inputs, or None when all are sound."""
    try:
        parsed = urlsplit(url)
        _ = parsed.port
    except ValueError:
        return _BAD_URL
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        return _BAD_URL
    if not is_header_value(token=token):
        return "the observer query token is empty, oversize or not a valid header value"
    window: object = query.get("window_shas")
    if (
        frozenset(query) != _QUERY_FIELDS
        or not isinstance(query.get("repository"), str)
        or re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", query["repository"]) is None
        or not isinstance(query.get("action"), str)
        or not query["action"]
        or not isinstance(window, list)
        or len(cast("list[object]", window)) > _MAX_WINDOW_SHAS
        or not all(
            isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{40}", sha) is not None
            for sha in cast("list[object]", window)
        )
    ):
        return "the ordinary-action query is malformed"
    return None


def _answer(
    *, status: int, raw: bytes, query: dict[str, Any], where: str
) -> OrdinaryActionOwnership:
    """Accept only the observer's exact, bounded 202 ownership reply."""
    if status != ACCEPTED:
        return _unreadable(detail="HTTP " + str(status) + where)
    if len(raw) > MAX_REPLY:
        return _unreadable(detail="oversize reply" + where)
    try:
        value: object = strict_json(text=raw, limit=MAX_REPLY)
    except (IncidentJsonRefusalError, ValueError, RecursionError):
        return _unreadable(detail="unparseable reply" + where)
    reply = cast("dict[str, Any]", value) if isinstance(value, dict) else {}
    answer: object = reply.get("status")
    reason: object = reply.get("reason")
    receipt: object = reply.get("receipt")
    if (
        frozenset(reply) != _REPLY_FIELDS
        or type(reply.get("schema")) is not int
        or reply.get("schema") != 1
        or not isinstance(answer, str)
        or answer not in {"ordinary", "incident-owned"}
        or not isinstance(reason, str)
        or not reason
        or not (
            (isinstance(receipt, str) and bool(receipt))
            if answer == "ordinary"
            else receipt is None
        )
        or json.dumps(reply.get("query"), sort_keys=True) != json.dumps(query, sort_keys=True)
    ):
        return _unreadable(detail="reply is not the exact ordinary-action answer" + where)
    return OrdinaryActionOwnership(
        status=answer, reason=reason, receipt=cast("str | None", receipt)
    )


def _unreadable(*, detail: str) -> OrdinaryActionOwnership:
    """Name why no ownership answer was read; the token never appears in it."""
    _ = refuse(detail=detail)
    return OrdinaryActionOwnership(status=UNREADABLE, reason=detail)
