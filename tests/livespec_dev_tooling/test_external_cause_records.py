"""Coverage for external-cause records beyond the Red 403 scenario."""

from __future__ import annotations

import pytest

from livespec_dev_tooling.external_cause import classify_external_cause

__all__: list[str] = []


def _classify(**changes: object):
    """Classify one GitHub failure with safe defaults for each test."""
    arguments: dict[str, object] = {
        "dependency": "github",
        "status": None,
        "headers": {},
        "body": "",
        "stderr": "",
    }
    arguments.update(changes)
    return classify_external_cause(**arguments)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("status", "headers", "body", "evidence"),
    [
        (403, {"Retry-After": "10"}, "{}", "retry-after: 10"),
        (429, {"x-ratelimit-remaining": "0"}, "{}", "x-ratelimit-remaining: 0"),
        (429, {}, '{"message":"rate limit exceeded"}', "HTTP 429"),
    ],
)
def test_rate_limit_evidence_emits_one_serializable_record(
    *, status: int, headers: dict[str, str], body: str, evidence: str
) -> None:
    """A response's distinct rate-limit proofs all publish the same kind."""
    record = _classify(status=status, headers=headers, body=body)

    assert record is not None
    assert record.as_dict() == {
        "dependency": "github",
        "kind": "rate_limited",
        "evidence": record.evidence,
    }
    assert evidence in record.evidence


def test_a_forge_5xx_emits_the_server_error_record() -> None:
    """A forge server response is an external cause with observed HTTP evidence."""
    record = _classify(status=502, body="Bad Gateway")

    assert record is not None
    assert (record.kind, record.evidence) == ("server_error", "HTTP 502: Bad Gateway")


def test_a_documented_dependency_outage_is_preserved_as_external() -> None:
    """The caller can publish an independently documented dependency outage."""
    record = _classify(status=404, body="temporarily unavailable", documented_outage=True)

    assert record is not None
    assert (record.kind, record.evidence) == (
        "third_party_outage",
        "HTTP 404: temporarily unavailable",
    )


@pytest.mark.parametrize(
    ("stderr", "kind"),
    [
        ("could not resolve host: api.github.com", "dns_failure"),
        ("dial tcp: connection refused", "connect_failure"),
        ("request timed out after 30 seconds", "timeout"),
    ],
)
def test_external_transport_failures_emit_their_matching_kind(*, stderr: str, kind: str) -> None:
    """Only failures to an externally run host are publishable transport causes."""
    record = _classify(stderr=stderr)

    assert record is not None
    assert (record.kind, record.evidence) == (kind, stderr)


@pytest.mark.parametrize(
    "changes",
    [
        {"status": 401, "body": "Bad credentials"},
        {"status": 403, "body": "Resource not accessible by integration"},
        {"stderr": "gh: command not found"},
        {"stderr": "could not resolve host: internal.example", "fleet_runs_host": True},
    ],
)
def test_credential_local_and_fleet_failures_do_not_emit_external_records(
    *, changes: dict[str, object]
) -> None:
    """Only independently evidenced dependency failures become external records."""
    assert _classify(**changes) is None
