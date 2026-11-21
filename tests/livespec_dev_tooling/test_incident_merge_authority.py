"""The incident-merge principal decides from the canonical incident authority chain alone."""

from __future__ import annotations

from unittest.mock import Mock

import pytest
from returns.result import Failure, Success

from livespec_dev_tooling.incident_authority_client import AuthorityRefusal
from livespec_dev_tooling.incident_merge_authority import (
    MERGE_REFUSAL_REASONS,
    MergeAuthorityVerdict,
    decide,
)

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-u3nbm3

_BASE = "e" * 40
_HEAD = "c" * 40


def _attempt(**overrides: object) -> dict[str, object]:
    attempt: dict[str, object] = {
        "repository": "owner/repo",
        "item_id": "incident-1",
        "attempt_id": "repair-1",
        "phase": "repair",
        "operation_id": "operation-1",
        "generation": 2,
        "owner": "owner",
        "base": _BASE,
        "head": _HEAD,
        "pr_number": 55,
        "landed_commits": [],
        "landed_trees": [],
        "original_paths": ["module.py"],
        "deferred_work": [],
        "repayment_required": True,
        "carrier": {"state": "pr-bound", "target_ref": "refs/heads/incident-1"},
    }
    attempt.update(overrides)
    return attempt


def _reading(*, attempt: dict[str, object] | None = None, **overrides: object) -> dict[str, object]:
    reading: dict[str, object] = {
        "genesis_writer": "publish-genesis",
        "item_status": "active",
        "is_current": True,
        "attempt": _attempt() if attempt is None else attempt,
    }
    reading.update(overrides)
    return reading


def _decide(*, reply: object, pr_number: int = 55, base: str = _BASE, head: str = _HEAD):
    reader = Mock(return_value=reply)
    verdict = decide(
        reader=reader,
        incident_id="incident-1",
        pr_number=pr_number,
        base_sha=base,
        head_sha=head,
    )
    return verdict, reader


def test_a_publish_genesis_genesis_whose_current_attempt_binds_the_pr_allows_the_merge():
    verdict, reader = _decide(reply=Success(_reading()))
    facts = [
        verdict == MergeAuthorityVerdict(allowed=True, reason=None, detail="incident-1"),
        reader.call_count == 1,
        reader.call_args.kwargs == {"incident_id": "incident-1"},
    ]
    assert all(facts)


def test_the_refusal_reasons_are_the_closed_named_set():
    assert (
        frozenset(
            (
                "no-genesis-record",
                "incident-closed",
                "attempt-superseded",
                "attempt-not-pr-bound",
                "pr-number-mismatch",
                "base-head-mismatch",
                "incident-inverse",
            )
        )
        == MERGE_REFUSAL_REASONS
    )


@pytest.mark.parametrize(
    ("reply", "reason"),
    [
        (
            Failure(
                AuthorityRefusal(code="incident-authority-missing", detail="x", canonical=True)
            ),
            "no-genesis-record",
        ),
        (
            Failure(AuthorityRefusal(code="incident-authority-timeout", detail="hung")),
            "no-genesis-record",
        ),
        (Success(_reading(genesis_writer="file-incident")), "no-genesis-record"),
        (
            Success({k: v for k, v in _reading().items() if k != "genesis_writer"}),
            "no-genesis-record",
        ),
        (Success(_reading(attempt=_attempt(item_id="incident-2"))), "no-genesis-record"),
        (Success(_reading(item_status="closed")), "incident-closed"),
        (Success(_reading(attempt=_attempt(phase="closed"))), "incident-closed"),
        (Success(_reading(attempt=_attempt(phase="drill-closed"))), "incident-closed"),
        (Success(_reading(is_current=False)), "attempt-superseded"),
        (Success(_reading(is_current="true")), "attempt-superseded"),
        (Success(_reading(attempt=_attempt(phase="master-observation"))), "attempt-superseded"),
        (Success(_reading(attempt=_attempt(phase="repayment-active"))), "attempt-superseded"),
        (Success(_reading(attempt=_attempt(phase="reverting"))), "incident-inverse"),
        (Success(_reading(attempt=_attempt(phase="rollback-conflict"))), "incident-inverse"),
        (
            Success(_reading(attempt=_attempt(carrier={"state": "head-published"}))),
            "attempt-not-pr-bound",
        ),
        (Success(_reading(attempt=_attempt(carrier=None))), "attempt-not-pr-bound"),
        (Success(_reading(attempt=_attempt(pr_number=0))), "attempt-not-pr-bound"),
        (Success(_reading(attempt=_attempt(pr_number=True))), "attempt-not-pr-bound"),
        (Success(_reading(attempt=_attempt(pr_number=56))), "pr-number-mismatch"),
        (Success(_reading(attempt=_attempt(base="f" * 40))), "base-head-mismatch"),
        (Success(_reading(attempt=_attempt(head="d" * 40))), "base-head-mismatch"),
        (Success(_reading(attempt="not-an-object")), "attempt-not-pr-bound"),
    ],
)
def test_each_failed_condition_refuses_with_its_one_named_reason(reply, reason):
    verdict, _reader = _decide(reply=reply)
    facts = [
        verdict.allowed is False,
        verdict.reason == reason,
        verdict.reason in MERGE_REFUSAL_REASONS,
        bool(verdict.detail),
    ]
    assert all(facts)


def test_the_forge_read_pr_identity_must_match_the_bound_attempt():
    by_number, _ = _decide(reply=Success(_reading()), pr_number=54)
    by_base, _ = _decide(reply=Success(_reading()), base="a" * 40)
    by_head, _ = _decide(reply=Success(_reading()), head="b" * 40)
    facts = [
        by_number.reason == "pr-number-mismatch",
        by_base.reason == "base-head-mismatch",
        by_head.reason == "base-head-mismatch",
    ]
    assert all(facts)


def test_a_reader_refusal_names_the_authority_code_in_the_detail():
    refusal = AuthorityRefusal(code="incident-authority-ambiguous", detail="two roots")
    verdict, _ = _decide(reply=Failure(refusal))
    assert "incident-authority-ambiguous" in verdict.detail


def test_no_flag_or_environment_variable_stands_in_for_a_genesis_record(monkeypatch):
    monkeypatch.setenv("EXPEDITED_INCIDENT_RESPONSE", "1")
    monkeypatch.setenv("LIVESPEC_INCIDENT_MERGE", "1")
    missing = Failure(
        AuthorityRefusal(code="incident-authority-missing", detail="incident-1", canonical=True)
    )
    verdict, _ = _decide(reply=missing)
    assert verdict.reason == "no-genesis-record"
