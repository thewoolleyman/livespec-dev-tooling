"""Historical reads use the retained exact attempt and never manufacture success."""

from __future__ import annotations

import subprocess

import pytest

from livespec_dev_tooling import incident_ci_job_identity as forge
from livespec_dev_tooling.incident_ci_job_history import classify_snapshot, observe_retained_job
from tests.livespec_dev_tooling import test_incident_ci_attachment_edges as edge_tests

trusted = edge_tests.trusted
correlated = edge_tests.correlated
authenticated = edge_tests.authenticated
attached = edge_tests.attached

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-si6uu7
_JOBS = "repos/owner/repo/actions/runs/812/attempts/2/jobs?per_page=100&page=1"
CHECK = "repos/owner/repo/check-runs/913"
_ATTEMPT = "repos/owner/repo/actions/runs/812/attempts/2"


def conclude(records, *, job=("completed", "success"), check=("completed", "success")):
    records[_JOBS]["jobs"][0].update(status=job[0], conclusion=job[1])
    records[CHECK].update(status=check[0], conclusion=check[1])


@pytest.mark.parametrize(
    ("job", "check", "expected"),
    [
        (("completed", "success"), ("completed", "success"), "successful"),
        (("completed", "failure"), ("completed", "failure"), "failed"),
        (("completed", "timed_out"), ("completed", "timed_out"), "failed"),
        (("completed", "skipped"), ("completed", "skipped"), "skipped"),
        (("completed", "cancelled"), ("completed", "cancelled"), "cancelled"),
        (("in_progress", None), ("queued", None), "pending"),
        (("completed", "neutral"), ("completed", "neutral"), "unavailable"),
        (("completed", None), ("completed", None), "unavailable"),
        (("completed", "success"), ("completed", "failure"), "conflict"),
        (("completed", "success"), ("in_progress", None), "conflict"),
        ((None, None), ("completed", "success"), "unavailable"),
        (("completed", "Success!"), ("completed", "success"), "unavailable"),
    ],
)
def test_snapshot_requires_coherent_completed_success(attached, job, check, expected):
    conclude(attached.records, job=job, check=check)
    status, facts = observe_retained_job(binding=attached.receipt["binding"])
    assert status == expected == facts["snapshot_status"]
    if expected != "unavailable" or job[1] != "Success!":
        assert (facts["job_status"], facts["check_conclusion"]) == (job[0], check[1])


def test_classification_never_defaults_to_success():
    assert classify_snapshot(
        job_status="completed", job_conclusion=1, check_status="completed", check_conclusion=1
    ) == ("unavailable", "unclassified completed conclusion")


def test_history_ignores_closed_pr_later_attempt_and_expired_token(attached, monkeypatch):
    import time

    records = attached.records
    conclude(records)
    records["repos/owner/repo/pulls/55"].update(state="closed", merged=True)
    records["repos/owner/repo/actions/runs/812"]["run_attempt"] = 3
    attached.application.installation.ci_identity_policy = None
    monkeypatch.setattr(time, "time", lambda: 1800000000)
    before = len(attached.calls)
    assert observe_retained_job(binding=attached.receipt["binding"])[0] == "successful"
    read = attached.calls[before:]
    assert "repos/owner/repo/pulls/55" not in read
    assert "repos/owner/repo/actions/runs/812" not in read
    assert _ATTEMPT in read and CHECK in read


@pytest.mark.parametrize(
    ("path", "field", "value"),
    [
        (_ATTEMPT, "check_suite_id", 78),
        (_ATTEMPT, "run_attempt", 3),
        (_ATTEMPT, "head_sha", "d" * 40),
        (_ATTEMPT, "event", "push"),
        (_ATTEMPT, "repository", {"full_name": "owner/repo", "id": 123, "owner": {"id": 9}}),
        (CHECK, "app", {"id": 15368, "slug": "forged"}),
        (CHECK, "check_suite", {"id": True}),
        (CHECK, "head_sha", "d" * 40),
        (CHECK, "id", 914),
    ],
)
def test_contradicting_forge_identity_is_conflict(attached, path, field, value):
    conclude(attached.records)
    attached.records[path][field] = value
    status, facts = observe_retained_job(binding=attached.receipt["binding"])
    assert status == "conflict" and facts["job_conclusion"] is None


@pytest.mark.parametrize(
    "change", ["foreign-url", "other-id", "duplicate", "wrong-run", "wrong-head", "bool-run"]
)
def test_exact_job_and_canonical_check_url_required(attached, change):
    conclude(attached.records)
    page = attached.records[_JOBS]
    job = page["jobs"][0]
    if change == "foreign-url":
        job["check_run_url"] = "https://attacker/check-runs/913"
    elif change == "other-id":
        job["id"] = 1012
    elif change == "duplicate":
        page["jobs"].append(dict(job))
        page["total_count"] = 2
    elif change == "wrong-run":
        job["run_id"] = 813
    elif change == "wrong-head":
        job["head_sha"] = "d" * 40
    else:
        job["run_id"] = True
    status, _ = observe_retained_job(binding=attached.receipt["binding"])
    assert status in {"conflict", "unavailable"} and status != "successful"


def test_complete_pagination_finds_retained_job_on_later_page(attached):
    conclude(attached.records)
    actual = attached.records[_JOBS]["jobs"][0]
    attached.records[_JOBS] = {
        "total_count": 101,
        "jobs": [{"id": 3000 + i, "check_run_url": "other"} for i in range(100)],
    }
    attached.records[_JOBS[: -len("1")] + "2"] = {"total_count": 101, "jobs": [actual]}
    assert observe_retained_job(binding=attached.receipt["binding"])[0] == "successful"


@pytest.mark.parametrize("missing", [_ATTEMPT, CHECK, _JOBS])
def test_unavailable_forge_is_unavailable_not_success(attached, monkeypatch, missing):
    conclude(attached.records)
    del attached.records[missing]
    assert observe_retained_job(binding=attached.receipt["binding"])[0] == "unavailable"

    def down(*, args, **_kwargs):
        return subprocess.CompletedProcess(args, 1, "", "private")

    monkeypatch.setattr(forge, "gh_read", down)
    status, facts = observe_retained_job(binding=attached.receipt["binding"])
    assert status == "unavailable" and "private" not in facts["reason"]
