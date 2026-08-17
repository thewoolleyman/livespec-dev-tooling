"""GitHub REST response classification for the JIT runner admission controller.

Extraction seam for
`SPECIFICATION/non-functional-requirements.md#adaptive-jit-runner-admission-budget`:
"Only an actual primary/secondary limit response (403 or 429) or valid
authoritative Retry-After or reset-time guidance MAY open the shared circuit
and backoff. When both valid guidance forms are present, the later boundary
wins. Missing, malformed, or contradictory guidance MUST use a conservative
finite fallback ... Authentication and authorization failures are terminal."

Lives under `ci-runner/supervisor/` beside the bash supervisor it will serve
rather than under `livespec_dev_tooling/` — outside this repo's declared
`source_trees` (pyproject.toml). Pure and dependency-free
so the bash supervisor can invoke it as a standalone interpreter call, and so
it is testable without a network seam.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

__all__: list[str] = [
    "CONSERVATIVE_FALLBACK_SECONDS",
    "RetryDecision",
    "classify_response",
]

# A conservative, finite wait used only when GitHub gives no usable guidance —
# never an immediate retry, per the ratified spec clause above. Deliberately
# well inside the fleet's measured secondary-limit cooldowns (see
# `livespec_dev_tooling/fleet/_gh_runner.py`'s `_THROTTLE_COOLDOWN_SECONDS`,
# derived from a measured 16s-apart double-refusal) with headroom for the
# absence of any signal at all.
CONSERVATIVE_FALLBACK_SECONDS = 60.0

# Body-text signature GitHub uses for its secondary rate limiter, which does
# not always carry `X-RateLimit-Remaining: 0` the way the primary limiter
# does. Checked only as a fallback when the header signal is absent.
_SECONDARY_LIMIT_BODY_MARKER = "secondary rate limit"

_HTTP_OK_LOW = 200
_HTTP_OK_HIGH = 300
_HTTP_UNAUTHORIZED = 401
_HTTP_FORBIDDEN = 403
_HTTP_TOO_MANY_REQUESTS = 429
_HTTP_SERVER_ERROR_LOW = 500
_HTTP_SERVER_ERROR_HIGH = 600


@dataclass(frozen=True, kw_only=True)
class RetryDecision:
    """The admission controller's verdict on one GitHub REST response."""

    kind: str  # "ok" | "rate_limited" | "auth_failure" | "server_error" | "other_error"
    retryable: bool
    opens_circuit: bool
    wait_seconds: float
    # "retry_after" | "rate_limit_reset" | "later_boundary" | "fallback" | "none"
    guidance_source: str


def _lower_headers(*, headers: Mapping[str, str]) -> dict[str, str]:
    return {key.lower(): value for key, value in headers.items()}


def _parse_positive_float(*, raw: str | None) -> float | None:
    if raw is None:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    return value if value >= 0.0 else None


def _resolve_retry_wait(*, headers: Mapping[str, str], now: float) -> tuple[float, str]:
    """Apply the ratified later-boundary rule, falling back when neither guidance is usable."""
    retry_after = _parse_positive_float(raw=headers.get("retry-after"))
    reset_at = _parse_positive_float(raw=headers.get("x-ratelimit-reset"))
    reset_wait = max(reset_at - now, 0.0) if reset_at is not None else None

    if retry_after is not None and reset_wait is not None:
        return max(retry_after, reset_wait), "later_boundary"
    if retry_after is not None:
        return retry_after, "retry_after"
    if reset_wait is not None:
        return reset_wait, "rate_limit_reset"
    return CONSERVATIVE_FALLBACK_SECONDS, "fallback"


def _is_rate_limited_403(*, headers: Mapping[str, str], body: str) -> bool:
    remaining = headers.get("x-ratelimit-remaining")
    if remaining is not None:
        try:
            return int(remaining) == 0
        except ValueError:
            pass
    return _SECONDARY_LIMIT_BODY_MARKER in body.lower()


def classify_response(
    *, status_code: int, headers: Mapping[str, str], body: str, now: float
) -> RetryDecision:
    """Classify one GitHub REST response into an admission retry decision.

    `now` is taken as a parameter rather than read internally so this stays a
    pure function: the caller (the durable admission controller) owns the
    clock seam.
    """
    normalized_headers = _lower_headers(headers=headers)

    if _HTTP_OK_LOW <= status_code < _HTTP_OK_HIGH:
        return RetryDecision(
            kind="ok",
            retryable=False,
            opens_circuit=False,
            wait_seconds=0.0,
            guidance_source="none",
        )

    if status_code == _HTTP_UNAUTHORIZED:
        return RetryDecision(
            kind="auth_failure",
            retryable=False,
            opens_circuit=False,
            wait_seconds=0.0,
            guidance_source="none",
        )

    if status_code in (_HTTP_FORBIDDEN, _HTTP_TOO_MANY_REQUESTS):
        is_bare_forbidden = status_code == _HTTP_FORBIDDEN and not _is_rate_limited_403(
            headers=normalized_headers, body=body
        )
        if is_bare_forbidden:
            return RetryDecision(
                kind="auth_failure",
                retryable=False,
                opens_circuit=False,
                wait_seconds=0.0,
                guidance_source="none",
            )
        wait_seconds, guidance_source = _resolve_retry_wait(headers=normalized_headers, now=now)
        return RetryDecision(
            kind="rate_limited",
            retryable=True,
            opens_circuit=True,
            wait_seconds=wait_seconds,
            guidance_source=guidance_source,
        )

    if _HTTP_SERVER_ERROR_LOW <= status_code < _HTTP_SERVER_ERROR_HIGH:
        return RetryDecision(
            kind="server_error",
            retryable=True,
            opens_circuit=False,
            wait_seconds=0.0,
            guidance_source="none",
        )

    return RetryDecision(
        kind="other_error",
        retryable=False,
        opens_circuit=False,
        wait_seconds=0.0,
        guidance_source="none",
    )
