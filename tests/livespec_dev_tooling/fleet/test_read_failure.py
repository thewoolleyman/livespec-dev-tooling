"""Unit tests for `livespec_dev_tooling/fleet/_read_failure.py`.

The cause-classification and redaction half of the fleet `gh` seam, split out
of `_context.py` when that module crossed the 250-LLOC hard ceiling. The
integration behaviour (causes actually recorded by `FleetContext` reads) lives
in `test_context_read_failures.py`; this module covers the pure helpers
directly, including the bounds an API error body can push them past.
"""

from __future__ import annotations

from livespec_dev_tooling.fleet._read_failure import (
    ReadFailure,
    classify_gh_failure,
    sanitize_detail,
)

__all__: list[str] = []


def test_an_oversized_detail_is_truncated_with_an_ellipsis() -> None:
    """An unbounded API error body would otherwise dominate a structured log line."""
    detail = sanitize_detail(text="x" * 5000)

    assert len(detail) < 5000, "an oversized body must not pass through whole"
    assert detail.endswith("…"), f"truncation should be visible: {detail[-20:]!r}"


def test_a_short_detail_passes_through_untruncated() -> None:
    """Bounding must not mangle the ordinary case."""
    assert sanitize_detail(text="  gh: Not Found (HTTP 404)  ") == "gh: Not Found (HTTP 404)"


def test_every_credential_prefix_github_issues_is_redacted() -> None:
    """One prefix escaping redaction would leak a live token into CI logs."""
    for prefix in ("ghp", "gho", "ghu", "ghs", "ghr", "github_pat"):
        secret = f"{prefix}_AbCdEf0123456789AbCdEf0123456789"
        assert secret not in sanitize_detail(text=f"failed with {secret}"), prefix


def test_classification_prefers_rate_limit_over_a_generic_status() -> None:
    """A 429 body often also mentions other numbers; the retryable kind must win."""
    assert classify_gh_failure(stderr="API rate limit exceeded (HTTP 429)") == "rate_limited"


def test_an_unrecognized_failure_classifies_as_transport() -> None:
    """No HTTP status at all means the request never got an answer."""
    assert classify_gh_failure(stderr="connection reset by peer") == "transport"


def test_read_failure_projects_every_field_for_structured_logging() -> None:
    """The projection is what consumers emit; a dropped field is an invisible cause."""
    projected = ReadFailure(
        operation="contents",
        path="livespec:AGENTS.md",
        returncode=1,
        kind="not_found",
        detail="gh: Not Found (HTTP 404)",
    ).as_dict()

    assert projected == {
        "operation": "contents",
        "path": "livespec:AGENTS.md",
        "returncode": 1,
        "kind": "not_found",
        "detail": "gh: Not Found (HTTP 404)",
    }
