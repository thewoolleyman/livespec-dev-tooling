"""Malformed canonical process replies cannot become historical proof."""

from __future__ import annotations

from dataclasses import asdict, replace
from typing import Any

import pytest
from returns.pipeline import is_successful

from livespec_dev_tooling._incident_provenance_protocol import decode_historical_result
from livespec_dev_tooling._incident_provenance_types import IncidentCommitQuery

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


def _result() -> dict[str, Any]:
    query = _query()
    attempt: dict[str, Any] = dict(asdict(query))
    del attempt["commit_sha"]
    del attempt["tree_sha"]
    attempt.update(
        landed_commits=["c" * 40, "e" * 40],
        landed_trees=["d" * 40, "f" * 40],
        original_paths=["src/repair.py"],
        deferred_work=["full-replay"],
        repayment_required=True,
    )
    return {
        "attempt": attempt,
        "committed_token_id": "token-old",
        "current_token_id": "token-current",
    }


def test_a_matching_receipt_retains_the_deferred_proof() -> None:
    decoded = decode_historical_result(result=_result(), query=_query())
    assert is_successful(decoded)
    proof = decoded.unwrap()
    assert proof.query == _query()
    assert proof.committed_token_id == "token-old"
    assert proof.current_token_id == "token-current"
    assert proof.original_paths == ("src/repair.py",)
    assert proof.deferred_work == ("full-replay",)
    assert proof.repayment_required is True


@pytest.mark.parametrize(
    "field",
    [
        "repository",
        "item_id",
        "attempt_id",
        "phase",
        "operation_id",
        "generation",
        "owner",
        "base",
        "head",
        "pr_number",
    ],
)
def test_exact_receipt_fields_must_match(field: str) -> None:
    result = _result()
    result["attempt"][field] = "foreign"
    decoded = decode_historical_result(result=result, query=_query())
    assert decoded.failure().code == "incident-provenance-identity-mismatch"


@pytest.mark.parametrize("mutate", ["commit", "tree", "length", "bool_generation", "bool_pr"])
def test_landed_commit_and_tree_are_verified_as_one_pair(mutate: str) -> None:
    result = _result()
    attempt = result["attempt"]
    if mutate == "commit":
        attempt["landed_commits"][0] = "x" * 40
    elif mutate == "tree":
        attempt["landed_trees"].reverse()
    elif mutate == "length":
        attempt["landed_trees"] = []
    elif mutate == "bool_generation":
        attempt["generation"] = True
    else:
        attempt["pr_number"] = True
    assert not is_successful(decode_historical_result(result=result, query=_query()))


@pytest.mark.parametrize("field", ["attempt", "committed_token_id", "current_token_id"])
def test_incomplete_historical_proof_is_refused(field: str) -> None:
    result = _result()
    del result[field]
    decoded = decode_historical_result(result=result, query=_query())
    assert decoded.failure().code == "incident-reader-invalid-response"


def test_a_later_landed_commit_is_not_reduced_to_the_terminal_sha() -> None:
    query = replace(_query(), commit_sha="e" * 40, tree_sha="f" * 40)
    decoded = decode_historical_result(result=_result(), query=query)
    assert is_successful(decoded)
    assert decoded.unwrap().query == query
