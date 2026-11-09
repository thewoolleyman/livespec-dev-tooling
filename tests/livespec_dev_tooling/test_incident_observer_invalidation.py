"""Mode invalidation revokes an exact unbound arm without losing owed recovery."""

from __future__ import annotations

import hashlib
import hmac
import io
import json
import subprocess
from dataclasses import replace
from threading import Barrier, Event, Thread
from types import SimpleNamespace

import pytest

from livespec_dev_tooling._incident_observer_store import (
    load_record,
    repository_lock,
)
from livespec_dev_tooling._incident_observer_types import ObserverArm, ObserverArmQuery
from livespec_dev_tooling.incident_observer_admission import (
    arm_before_merge,
    observer_arm_admitted,
)
from livespec_dev_tooling.incident_observer_service import ControllerService

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-47ij37


@pytest.fixture
def provisioned(tmp_path, monkeypatch):
    attempt = {
        "repository": "owner/repo",
        "item_id": "incident-1",
        "attempt_id": "repair-1",
        "phase": "repair",
        "operation_id": "repair-operation",
        "generation": 1,
        "owner": "controller",
        "base": "e" * 40,
        "head": "c" * 40,
        "pr_number": 55,
        "landed_commits": [],
    }
    arm = ObserverArm(
        repository=attempt["repository"],
        incident_item_id=attempt["item_id"],
        attempt_id=attempt["attempt_id"],
        phase=attempt["phase"],
        operation_id=attempt["operation_id"],
        generation=1,
        owner=attempt["owner"],
        base_sha=attempt["base"],
        head_sha=attempt["head"],
        pr_number=55,
        required_jobs=("coverage",),
        controller_release="v1.170.0",
        controller_revision="b" * 40,
        authority_receipt=json.dumps(attempt, sort_keys=True, separators=(",", ":")).encode(),
    )
    settings = SimpleNamespace(
        repository=arm.repository,
        repo=tmp_path / "reference",
        state=tmp_path / "protected",
        reader=("/installed/reader",),
        reader_release="v0.283.0",
        control_secret=b"control" * 8,
        query_secret=b"query" * 8,
        webhook_secret=b"webhook" * 8,
    )
    ready = _arm(settings=settings, arm=arm)
    query = dict(
        repository=arm.repository,
        arm_id=ready.receipt,
        pr_number=55,
        base_sha=arm.base_sha,
        head_sha=arm.head_sha,
        receipt_digest=hashlib.sha256(arm.authority_receipt).hexdigest(),
    )
    payload = query | dict(
        incident_item_id=arm.incident_item_id,
        attempt_id=arm.attempt_id,
        generation=arm.generation,
        owner=arm.owner,
        phase=arm.phase,
        incident_operation_id=arm.operation_id,
        operation_id="mode-change-1",
    )
    calls, effects = [], []

    def reader(argv, **_kwargs):
        calls.append(argv)
        return _reply(argv=argv, attempt=attempt)

    monkeypatch.setattr(subprocess, "run", reader)
    monkeypatch.setattr(
        "livespec_dev_tooling.incident_observer_control.MergedRunVerifier.__call__",
        lambda *_: True,
    )
    application = ControllerService(
        installation=settings, recover=lambda intent: effects.append(intent.action_id) or "effect-1"
    )
    return application, arm, query, payload, attempt, calls, effects


def _arm(*, settings, arm, expected=None):
    return arm_before_merge(
        directory=settings.state,
        arm=arm,
        expected_arm_id=expected,
        authorize_current=lambda _: True,
        released_controller=lambda *_: True,
    )


def _reply(*, argv, attempt):
    return subprocess.CompletedProcess(
        argv,
        0,
        json.dumps(
            {
                "schema": 1,
                "status": "verified",
                "authorizes_current_effects": True,
                "normal_factory_proof": False,
                "result": {"is_current": True, "attempt": attempt},
            }
        ),
        "",
    )


def _request(*, application, path, payload, secret=None):
    body = json.dumps(payload).encode()
    secret = application.installation.control_secret if secret is None else secret
    environ = dict(
        PATH_INFO=path,
        REQUEST_METHOD="POST",
        CONTENT_LENGTH=str(len(body)),
        HTTP_AUTHORIZATION="Bearer " + secret.decode(),
    )
    environ["wsgi.input"] = io.BytesIO(body)
    responses = []
    result = b"".join(
        application(environ, lambda status, headers: responses.append((status, headers)))
    )
    return responses[0], json.loads(result)


def _invalidate(*, application, payload, **options):
    return _request(application=application, path="/invalidate-ci", payload=payload, **options)


def _record(*, application):
    with repository_lock(
        directory=application.installation.state, repository=application.installation.repository
    ) as path:
        return load_record(path=path)


def test_invalidation_survives_restart_and_refuses_every_old_admission(provisioned):
    application, arm, query, payload, _, calls, effects = provisioned
    before = _record(application=application)
    response, result = _invalidate(application=application, payload=payload)
    assert response[0] == "202 Accepted" and result["status"] == "invalidated"
    assert ("Cache-Control", "no-store") in response[1]
    assert result["schema"] == 1 and result["authorizes_current_effects"] is False
    assert len(result["receipt"]) == 64 and len(calls) == 1
    application = ControllerService(
        installation=application.installation, recover=application.recover
    )
    after = _record(application=application)
    assert after["observer_arm"] == before["observer_arm"]
    assert _invalidate(application=application, payload=payload)[1] == result
    assert _record(application=application) == after and len(calls) == 1
    for path in ("/current", "/admitted"):
        assert (
            _request(
                application=application,
                path=path,
                payload=query,
                secret=application.installation.query_secret,
            )[1]["status"]
            == "refused"
        )
    assert not observer_arm_admitted(
        directory=application.installation.state, query=ObserverArmQuery(**query)
    )
    assert _arm(settings=application.installation, arm=arm).status == "refused"
    assert (
        _arm(
            settings=application.installation,
            arm=replace(arm, required_jobs=("different",)),
            expected=query["arm_id"],
        ).status
        == "refused"
    )
    assert (
        _request(
            application=application,
            path="/bind",
            payload=dict(repository=arm.repository, head_sha="a" * 40, run_id=91),
        )[1]["status"]
        == "admitted"
    )
    assert _record(application=application)["registration"] is not None
    assert _callback(application=application)["status"] == "completed"
    assert len(effects) == 1


@pytest.mark.parametrize(
    "change",
    [
        {"arm_id": "f" * 64},
        {"head_sha": "f" * 40},
        {"base_sha": "f" * 40},
        {"pr_number": 56},
        {"pr_number": True},
        {"receipt_digest": "f" * 64},
        {"incident_item_id": "other"},
        {"attempt_id": "other"},
        {"generation": 2},
        {"generation": True},
        {"owner": "other"},
        {"phase": "closed"},
        {"incident_operation_id": "other"},
        {"operation_id": ""},
        {"extra": "ignored"},
    ],
)
def test_invalidation_refuses_wrong_or_malformed_exact_scope(provisioned, change):
    application, _, _, payload, _, _, _ = provisioned
    before = _record(application=application)
    assert _invalidate(application=application, payload=payload | change)[1]["status"] == "refused"
    assert _record(application=application) == before


def test_query_credential_cannot_revoke_an_arm(provisioned):
    application, _, _, payload, _, calls, _ = provisioned
    before = _record(application=application)
    assert (
        _invalidate(
            application=application, payload=payload, secret=application.installation.query_secret
        )[0][0]
        == "403 Forbidden"
    )
    assert _record(application=application) == before and calls == []


def test_stale_canonical_authority_cannot_invalidate(provisioned):
    application, _, _, payload, attempt, calls, _ = provisioned
    attempt["generation"] = 2
    before = _record(application=application)
    assert _invalidate(application=application, payload=payload)[1]["status"] == "refused"
    assert _record(application=application) == before and len(calls) == 1


def test_operation_conflict_and_old_retry_never_revoke_new_arm(provisioned):
    application, arm, query, payload, _, calls, _ = provisioned
    original = _invalidate(application=application, payload=payload)[1]
    assert original["status"] == "invalidated"
    assert (
        _invalidate(application=application, payload=payload | {"owner": "changed"})[1]["status"]
        == "refused"
    )
    newer = replace(
        arm,
        generation=2,
        attempt_id="repair-2",
        head_sha="d" * 40,
        authority_receipt=b"new canonical receipt",
    )
    ready = _arm(settings=application.installation, arm=newer, expected=query["arm_id"])
    assert ready.status == "armed"
    before = _record(application=application)
    assert _invalidate(application=application, payload=payload)[1] == original
    assert _record(application=application) == before and len(calls) == 1
    assert (
        _invalidate(application=application, payload=payload | {"operation_id": "new-old-op"})[1][
            "status"
        ]
        == "refused"
    )
    assert observer_arm_admitted(
        directory=application.installation.state,
        query=ObserverArmQuery(
            **(
                query
                | dict(
                    arm_id=ready.receipt,
                    head_sha=newer.head_sha,
                    receipt_digest=hashlib.sha256(newer.authority_receipt).hexdigest(),
                )
            )
        ),
    )


def _callback(*, application):
    body = json.dumps(
        dict(
            action="completed",
            repository=dict(full_name="owner/repo"),
            workflow_job=dict(
                id=9,
                run_id=91,
                head_sha="a" * 40,
                head_branch="master",
                name="coverage",
                conclusion="failure",
                status="completed",
            ),
        )
    ).encode()
    environ = dict(
        PATH_INFO="/callback",
        REQUEST_METHOD="POST",
        CONTENT_LENGTH=str(len(body)),
        HTTP_X_GITHUB_EVENT="workflow_job",
        HTTP_X_GITHUB_DELIVERY="delivery-1",
        HTTP_X_HUB_SIGNATURE_256="sha256="
        + hmac.new(application.installation.webhook_secret, body, hashlib.sha256).hexdigest(),
    )
    environ["wsgi.input"] = io.BytesIO(body)
    result = b"".join(application(environ, lambda *_: None))
    return json.loads(result)


def test_bound_arm_cannot_be_revoked_and_retains_recovery_after_restart(provisioned):
    application, arm, _, payload, _, calls, effects = provisioned
    assert (
        _request(
            application=application,
            path="/bind",
            payload=dict(repository=arm.repository, head_sha="a" * 40, run_id=91),
        )[1]["status"]
        == "admitted"
    )
    before = _record(application=application)
    assert _invalidate(application=application, payload=payload)[1]["status"] == "refused"
    assert _record(application=application) == before and calls == []
    application = ControllerService(
        installation=application.installation, recover=application.recover
    )
    assert _callback(application=application)["status"] == "completed" and len(effects) == 1
    assert _callback(application=application)["status"] == "completed" and len(effects) == 1


def test_blocked_invalidation_reader_does_not_delay_bind_or_recovery(provisioned, monkeypatch):
    application, arm, _, payload, attempt, _, effects = provisioned
    entered, release = Event(), Event()

    def reader(argv, **_kwargs):
        entered.set()
        assert release.wait(3)
        return _reply(argv=argv, attempt=attempt)

    monkeypatch.setattr(subprocess, "run", reader)
    replies = []
    worker = Thread(
        target=lambda: replies.append(_invalidate(application=application, payload=payload))
    )
    worker.start()
    assert entered.wait(3)
    try:
        assert (
            _request(
                application=application,
                path="/bind",
                payload=dict(repository=arm.repository, head_sha="a" * 40, run_id=91),
            )[1]["status"]
            == "admitted"
        )
        assert _callback(application=application)["status"] == "completed" and len(effects) == 1
    finally:
        release.set()
        worker.join(3)
    assert not worker.is_alive() and replies[0][1]["status"] == "refused"


def test_competing_invalidations_have_one_winner(provisioned, monkeypatch):
    application, _, _, payload, attempt, _, _ = provisioned
    barrier = Barrier(2)

    def reader(argv, **_kwargs):
        barrier.wait(timeout=3)
        return _reply(argv=argv, attempt=attempt)

    monkeypatch.setattr(subprocess, "run", reader)
    replies = []
    workers = [
        Thread(
            target=lambda operation=operation: replies.append(
                _invalidate(application=application, payload=payload | dict(operation_id=operation))
            )
        )
        for operation in ("mode-change-1", "mode-change-2")
    ]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(3)
        assert not worker.is_alive()
    assert sorted(reply[1]["status"] for reply in replies) == ["invalidated", "refused"]
