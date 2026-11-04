"""Original workflow completion preserves missing work and correction obligations."""

from dataclasses import replace
from typing import Any

import pytest

from livespec_dev_tooling._incident_run_types import (
    CorrectedAttempt,
    EvidenceRefusal,
    ExpectedJob,
    ObservedJob,
    OriginalRun,
    RunEvidence,
    RunSnapshot,
)
from livespec_dev_tooling.incident_run_evidence import (
    build_run_evidence,
    evidence_digest,
    validate_correction,
)


def original(**changes: Any) -> OriginalRun:
    record = OriginalRun(
        repository="owner/repo",
        item_id="incident-1",
        attempt_id="attempt-1",
        operation_id="operation-1",
        generation=1,
        owner="incident-owner",
        pr_number=12,
        merge_sha="a" * 40,
        tree_sha="b" * 40,
        revert_sha="c" * 40,
        run_id=42,
        run_attempt=1,
        workflow_path=".github/workflows/ci.yml",
        graph_revision="a" * 40,
        graph_digest="digest",
        expected=(
            ExpectedJob(name="test"),
            ExpectedJob(name="coverage", needs=("test",)),
            ExpectedJob(name="other"),
        ),
    )
    return replace(record, **changes)


def job(
    *,
    name: str = "test",
    conclusion: str | None = "failure",
    status: str = "completed",
    job_id: int = 10,
) -> ObservedJob:
    return ObservedJob(
        name=name,
        job_id=job_id,
        status=status,
        conclusion=conclusion,
        evidence_url="https://forge.invalid/job/" + str(job_id),
    )


def snapshot(**changes: Any) -> RunSnapshot:
    return replace(
        RunSnapshot(
            repository="owner/repo",
            run_id=42,
            run_attempt=1,
            head_sha="a" * 40,
            status="completed",
            graph_digest="digest",
            complete_listing=True,
            jobs=(job(), job(name="coverage", conclusion="skipped", job_id=11)),
        ),
        **changes,
    )


def evidence(**changes: Any) -> RunEvidence:
    value = build_run_evidence(
        original=original(), snapshot=snapshot(**changes), continuation_id="original-tree-proof-42"
    )
    assert isinstance(value, RunEvidence)
    return value


def proposal(*, collected: RunEvidence, **changes: Any) -> CorrectedAttempt:
    return replace(
        CorrectedAttempt(
            original=collected.original,
            evidence_digest=evidence_digest(evidence=collected),
            classification_receipt="canonical-classification-1",
            next_attempt_id="attempt-2",
            next_head_sha="d" * 40,
            repair_diff_digest="real-repair-diff",
            resolved_jobs=(),
        ),
        **changes,
    )


def test_terminal_run_is_not_proof_that_every_expected_check_ran() -> None:
    collected = evidence()
    assert collected.terminal
    assert [(row.name, row.state) for row in collected.jobs] == [
        ("test", "failed"),
        ("coverage", "prerequisite-blocked"),
        ("other", "never-created"),
    ]
    assert [
        (row.job_name, row.owner, row.original_tree, row.continuation_id) for row in collected.debts
    ] == [
        ("coverage", "incident-owner", "b" * 40, "original-tree-proof-42"),
        ("other", "incident-owner", "b" * 40, "original-tree-proof-42"),
    ]


@pytest.mark.parametrize(
    ("conclusion", "state"),
    [
        ("success", "completed"),
        ("failure", "failed"),
        ("timed_out", "failed"),
        ("action_required", "failed"),
        ("startup_failure", "failed"),
        ("cancelled", "cancelled"),
        ("skipped", "skipped"),
        ("neutral", "unverified"),
        ("stale", "unverified"),
    ],
)
def test_job_states_remain_distinct(conclusion: str, state: str) -> None:
    collected = evidence(jobs=(job(conclusion=conclusion),))
    assert collected.jobs[0].state == state
    assert ("test" in {row.job_name for row in collected.debts}) == (
        state not in {"completed", "failed"}
    )


def test_running_original_retains_pending_checks_after_revert() -> None:
    collected = evidence(status="in_progress", jobs=(job(status="in_progress", conclusion=None),))
    assert not collected.terminal
    assert {row.state for row in collected.jobs} == {"pending"}
    assert isinstance(
        validate_correction(evidence=collected, proposal=proposal(collected=collected)),
        EvidenceRefusal,
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"repository": "other/repo"},
        {"run_id": 43},
        {"run_attempt": 2},
        {"head_sha": "other"},
        {"graph_digest": "other"},
        {"complete_listing": False},
        {"status": "unknown"},
        {"jobs": (job(), job())},
        {"jobs": (job(), job(name="other"))},
        {"jobs": (job(job_id=0),)},
        {"jobs": (job(conclusion="unknown"),)},
        {"jobs": (job(status="unknown"),)},
        {"jobs": (job(status="queued"),)},
        {"jobs": (job(status="queued", conclusion=None),)},
        {"jobs": (replace(job(), evidence_url=""),)},
    ],
)
def test_foreign_partial_or_inconsistent_observations_refuse(changes: dict[str, Any]) -> None:
    value = build_run_evidence(
        original=original(), snapshot=snapshot(**changes), continuation_id="owned"
    )
    assert isinstance(value, EvidenceRefusal)


@pytest.mark.parametrize(
    "changes",
    [
        {"owner": ""},
        {"run_attempt": 0},
        {"graph_revision": "wrong"},
        {"expected": ()},
        {"expected": (ExpectedJob(name=""),)},
        {"expected": (ExpectedJob(name="one"), ExpectedJob(name="one"))},
        {"expected": (ExpectedJob(name="one", needs=("missing",)),)},
        {
            "expected": (
                ExpectedJob(name="one", needs=("two",)),
                ExpectedJob(name="two", needs=("one",)),
            )
        },
    ],
)
def test_invalid_original_identity_or_graph_refuses(changes: dict[str, Any]) -> None:
    assert isinstance(
        build_run_evidence(
            original=original(**changes), snapshot=snapshot(), continuation_id="owned"
        ),
        EvidenceRefusal,
    )


def test_graph_order_can_differ_from_dependency_order() -> None:
    source = original(
        expected=(ExpectedJob(name="coverage", needs=("test",)), ExpectedJob(name="test"))
    )
    value = build_run_evidence(original=source, snapshot=snapshot(), continuation_id="owned")
    assert isinstance(value, RunEvidence)
    assert value.jobs[0].state == "prerequisite-blocked"
    assert isinstance(
        build_run_evidence(original=source, snapshot=snapshot(), continuation_id=""),
        EvidenceRefusal,
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"original": original(pr_number=99)},
        {"evidence_digest": "foreign"},
        {"classification_receipt": ""},
        {"next_attempt_id": ""},
        {"next_attempt_id": "attempt-1"},
        {"next_head_sha": ""},
        {"repair_diff_digest": "", "resolved_jobs": ()},
        {"resolved_jobs": (("test", ""),)},
        {"resolved_jobs": (("test", "r"), ("test", "r"))},
        {"resolved_jobs": (("foreign", "r"),)},
    ],
)
def test_invalid_correction_or_timestamp_only_retry_refuses(changes: dict[str, Any]) -> None:
    collected = evidence()
    assert isinstance(
        validate_correction(evidence=collected, proposal=proposal(collected=collected, **changes)),
        EvidenceRefusal,
    )


def test_correction_preserves_all_prior_identities_and_requires_repair_or_full_resolution() -> None:
    collected = evidence()
    repaired = proposal(collected=collected)
    assert validate_correction(evidence=collected, proposal=repaired) == repaired
    resolved = proposal(
        collected=collected,
        next_head_sha=collected.original.merge_sha,
        repair_diff_digest="",
        resolved_jobs=tuple((row.name, "measured:" + row.name) for row in collected.jobs),
    )
    assert validate_correction(evidence=collected, proposal=resolved) == resolved
    assert isinstance(
        validate_correction(
            evidence=collected, proposal=replace(resolved, resolved_jobs=(("test", "measured"),))
        ),
        EvidenceRefusal,
    )
    successful = evidence(
        jobs=(
            job(conclusion="success"),
            job(name="coverage", conclusion="success", job_id=11),
            job(name="other", conclusion="success", job_id=12),
        )
    )
    assert isinstance(
        validate_correction(
            evidence=successful, proposal=proposal(collected=successful, repair_diff_digest="")
        ),
        EvidenceRefusal,
    )
