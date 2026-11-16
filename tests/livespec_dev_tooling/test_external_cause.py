"""Contract tests for the shared external-cause classifier.

The master-green external-red contract distinguishes a credential failure from
a rate-limited forge response even though both can arrive as HTTP 403.
"""

from __future__ import annotations

import importlib

__all__: list[str] = []


def _classify_external_cause():
    """Load the shared helper after asserting the module is supplied."""
    try:
        module = importlib.import_module("livespec_dev_tooling.external_cause")
    except ModuleNotFoundError:
        module = None

    assert module is not None, "the shared external-cause helper module must exist"
    return module.classify_external_cause


def test_a_403_with_an_exhausted_rate_limit_header_emits_a_rate_limit_record() -> None:
    """A forge's exhausted-quota 403 is external, not an App credential defect."""
    record = _classify_external_cause()(
        dependency="github",
        status=403,
        headers={"x-ratelimit-remaining": "0"},
        body='{"message":"API rate limit exceeded"}',
        stderr="gh: API rate limit exceeded (HTTP 403)",
    )

    assert record is not None
    assert (record.dependency, record.kind) == ("github", "rate_limited")
    assert "x-ratelimit-remaining: 0" in record.evidence
