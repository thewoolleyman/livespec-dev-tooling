"""Signed synthetic merge and exact check identity need independent complete forge reads."""

from __future__ import annotations

import copy
from dataclasses import replace

import pytest

from livespec_dev_tooling import incident_ci_job_identity as forge
from livespec_dev_tooling._incident_observer_types import ObserverArmQuery
from livespec_dev_tooling.incident_ci_oidc import verify_oidc
from livespec_dev_tooling.incident_forge_reads import ForgeReads
from tests.livespec_dev_tooling import test_incident_ci_identity_policy as policy_tests

trusted = policy_tests.trusted

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-rqhqnb


def observations(query):
    repository = {"full_name": "owner/repo", "id": 123, "owner": {"id": 456}}
    run = {
        "id": 812,
        "run_attempt": 2,
        "event": "pull_request",
        "head_sha": query.head_sha,
        "head_branch": "repair",
        "path": ".github/workflows/ci.yml",
        "repository": repository,
        "check_suite_id": 77,
        "pull_requests": [],
    }
    pr = {
        "number": 55,
        "state": "open",
        "merged": False,
        "merge_commit_sha": "d" * 40,
        "base": {"sha": query.base_sha, "ref": "master", "repo": repository},
        "head": {"sha": query.head_sha, "ref": "repair"},
    }
    job = {
        "id": 1011,
        "run_id": 812,
        "head_sha": query.head_sha,
        "check_run_url": "https://api.github.com/repos/owner/repo/check-runs/913",
    }
    return {
        "repos/owner/repo/actions/runs/812": run,
        "repos/owner/repo/actions/runs/812/attempts/2": copy.deepcopy(run),
        "repos/owner/repo/pulls/55": pr,
        "repos/owner/repo/git/commits/" + "d" * 40: {
            "sha": "d" * 40,
            "parents": [{"sha": query.base_sha}, {"sha": query.head_sha}],
        },
        "repos/owner/repo/actions/runs/812/attempts/2/jobs?per_page=100&page=1": {
            "total_count": 1,
            "jobs": [job],
        },
        "repos/owner/repo/check-runs/913": {
            "id": 913,
            "head_sha": query.head_sha,
            "check_suite": {"id": 77},
            "app": {"id": 15368, "slug": "github-actions"},
            "pull_requests": [],
        },
    }


@pytest.fixture
def correlated(trusted, monkeypatch):
    _, policy, token, *_ = trusted
    identity = verify_oidc(token=token, policy=policy, now=1700000010)
    assert identity is not None
    query = ObserverArmQuery(
        repository="owner/repo",
        arm_id="a" * 64,
        receipt_digest="b" * 64,
        pr_number=55,
        base_sha="e" * 40,
        head_sha="c" * 40,
    )
    records, calls = observations(query), []

    def read(path):
        calls.append(path)
        return copy.deepcopy(records.get(path, {}))

    monkeypatch.setattr(ForgeReads, "installed", classmethod(lambda _cls, **_: read))
    return forge.CiJobVerifier(identity=identity, query=query, read=read), records, calls


def test_exact_attempt_job_resolves_check_without_equal_job_id_or_pr_arrays(correlated):
    verifier, _, calls = correlated
    identity = verifier.verify()
    assert identity is not None and identity.job_id == 1011 and identity.check_suite_id == 77
    assert calls.count("repos/owner/repo/actions/runs/812") == 2
    assert calls.count("repos/owner/repo/pulls/55") == 2


@pytest.mark.parametrize(
    ("record", "field", "value"),
    [
        ("actions/runs/812", "run_attempt", 3),
        ("actions/runs/812/attempts/2", "run_attempt", 1),
        ("actions/runs/812/attempts/2", "check_suite_id", 78),
        ("actions/runs/812", "event", "push"),
        ("actions/runs/812", "head_sha", "d" * 40),
        ("actions/runs/812", "repository", {"full_name": "owner/repo", "id": 999}),
        ("pulls/55", "merged", True),
        ("pulls/55", "state", "closed"),
        ("pulls/55", "merge_commit_sha", "a" * 40),
        ("pulls/55", "head", {}),
        ("git/commits/" + "d" * 40, "parents", [{"sha": "c" * 40}, {"sha": "e" * 40}]),
        ("git/commits/" + "d" * 40, "parents", [None]),
        ("check-runs/913", "id", 914),
        ("check-runs/913", "head_sha", "d" * 40),
        ("check-runs/913", "app", {"id": 15368, "slug": "forged"}),
        ("check-runs/913", "app", {"id": 99, "slug": "github-actions"}),
        ("check-runs/913", "check_suite", {"id": 78}),
    ],
)
def test_conflicting_or_unsupported_forge_shape_refuses(correlated, record, field, value):
    verifier, records, _ = correlated
    records["repos/owner/repo/" + record][field] = value
    assert verifier.verify() is None


@pytest.mark.parametrize(
    "change",
    [
        "missing",
        "duplicate-check",
        "duplicate-job",
        "wrong-run",
        "wrong-head",
        "foreign-url",
        "bad-total",
        "incomplete",
        "rows-type",
        "row-type",
        "too-many",
    ],
)
def test_jobs_require_complete_unambiguous_exact_attempt(correlated, change):
    verifier, records, _ = correlated
    page = records["repos/owner/repo/actions/runs/812/attempts/2/jobs?per_page=100&page=1"]
    job = page["jobs"][0]
    if change == "missing":
        page["jobs"] = []
    elif change in {"duplicate-check", "duplicate-job"}:
        page["jobs"].append(job | {"id": 1012 if change == "duplicate-check" else 1011})
        page["total_count"] = 2
    elif change == "wrong-run":
        job["run_id"] = 999
    elif change == "wrong-head":
        job["head_sha"] = "d" * 40
    elif change == "foreign-url":
        job["check_run_url"] = "https://attacker/check-runs/913"
    elif change == "bad-total":
        page["total_count"] = True
    elif change == "incomplete":
        page["total_count"] = 2
    elif change == "rows-type":
        page["jobs"] = {}
    elif change == "row-type":
        page["jobs"] = [None]
    else:
        page["total_count"] = 1001
    assert verifier.verify() is None


def test_bounded_multiple_pages_and_consistent_final_observation(correlated):
    verifier, records, _ = correlated
    path = "repos/owner/repo/actions/runs/812/attempts/2/jobs?per_page=100&page="
    actual = records[path + "1"]["jobs"][0]
    records[path + "1"] = {
        "total_count": 101,
        "jobs": [{"id": 2000 + i, "check_run_url": "other"} for i in range(100)],
    }
    records[path + "2"] = {"total_count": 101, "jobs": [actual]}
    assert verifier.verify() is not None
    records[path + "2"]["total_count"] = 102
    assert verifier.verify() is None


@pytest.mark.parametrize("target", ["latest", "pr", "jobs"])
def test_final_rerun_pr_or_pagination_change_refuses(correlated, target):
    verifier, records, calls = correlated
    selected = {
        "latest": "repos/owner/repo/actions/runs/812",
        "pr": "repos/owner/repo/pulls/55",
        "jobs": "repos/owner/repo/actions/runs/812/attempts/2/jobs?per_page=100&page=1",
    }[target]

    def read(path):
        calls.append(path)
        data = copy.deepcopy(records.get(path, {}))
        if path == selected and calls.count(path) > 1:
            data.update({"run_attempt": 3, "state": "closed", "total_count": 2})
        return data

    assert replace(verifier, read=read).verify() is None


def test_mismatched_arm_and_unavailable_forge_refuse(correlated):
    verifier, _, _ = correlated
    assert replace(verifier, query=replace(verifier.query, pr_number=56)).verify() is None
    for answer in (None, [], "not-an-object"):
        assert replace(verifier, read=lambda _path, answer=answer: answer).verify() is None


def test_pagination_bound_rejects_truncated_attempt_and_invalid_job_ids(correlated):
    verifier, records, _ = correlated
    path = "repos/owner/repo/actions/runs/812/attempts/2/jobs?per_page=100&page="
    actual = records[path + "1"]["jobs"][0]
    for page in range(1, 11):
        records[path + str(page)] = {"total_count": 1000, "jobs": [actual | {"id": page}]}
    assert verifier.verify() is None
    records[path + "1"] = {"total_count": 1, "jobs": [actual | {"id": True}]}
    assert verifier.verify() is None


def test_final_suite_boolean_cannot_equal_a_valid_integer_suite(correlated):
    verifier, records, calls = correlated
    path = "repos/owner/repo/actions/runs/812"
    records[path]["check_suite_id"] = 1
    records[path + "/attempts/2"]["check_suite_id"] = 1
    records["repos/owner/repo/check-runs/913"]["check_suite"]["id"] = 1

    def read(requested):
        calls.append(requested)
        data = copy.deepcopy(records.get(requested, {}))
        if requested == path and calls.count(path) > 1:
            data["check_suite_id"] = True
        return data

    assert replace(verifier, read=read).verify() is None
