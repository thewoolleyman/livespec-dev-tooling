"""The incident-merge principal accepts the genesis the released writer actually publishes."""

from __future__ import annotations

from unittest.mock import Mock

from returns.result import Success

from livespec_dev_tooling.incident_merge_authority import (
    MergeAuthorityVerdict,
    decide,
)

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-nrb3oa

_BASE = "e" * 40
_HEAD = "c" * 40


def _reading(*, writer: object) -> dict[str, object]:
    return {
        "genesis_writer": writer,
        "item_status": "active",
        "is_current": True,
        "attempt": {
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
        },
    }


def _decide(*, writer: object) -> MergeAuthorityVerdict:
    return decide(
        reader=Mock(return_value=Success(_reading(writer=writer))),
        incident_id="incident-1",
        pr_number=55,
        base_sha=_BASE,
        head_sha=_HEAD,
    )


def test_a_publish_genesis_genesis_allows_the_merge():
    verdict = _decide(writer="publish-genesis")
    assert verdict == MergeAuthorityVerdict(allowed=True, reason=None, detail="incident-1")


def test_any_other_genesis_writer_is_refused_and_named():
    verdict = _decide(writer="file-incident")
    facts = [
        verdict.allowed is False,
        verdict.reason == "no-genesis-record",
        "file-incident" in verdict.detail,
        "publish-genesis" in verdict.detail,
    ]
    assert all(facts)
