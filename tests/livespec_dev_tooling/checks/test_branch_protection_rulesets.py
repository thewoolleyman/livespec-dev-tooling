"""Unit coverage for malformed ruleset bodies in branch-protection reads."""

from __future__ import annotations

from livespec_dev_tooling.checks._branch_protection_rulesets import (
    _non_app_bypass,
    _ruleset_read_failure,
)

__all__: list[str] = []


def test_malformed_ruleset_body_is_unreadable_not_an_exception() -> None:
    """An invalid forge body is recorded as a retryable read failure."""
    assert _non_app_bypass(stdout="{") is None
    assert _ruleset_read_failure(stdout="{", stderr="", returncode=0) == "body was not valid JSON"
