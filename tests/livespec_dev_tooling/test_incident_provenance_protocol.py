"""Malformed canonical process replies cannot become historical proof."""

from __future__ import annotations

from dataclasses import asdict

import pytest

from livespec_dev_tooling._incident_provenance_protocol import decode_historical_result
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
    result = decode_historical_result(
        result={"attempt": attempt, "committed_token_id": "old", "current_token_id": "current"},
        query=query,
    )
    assert result.failure().code == "incident-reader-invalid-response"
