"""An authenticated current incident identity cannot select an unrelated CI run."""

from __future__ import annotations

import copy
import json
import subprocess
from dataclasses import replace

import pytest

from livespec_dev_tooling._incident_observer_types import ObserverArm, ObserverRegistration
from livespec_dev_tooling.incident_observer_forge import MergedRunVerifier

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-47ij37


@pytest.fixture
def setup(monkeypatch):
    arm = ObserverArm(
        repository="owner/repo",
        incident_item_id="incident-1",
        attempt_id="repair-1",
        operation_id="operation-1",
        generation=1,
        owner="owner",
        phase="repair",
        pr_number=55,
        base_sha="e" * 40,
        head_sha="c" * 40,
        required_jobs=("coverage",),
        controller_release="v1.2.3",
        controller_revision="b" * 40,
        authority_receipt=b"canonical",
    )
    registration = ObserverRegistration(
        repository=arm.repository,
        incident_item_id=arm.incident_item_id,
        attempt_id=arm.attempt_id,
        operation_id=arm.operation_id,
        generation=arm.generation,
        owner=arm.owner,
        phase=arm.phase,
        head_sha="a" * 40,
        run_id=91,
        required_jobs=arm.required_jobs,
        controller_release=arm.controller_release,
        controller_revision=arm.controller_revision,
        candidate_revision=arm.head_sha,
        authority_receipt=arm.authority_receipt,
    )
    records = {
        "pulls/55": {
            "number": 55,
            "merged": True,
            "state": "closed",
            "merge_commit_sha": "a" * 40,
            "head": {"sha": "c" * 40},
            "base": {"ref": "master", "repo": {"full_name": "owner/repo"}},
        },
        "actions/runs/91": {
            "id": 91,
            "event": "push",
            "head_branch": "master",
            "head_sha": "a" * 40,
            "path": ".github/workflows/ci.yml",
            "repository": {"full_name": "owner/repo"},
            "head_repository": {"full_name": "owner/repo"},
            "status": "in_progress",
        },
    }
    calls = []

    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        key = argv[-1].removeprefix("repos/owner/repo/")
        record = records.get(key)
        if isinstance(record, Exception):
            raise record
        return subprocess.CompletedProcess(argv, 0, json.dumps(record), "")

    monkeypatch.setattr(subprocess, "run", run)
    return arm, registration, records, calls


def test_exact_merged_pr_and_running_master_push_bind_without_waiting_for_completion(setup):
    arm, registration, _, calls = setup
    assert MergedRunVerifier()(arm, registration)
    assert [call[0][-1] for call in calls] == [
        "repos/owner/repo/pulls/55",
        "repos/owner/repo/actions/runs/91",
    ]
    assert all(call[0][:2] == ["gh", "api"] for call in calls)
    assert all(call[1]["timeout"] == 10 for call in calls)


def test_malformed_repository_or_nonmaster_run_is_refused_before_api(setup):
    arm, registration, _, calls = setup
    assert not MergedRunVerifier()(replace(arm, repository="invalid"), registration)
    assert not MergedRunVerifier()(arm, replace(registration, branch="feature"))
    assert not MergedRunVerifier()(arm, replace(registration, run_id=0))
    assert not calls


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("number", True),
        ("number", 56),
        ("merged", False),
        ("state", "open"),
        ("merge_commit_sha", "f" * 40),
        ("head", []),
        ("base", []),
        ("head", {"sha": "f" * 40}),
        ("base", {"ref": "feature", "repo": {"full_name": "owner/repo"}}),
        ("base", {"ref": "master", "repo": []}),
        ("base", {"ref": "master", "repo": {"full_name": "owner/other"}}),
    ],
)
def test_unmerged_or_different_pr_identity_is_refused(setup, key, value):
    arm, registration, records, _ = setup
    records["pulls/55"][key] = copy.deepcopy(value)
    assert not MergedRunVerifier()(arm, registration)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("id", True),
        ("id", 99),
        ("event", "pull_request"),
        ("head_branch", "feature"),
        ("head_sha", "f" * 40),
        ("path", ".github/workflows/other.yml"),
        ("repository", []),
        ("repository", {"full_name": "owner/other"}),
        ("head_repository", []),
        ("head_repository", {"full_name": "fork/repo"}),
    ],
)
def test_arbitrary_pr_fork_or_nongating_run_is_refused(setup, key, value):
    arm, registration, records, _ = setup
    records["actions/runs/91"][key] = copy.deepcopy(value)
    assert not MergedRunVerifier()(arm, registration)


@pytest.mark.parametrize(
    "error", [OSError("forge unavailable"), subprocess.TimeoutExpired("gh", 10), []]
)
def test_forge_dependency_failure_or_unreadable_record_cannot_bind(setup, error):
    arm, registration, records, _ = setup
    records["actions/runs/91"] = error
    assert not MergedRunVerifier()(arm, registration)


@pytest.mark.parametrize(
    "result",
    [
        subprocess.CompletedProcess([], 1, "", "refused"),
        subprocess.CompletedProcess([], 0, "not-json", ""),
    ],
)
def test_failed_api_or_bad_json_cannot_bind(setup, monkeypatch, result):
    arm, registration, _, _ = setup
    monkeypatch.setattr(subprocess, "run", lambda *_args, **_kwargs: result)
    assert not MergedRunVerifier()(arm, registration)
