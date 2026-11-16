"""Classify dependency failures that are proved external at the transport boundary.

The master-green external-red protocol intentionally has a small input surface:
callers pass the response as it was observed, rather than an interpretation of
it.  That keeps a 403 caused by the fleet's own credentials distinct from a
403 that the forge accompanied with rate-limit evidence.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

__all__: list[str] = ["ExternalCause", "classify_external_cause", "classify_failure_kind"]

_RATE_LIMIT_BODY = re.compile(
    r"rate[ -]?limit(?:ed)?|quota exceeded|abuse detection mechanism|secondary quota",
    re.IGNORECASE,
)
_DNS_FAILURE = re.compile(
    r"(?:no such host|could not resolve|name or service not known|dns(?: lookup)? failed)",
    re.IGNORECASE,
)
_CONNECT_FAILURE = re.compile(
    r"(?:connection refused|connect(?:ion)? failed|dial tcp|connection reset)", re.IGNORECASE
)
_TIMEOUT = re.compile(r"(?:timed? ?out|deadline exceeded)", re.IGNORECASE)
_HTTP_STATUS = re.compile(r"\b(?:http\s*|error:\s*)([1-5]\d\d)\b", re.IGNORECASE)
_GIT_HTTP_STATUS = re.compile(r"requested url returned error:\s*([1-5]\d\d)", re.IGNORECASE)
_EVIDENCE_LIMIT = 400
_HTTP_TOO_MANY_REQUESTS = 429
_HTTP_NOT_FOUND = 404
_HTTP_SERVER_ERROR_FIRST = 500
_HTTP_SERVER_ERROR_AFTER_LAST = 600


@dataclass(frozen=True, kw_only=True)
class ExternalCause:
    """One published, transport-layer proof that a dependency was external."""

    dependency: str
    kind: str
    evidence: str

    def as_dict(self) -> dict[str, str]:
        """Return the workflow-result representation required by the contract."""
        return {"dependency": self.dependency, "kind": self.kind, "evidence": self.evidence}


def _normal_headers(*, headers: Mapping[str, str]) -> dict[str, str]:
    return {str(name).lower(): str(value).strip() for name, value in headers.items()}


def _status_from_stderr(*, stderr: str) -> int | None:
    """Recover a relayed HTTP status for legacy clients that expose stderr only."""
    matched = _HTTP_STATUS.search(stderr) or _GIT_HTTP_STATUS.search(stderr)
    return int(matched.group(1)) if matched is not None else None


def _rate_limited(*, status: int | None, headers: Mapping[str, str], body: str) -> bool:
    """Whether this response itself proves a forge quota or rate-limit failure."""
    if status not in {403, 429}:
        return False
    return (
        headers.get("x-ratelimit-remaining") == "0"
        or bool(headers.get("retry-after"))
        or _RATE_LIMIT_BODY.search(body) is not None
    )


def classify_failure_kind(
    *, status: int | None, headers: Mapping[str, str], body: str, stderr: str
) -> str:
    """Return the common retry vocabulary for one HTTP or transport result.

    This is deliberately separate from record emission: a headerless 429 is
    retryable for a caller, but is not publishable as an external-cause record
    until the transport supplied rate-limit evidence.
    """
    observed_status = status if status is not None else _status_from_stderr(stderr=stderr)
    if observed_status is None:
        return "transport"
    if _rate_limited(status=observed_status, headers=_normal_headers(headers=headers), body=body):
        return "rate_limited"
    status_kinds = {
        _HTTP_TOO_MANY_REQUESTS: "rate_limited",
        401: "forbidden",
        403: "forbidden",
        _HTTP_NOT_FOUND: "not_found",
    }
    return status_kinds.get(
        observed_status,
        "server_error"
        if _HTTP_SERVER_ERROR_FIRST <= observed_status < _HTTP_SERVER_ERROR_AFTER_LAST
        else "transport",
    )


def _evidence(*, status: int | None, headers: Mapping[str, str], body: str, stderr: str) -> str:
    """Keep the observed proof useful but bounded for a workflow summary."""
    shown_headers = [
        f"{name}: {headers[name]}"
        for name in ("x-ratelimit-remaining", "retry-after")
        if headers.get(name)
    ]
    if shown_headers:
        text = "; ".join(shown_headers)
    elif status is not None:
        text = f"HTTP {status}: {body.strip() or stderr.strip()}"
    else:
        text = stderr.strip() or body.strip()
    return text[:_EVIDENCE_LIMIT]


def classify_external_cause(  # noqa: PLR0913 - the transport result is the contract input.
    *,
    dependency: str,
    status: int | None,
    headers: Mapping[str, str],
    body: str,
    stderr: str,
    fleet_runs_host: bool = False,
    documented_outage: bool = False,
) -> ExternalCause | None:
    """Emit the external-cause record proved by one dependency failure, if any.

    ``fleet_runs_host`` is an explicit caller-owned fact.  A connection,
    resolver, or timeout failure is external only for a host the fleet does not
    run; a failure to one of our own hosts remains a defect and emits nothing.
    """
    normalized = _normal_headers(headers=headers)
    kind = classify_failure_kind(status=status, headers=normalized, body=body, stderr=stderr)
    if _rate_limited(status=status, headers=normalized, body=body):
        return ExternalCause(
            dependency=dependency,
            kind="rate_limited",
            evidence=_evidence(status=status, headers=normalized, body=body, stderr=stderr),
        )
    if kind == "server_error":
        return ExternalCause(
            dependency=dependency,
            kind="server_error",
            evidence=_evidence(status=status, headers=normalized, body=body, stderr=stderr),
        )
    if documented_outage:
        return ExternalCause(
            dependency=dependency,
            kind="third_party_outage",
            evidence=_evidence(status=status, headers=normalized, body=body, stderr=stderr),
        )
    if status is None and not fleet_runs_host:
        transport_kind = (
            "dns_failure"
            if _DNS_FAILURE.search(stderr)
            else "connect_failure"
            if _CONNECT_FAILURE.search(stderr)
            else "timeout"
            if _TIMEOUT.search(stderr)
            else None
        )
        if transport_kind is not None:
            return ExternalCause(
                dependency=dependency,
                kind=transport_kind,
                evidence=_evidence(status=None, headers=normalized, body=body, stderr=stderr),
            )
    return None
