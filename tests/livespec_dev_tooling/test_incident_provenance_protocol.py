"""Malformed canonical process replies cannot become historical proof."""

from __future__ import annotations

import json
from dataclasses import asdict

import pytest

from livespec_dev_tooling._incident_provenance_protocol import decode_historical_reply
from livespec_dev_tooling.incident_provenance import IncidentCommitQuery

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-gvylzw


def _query() -> IncidentCommitQuery:
    return IncidentCommitQuery(
        repository="owner/repo",
        item_id="incident-1",
        attempt_id="attempt-2",
        phase="repair",
        operation_id="operation-3",
        generation=4,
        owner="operator-5",
        base="a" * 40,
        head="b" * 40,
        pr_number=6,
        commit_sha="c" * 40,
        tree_sha="d" * 40,
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("landed_commits", [1]),
        ("landed_trees", "not a list"),
        ("original_paths", [False]),
        ("original_paths", []),
        ("deferred_work", None),
        ("repayment_required", "false"),
    ],
)
def test_malformed_landed_scope_is_refused(field: str, value: object) -> None:
    query = _query()
    attempt: dict[str, object] = dict(asdict(query))
    del attempt["commit_sha"]
    del attempt["tree_sha"]
    attempt.update(
        landed_commits=[query.commit_sha],
        landed_trees=[query.tree_sha],
        original_paths=["src/repair.py"],
        deferred_work=["full-replay"],
        repayment_required=True,
    )
    attempt[field] = value
    response = {
        "schema": 1,
        "status": "verified",
        "authorizes_current_effects": False,
        "normal_factory_proof": False,
        "result": {"attempt": attempt, "committed_token_id": "old", "current_token_id": "current"},
    }
    result = decode_historical_reply(stdout=json.dumps(response), returncode=0, query=query)
    assert result.failure().code == "incident-reader-invalid-response"


@pytest.mark.parametrize(
    ("status", "result"),
    [
        ("verified", {"code": "canonical-refusal", "detail": "reason"}),
        ("refused", {}),
        ("refused", {"code": False, "detail": "reason"}),
        ("refused", {"code": "canonical-refusal", "detail": []}),
    ],
)
def test_refusal_process_requires_an_actual_named_refusal(
    status: str, result: dict[str, object]
) -> None:
    response = {
        "schema": 1,
        "status": status,
        "result": result,
        "authorizes_current_effects": False,
        "normal_factory_proof": False,
    }
    decoded = decode_historical_reply(stdout=json.dumps(response), returncode=78, query=_query())
    assert decoded.failure().code == "incident-reader-invalid-response"
