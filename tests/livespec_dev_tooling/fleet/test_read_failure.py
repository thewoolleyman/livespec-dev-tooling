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


# Literal `gh` stderr bodies, each paired with the kind its REMEDY demands. The
# 403s are grouped together deliberately: GitHub answers a secondary rate limit
# and a permission denial with the SAME status, so the status cannot tell them
# apart and only the body can. The two secondary-limit phrasings that omit the
# words "rate limit" are the cases `livespec-dev-tooling-sh71` measured as
# misclassified — retryable and self-clearing, but marked permanent.
_CLASSIFICATION_CASES: tuple[tuple[str, str, str], ...] = (
    (
        "primary limit — the phrasing that already classified correctly",
        "gh: API rate limit exceeded for installation ID 131208965. (HTTP 403)",
        "rate_limited",
    ),
    (
        "bare throttle status, no body at all",
        "gh: HTTP 429",
        "rate_limited",
    ),
    (
        "secondary limit, the phrasing that names itself",
        "gh: You have exceeded a secondary rate limit. Please wait a few "
        "minutes before you try again. (HTTP 403)",
        "rate_limited",
    ),
    (
        "secondary limit as abuse detection",
        "gh: You have triggered an abuse detection mechanism. Please wait a "
        "few minutes before you try again. (HTTP 403)",
        "rate_limited",
    ),
    (
        "secondary limit as a quota",
        "gh: You have exceeded a secondary quota. Please wait a few minutes "
        "before you try again. (HTTP 403)",
        "rate_limited",
    ),
    (
        "a GENUINE permission denial, sharing 403 with the three above",
        "gh: Resource not accessible by integration (HTTP 403)",
        "forbidden",
    ),
    (
        "a GENUINE credential rejection",
        "gh: Bad credentials (HTTP 401)",
        "forbidden",
    ),
    (
        "an absent thing, which carries real information",
        "gh: Not Found (HTTP 404)",
        "not_found",
    ),
)


def test_a_secondary_rate_limit_is_told_apart_from_a_permission_denial() -> None:
    """Both are HTTP 403 and their remedies are OPPOSITE: wait, versus fix access.

    Classifying a throttle as `forbidden` marks a self-clearing failure permanent,
    which blinds an obligation row that a bare rerun would have satisfied. Widening
    far enough to swallow a real denial is the reciprocal defect — it converts a
    permanent authorization failure into an endless retry — so both directions are
    asserted from the same table.
    """
    for label, stderr, expected in _CLASSIFICATION_CASES:
        assert classify_gh_failure(stderr=stderr) == expected, label


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
