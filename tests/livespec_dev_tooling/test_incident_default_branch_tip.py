"""An expedited event base must lie on the protected default branch's history."""

from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
from types import SimpleNamespace

from livespec_dev_tooling import incident_default_branch_tip as module
from livespec_dev_tooling._incident_observer_types import ObserverArm
from livespec_dev_tooling.incident_observer_admission import arm_before_merge
from livespec_dev_tooling.incident_observer_service import ControllerService

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-47ij37

_ENVIRONMENT = {
    **os.environ,
    "GIT_AUTHOR_NAME": "test",
    "GIT_AUTHOR_EMAIL": "test@example.invalid",
    "GIT_COMMITTER_NAME": "test",
    "GIT_COMMITTER_EMAIL": "test@example.invalid",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
}


def _git(*, root, args) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
        env=_ENVIRONMENT,
    ).stdout.strip()


def _commit(*, root, message: str) -> str:
    _git(root=root, args=("commit", "--quiet", "--allow-empty", "-m", message))
    return _git(root=root, args=("rev-parse", "HEAD"))


def _forge(tmp_path):
    """A forge with master, and a reference clone of it that reads master via origin."""
    origin = tmp_path / "origin.git"
    seed = tmp_path / "seed"
    _ = subprocess.run(["git", "init", "--quiet", "--initial-branch=master", str(seed)], check=True)
    genesis = _commit(root=seed, message="genesis")
    older = _commit(root=seed, message="older")
    tip = _commit(root=seed, message="tip")
    _ = subprocess.run(["git", "clone", "--quiet", "--bare", str(seed), str(origin)], check=True)
    reference = tmp_path / "reference"
    _ = subprocess.run(["git", "clone", "--quiet", str(origin), str(reference)], check=True)
    return origin, seed, reference, genesis, older, tip


def test_default_branch_tip_and_its_history_are_admitted(tmp_path):
    _, _, reference, genesis, older, tip = _forge(tmp_path)
    admitted = [
        module.default_branch_refusal(root=reference, branch="master", event_base=base)
        for base in (tip, older, genesis)
    ]
    assert admitted == [None, None, None]


def test_a_descendant_of_genesis_that_is_not_on_the_default_branch_is_refused(tmp_path):
    origin, _, reference, genesis, _, _ = _forge(tmp_path)
    _git(root=reference, args=("checkout", "--quiet", "-b", "other", genesis))
    divergent = _commit(root=reference, message="divergent")
    _git(root=reference, args=("push", "--quiet", str(origin), "other"))
    refusal = module.default_branch_refusal(root=reference, branch="master", event_base=divergent)
    assert refusal is not None
    assert divergent in refusal
    assert "master" in refusal


def test_an_unreadable_default_branch_refuses_with_a_named_failure(tmp_path):
    _, _, reference, _, _, tip = _forge(tmp_path)
    refusal = module.default_branch_refusal(root=reference, branch="absent", event_base=tip)
    assert refusal is not None
    assert "absent" in refusal


def _request(*, application, path, payload):
    body = json.dumps(payload).encode()
    environ = {
        "PATH_INFO": path,
        "REQUEST_METHOD": "POST",
        "CONTENT_LENGTH": str(len(body)),
        "wsgi.input": io.BytesIO(body),
        "HTTP_AUTHORIZATION": "Bearer " + application.installation.query_secret.decode(),
    }
    responses = []
    result = b"".join(
        application(environ, lambda status, headers: responses.append((status, headers)))
    )
    return json.loads(result)


def test_admitted_refuses_a_retargeted_event_base_off_the_default_branch(tmp_path):
    origin, _, reference, genesis, _, _ = _forge(tmp_path)
    _git(root=reference, args=("checkout", "--quiet", "-b", "other", genesis))
    divergent = _commit(root=reference, message="divergent")
    _git(root=reference, args=("push", "--quiet", str(origin), "other"))
    arm = ObserverArm(
        repository="owner/repo",
        incident_item_id="incident-1",
        attempt_id="repair-1",
        operation_id="operation-1",
        generation=1,
        owner="owner",
        phase="repair",
        pr_number=55,
        base_sha=genesis,
        head_sha="c" * 40,
        required_jobs=("coverage",),
        controller_release="v1.169.0",
        controller_revision="b" * 40,
        authority_receipt=b"receipt",
    )
    settings = SimpleNamespace(
        repository=arm.repository,
        repo=reference,
        state=tmp_path / "protected",
        reader=("/installed/reader",),
        reader_release="v0.282.0",
        control_secret=b"control" * 8,
        query_secret=b"query" * 8,
        webhook_secret=b"webhook" * 8,
        expedited_base_max_commits=5,
        expedited_base_max_minutes=10_000_000,
        target_branch="master",
    )
    armed = arm_before_merge(
        directory=settings.state,
        arm=arm,
        expected_arm_id=None,
        authorize_current=lambda _: True,
        released_controller=lambda *_: True,
    )
    application = ControllerService(installation=settings, recover=lambda _: None)
    query = {
        "repository": arm.repository,
        "arm_id": armed.receipt,
        "pr_number": arm.pr_number,
        "base_sha": arm.base_sha,
        "event_base_sha": divergent,
        "head_sha": arm.head_sha,
        "receipt_digest": hashlib.sha256(arm.authority_receipt).hexdigest(),
    }
    reply = _request(application=application, path="/admitted", payload=query)
    assert reply["status"] == "refused"
    assert divergent in reply["reason"]
