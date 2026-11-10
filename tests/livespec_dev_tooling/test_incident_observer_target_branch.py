"""The observer binds, watches and recovers only its installation's configured target branch.

livespec-dev-tooling-thhgeg made the recovery principal's target branch
configurable. The observer must follow the same configuration, or no authorized
scratch-branch action can exist: `/bind` authenticates the merged pull request and
its push run on the configured branch and records that branch in the
registration, a leaf callback for any other branch never acts, `/recover`
refuses a registration retained for another branch, and the principal names the
configured branch when its head is unavailable. None of them falls back to
master, and an installation that names no branch behaves exactly as master.
"""

from __future__ import annotations

import copy
import hashlib
import hmac
import io
import json
import subprocess
from dataclasses import replace

import pytest

from livespec_dev_tooling import incident_observer_control as control
from livespec_dev_tooling import incident_observer_service as service
from livespec_dev_tooling._incident_observer_store import (
    load_record,
    read_registration,
    repository_lock,
)
from livespec_dev_tooling.incident_controller_installation import ControllerInstallation
from tests.livespec_dev_tooling.test_incident_recovery_principal import REPOSITORY, build_world

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-thhgeg

SCRATCH = "drill/recovery-scratch"
_MERGE = "a" * 40
_RUN = 91


def _installation(*, tmp_path, **changes):
    return ControllerInstallation(
        repository="owner/repo",
        repo=tmp_path / "repo",
        state=tmp_path / "state",
        reader=("/installed/reader",),
        reader_release="v0.282.0",
        principal=("/installed/principal",),
        release="v1.169.0",
        revision="b" * 40,
        jobs=("coverage",),
        webhook_secret=b"webhook" * 8,
        control_secret=b"control" * 8,
        query_secret=b"query" * 8,
        port=8765,
        config=tmp_path / "controller.json",
        **changes,
    )


def _forge_records(*, branch):
    return {
        "pulls/55": {
            "number": 55,
            "merged": True,
            "state": "closed",
            "merge_commit_sha": _MERGE,
            "head": {"sha": "c" * 40},
            "base": {"ref": branch, "repo": {"full_name": "owner/repo"}},
        },
        f"actions/runs/{_RUN}": {
            "id": _RUN,
            "event": "push",
            "head_branch": branch,
            "head_sha": _MERGE,
            "path": ".github/workflows/ci.yml",
            "repository": {"full_name": "owner/repo"},
            "head_repository": {"full_name": "owner/repo"},
            "status": "in_progress",
        },
    }


class _World:
    """One observer service over a fake forge, canonical reader and recovery callback."""

    def __init__(self, *, tmp_path, monkeypatch, **changes):
        self.installation = _installation(tmp_path=tmp_path, **changes)
        self.forge_branch = self.installation.target_branch
        self.reads, self.reader_calls, self.effects = [], [], []
        attempt = {
            "repository": "owner/repo",
            "item_id": "incident-1",
            "attempt_id": "repair-1",
            "phase": "repair",
            "operation_id": "operation-1",
            "generation": 1,
            "owner": "owner",
            "base": "e" * 40,
            "head": "c" * 40,
            "pr_number": 55,
            "landed_commits": [],
        }
        self.arm = {
            "repository": "owner/repo",
            "incident_item_id": "incident-1",
            "attempt_id": "repair-1",
            "phase": "repair",
            "operation_id": "operation-1",
            "generation": 1,
            "owner": "owner",
            "base_sha": "e" * 40,
            "head_sha": "c" * 40,
            "pr_number": 55,
            "authority_receipt": json.dumps(attempt, sort_keys=True, separators=(",", ":"))
            .encode()
            .hex(),
        }
        reply = {
            "schema": 1,
            "status": "verified",
            "authorizes_current_effects": True,
            "normal_factory_proof": False,
            "result": {"is_current": True, "attempt": attempt},
        }

        def reader(argv, **_kwargs):
            self.reader_calls.append(argv)
            return subprocess.CompletedProcess(argv, 0, json.dumps(reply), "")

        def forge(path):
            self.reads.append(path)
            records = _forge_records(branch=self.forge_branch)
            return copy.deepcopy(records.get(path.removeprefix("repos/owner/repo/")))

        monkeypatch.setattr(subprocess, "run", reader)
        monkeypatch.setattr(control.ForgeReads, "installed", lambda **_: forge)

    @property
    def application(self):
        return service.ControllerService(
            installation=self.installation,
            recover=lambda intent: self.effects.append(intent) or "exact-effect",
        )

    def post(self, *, path, payload, **headers):
        body = json.dumps(payload).encode()
        secret = self.installation.control_secret.decode()
        environ = {
            "PATH_INFO": path,
            "REQUEST_METHOD": "POST",
            "CONTENT_LENGTH": str(len(body)),
            "wsgi.input": io.BytesIO(body),
            "HTTP_AUTHORIZATION": f"Bearer {secret}",
            **headers,
        }
        statuses = []
        data = b"".join(self.application(environ, lambda status, _: statuses.append(status)))
        return statuses[0], json.loads(data)

    def bind(self):
        assert self.post(path="/arm", payload=self.arm)[1]["status"] == "armed"
        return self.post(
            path="/bind",
            payload={"repository": "owner/repo", "head_sha": _MERGE, "run_id": _RUN},
        )

    def leaf(self, *, branch, delivery="delivery-1"):
        event = {
            "action": "completed",
            "repository": {"full_name": "owner/repo"},
            "workflow_job": {
                "id": 12,
                "run_id": _RUN,
                "head_sha": _MERGE,
                "head_branch": branch,
                "name": "coverage",
                "status": "completed",
                "conclusion": "failure",
            },
        }
        body = json.dumps(event).encode()
        signature = hmac.new(self.installation.webhook_secret, body, hashlib.sha256).hexdigest()
        return self.post(
            path="/callback",
            payload=event,
            HTTP_X_HUB_SIGNATURE_256=f"sha256={signature}",
            HTTP_X_GITHUB_EVENT="workflow_job",
            HTTP_X_GITHUB_DELIVERY=delivery,
        )

    def recover(self):
        return self.post(
            path="/recover",
            payload={
                "repository": "owner/repo",
                "incident_item_id": "incident-1",
                "attempt_id": "recovery-1",
                "phase": "reverting",
                "operation_id": "recovery-1#reverting",
                "generation": 2,
                "owner": "owner",
                "authority_receipt": b"reopened".hex(),
            },
        )

    def registration(self):
        with repository_lock(
            directory=self.installation.state, repository=self.installation.repository
        ) as path:
            return read_registration(record=load_record(path=path))


@pytest.fixture
def scratch(tmp_path, monkeypatch):
    return _World(tmp_path=tmp_path, monkeypatch=monkeypatch, target_branch=SCRATCH)


@pytest.fixture
def default(tmp_path, monkeypatch):
    return _World(tmp_path=tmp_path, monkeypatch=monkeypatch)


def test_scratch_observer_binds_its_branch_run_and_records_that_branch(scratch):
    status, result = scratch.bind()
    assert (status, result["status"]) == ("202 Accepted", "admitted"), result
    assert scratch.registration().branch == SCRATCH
    assert scratch.reads == ["repos/owner/repo/pulls/55", f"repos/owner/repo/actions/runs/{_RUN}"]


def test_scratch_observer_refuses_to_bind_a_master_merge_and_run(scratch):
    scratch.forge_branch = "master"
    status, result = scratch.bind()
    assert (status, result["status"]) == ("403 Forbidden", "refused"), result
    assert scratch.registration() is None


def test_scratch_observer_refuses_a_malformed_bind_by_naming_its_branch(scratch):
    assert scratch.post(path="/arm", payload=scratch.arm)[1]["status"] == "armed"
    status, result = scratch.post(
        path="/bind", payload={"repository": "owner/repo", "head_sha": _MERGE, "run_id": 0}
    )
    assert status == "403 Forbidden"
    assert result["reason"] == f"retained arm and exact {SCRATCH} run required"


def test_scratch_observer_acts_once_on_its_branch_leaf_and_ignores_master(scratch):
    assert scratch.bind()[1]["status"] == "admitted"
    status, result = scratch.leaf(branch="master")
    assert (status, result["status"]) == ("202 Accepted", "ignored"), result
    assert result["reason"] == "job is outside the configured target branch"
    assert scratch.effects == []
    for _ in range(2):
        status, result = scratch.leaf(branch=SCRATCH)
        assert (status, result["status"]) == ("202 Accepted", "completed"), result
    assert [intent.registration.branch for intent in scratch.effects] == [SCRATCH]


def test_a_master_registration_retained_across_reconfiguration_never_acts(default):
    assert default.bind()[1]["status"] == "admitted"
    assert default.registration().branch == "master"
    default.installation = replace(default.installation, target_branch=SCRATCH)
    reads = len(default.reader_calls)
    status, result = default.recover()
    assert (status, result["status"]) == ("403 Forbidden", "refused"), result
    assert result["reason"] == (
        "landed incident attempt is not registered for the configured target branch"
    )
    assert default.leaf(branch="master")[1]["status"] == "ignored"
    assert len(default.reader_calls) == reads
    assert default.effects == []


def test_an_installation_naming_no_branch_binds_and_acts_on_master_as_before(default):
    assert default.installation.target_branch == "master"
    status, result = default.bind()
    assert (status, result["status"]) == ("202 Accepted", "admitted"), result
    assert default.registration().branch == "master"
    assert default.leaf(branch=SCRATCH)[1]["status"] == "ignored"
    assert default.leaf(branch="master")[1]["status"] == "completed"
    assert [intent.registration.branch for intent in default.effects] == ["master"]


def test_an_installation_naming_no_branch_refuses_a_scratch_merge(default):
    default.forge_branch = SCRATCH
    assert default.bind()[1]["status"] == "refused"
    assert default.registration() is None


def test_principal_names_its_configured_branch_when_that_head_is_unavailable(tmp_path):
    world = build_world(tmp_path=tmp_path, branch=SCRATCH)
    world.forge.ref_missing = True
    reply = world.call("head", {"repository": REPOSITORY, "branch": SCRATCH})
    assert (reply["status"], reply["reason"]) == ("refused", f"{SCRATCH} head unavailable")
