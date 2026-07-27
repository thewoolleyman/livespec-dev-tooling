"""Typed GitHub read-failure causes for the fleet `gh` seam.

Split out of `_context.py` when that module crossed the 250-LLOC hard
ceiling. The contents are the cohesive half: what a failed read WAS, how it
is classified, and how its detail is made safe to log — with no knowledge of
`FleetContext` itself.

The classification exists to serve a decision the old code could not make.
`api_object()` and `file_text()` returned `None` on every failure, so 403 /
404 / 429 / 5xx / transport / malformed-payload were indistinguishable, and a
retry policy could not tell a retryable credential rejection from a
non-retryable 404. `livespec-dev-tooling-z4qi` is the red master that cost.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__: list[str] = [
    "ReadFailure",
    "classify_gh_failure",
    "sanitize_detail",
]

# Credential shapes GitHub issues. `gh` can echo one back in an error body, and
# these diagnostics reach CI logs, so redaction is a correctness requirement of
# preserving stderr at all — not a nicety.
_TOKEN_PATTERN = re.compile(r"\b(?:gh[pousr]|github_pat)_[A-Za-z0-9_]{8,}")
_REDACTED = "<REDACTED>"
_DETAIL_LIMIT = 400

# Ordered because a `gh` error body can mention more than one number; the FIRST
# match wins and the specific statuses are tried before the 5xx range.
_STATUS_KINDS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b(?:HTTP\s*)?429\b|rate limit"), "rate_limited"),
    (re.compile(r"\b(?:HTTP\s*)?40[13]\b|not accessible|bad credentials"), "forbidden"),
    (re.compile(r"\b(?:HTTP\s*)?404\b|not found"), "not_found"),
    (re.compile(r"\b(?:HTTP\s*)?5\d{2}\b"), "server_error"),
)


def sanitize_detail(*, text: str) -> str:
    """Return `text` with credential-shaped substrings redacted and bounded.

    Truncation is bounded rather than absent because an unbounded API error
    body would otherwise dominate a structured log line.
    """
    redacted = _TOKEN_PATTERN.sub(_REDACTED, text.strip())
    if len(redacted) > _DETAIL_LIMIT:
        return redacted[:_DETAIL_LIMIT] + "…"
    return redacted


def classify_gh_failure(*, stderr: str) -> str:
    """Classify a failed `gh` invocation into a retry-relevant kind from its stderr.

    Takes the stderr text rather than the `GhResult` so this module needs no
    import from `_context` — which imports THIS one.

    The distinction this exists for: `rate_limited` and `server_error` are
    retryable, `forbidden` and `not_found` are not, and `not_found` alone
    carries real information (the thing is absent). Collapsing all four to
    "unavailable" is what made one transient rejection indistinguishable from
    a genuine blind spot.
    """
    haystack = stderr.lower()
    for pattern, kind in _STATUS_KINDS:
        if pattern.search(haystack):
            return kind
    return "transport"


@dataclass(frozen=True, kw_only=True)
class ReadFailure:
    """One preserved GitHub read failure: what was attempted and why it failed.

    `operation` names the READ KIND rather than the endpoint — `repo_metadata`,
    `contents`, `tree`, `api`, `manifest` — so a consumer can tell a
    contents-read failure from a repository-metadata failure without parsing
    paths.
    """

    operation: str
    path: str
    returncode: int
    kind: str
    detail: str

    def as_dict(self) -> dict[str, object]:
        """Structured-log projection; already sanitized by construction."""
        return {
            "operation": self.operation,
            "path": self.path,
            "returncode": self.returncode,
            "kind": self.kind,
            "detail": self.detail,
        }
