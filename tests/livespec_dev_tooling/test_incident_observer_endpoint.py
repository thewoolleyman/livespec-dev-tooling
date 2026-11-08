"""The hosted endpoint has no request-driven authority or registration path."""

from __future__ import annotations

import hashlib
import hmac
import io
import json
from threading import Event, Thread

import pytest

from livespec_dev_tooling._incident_observer_types import ObserverRegistration
from livespec_dev_tooling.incident_observer import admit_observer
from livespec_dev_tooling.incident_observer_endpoint import observer_endpoint

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-47ij37


def _request(*, directory, **changes):
    environ = {"REQUEST_METHOD": "POST", "CONTENT_LENGTH": "2", "wsgi.input": io.BytesIO(b"{}")}
    environ.update(changes)
    responses = []

    def respond(status, headers):
        responses.append((status, headers))

    application = observer_endpoint(
        directory=directory,
        webhook_secret=b"host-configured",
        recover=lambda _: pytest.fail("untrusted HTTP effect"),
    )
    body = b"".join(application(environ, respond))
    return responses[0][0], json.loads(body)


def _registered_leaf_request(*, directory):
    registration = ObserverRegistration(
        repository="owner/repo",
        incident_item_id="incident-1",
        attempt_id="repair-1",
        operation_id="operation-1",
        generation=1,
        owner="recovery-controller",
        phase="repair",
        head_sha="a" * 40,
        run_id=91,
        required_jobs=("lint",),
        controller_release="v1.2.3",
        controller_revision="b" * 40,
        candidate_revision="c" * 40,
        authority_receipt=b"canonical-verified-receipt-1",
    )
    assert (
        admit_observer(
            directory=directory,
            registration=registration,
            expected_generation=None,
            authorize_current=lambda value: value == registration,
            released_controller=lambda tag, revision: tag == "v1.2.3" and revision == "b" * 40,
        ).status
        == "admitted"
    )
    raw = json.dumps(
        {
            "action": "completed",
            "repository": {"full_name": registration.repository},
            "workflow_job": {
                "id": 92,
                "run_id": registration.run_id,
                "name": "lint",
                "head_sha": registration.head_sha,
                "head_branch": registration.branch,
                "status": "completed",
                "conclusion": "failure",
            },
        }
    ).encode()
    return registration, raw


def _callback_environ(*, raw):
    return {
        "REQUEST_METHOD": "POST",
        "CONTENT_LENGTH": str(len(raw)),
        "wsgi.input": io.BytesIO(raw),
        "HTTP_X_GITHUB_EVENT": "workflow_job",
        "HTTP_X_GITHUB_DELIVERY": "delivery-one",
        "HTTP_X_HUB_SIGNATURE_256": "sha256="
        + hmac.new(b"host-configured", raw, hashlib.sha256).hexdigest(),
    }


def _deliver_pending_callback(*, directory, raw, effects):
    recovery_started, recovery_done, allow_recovery, response_started, request_done = (
        Event(),
        Event(),
        Event(),
        Event(),
        Event(),
    )
    responses: list[str] = []

    def recover(intent):
        recovery_started.set()
        assert allow_recovery.wait(timeout=2)
        effects.append(intent.action_id)
        recovery_done.set()
        return "revert-sha"

    application = observer_endpoint(
        directory=directory,
        webhook_secret=b"host-configured",
        recover=recover,
    )

    def respond(status, headers):
        del headers
        responses.append(status)
        response_started.set()

    def deliver():
        body = b"".join(application(_callback_environ(raw=raw), respond))
        assert json.loads(body)["status"] == "pending"
        request_done.set()

    request = Thread(target=deliver)
    request.start()
    return (
        recovery_started,
        recovery_done,
        allow_recovery,
        response_started,
        request_done,
        responses,
        request,
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"REQUEST_METHOD": "GET"},
        {"CONTENT_LENGTH": ""},
        {"CONTENT_LENGTH": "-1"},
        {"CONTENT_LENGTH": "1_000"},
        {"CONTENT_LENGTH": "1000001"},
        {"CONTENT_LENGTH": "\u0661"},
        {"wsgi.input": None},
        {"CONTENT_LENGTH": "3"},
        {"wsgi.input": io.StringIO("{}")},
    ],
)
def test_invalid_http_input_never_opens_controller_store(tmp_path, changes):
    status, result = _request(directory=tmp_path / "absent", **changes)
    assert status == "400 Bad Request"
    assert result["status"] == "refused"
    assert not (tmp_path / "absent").exists()


def test_absent_webhook_auth_cannot_register_or_execute_from_request(tmp_path):
    status, result = _request(directory=tmp_path / "absent")
    assert status == "403 Forbidden"
    assert result["status"] == "refused"
    assert not (tmp_path / "absent").exists()


def test_valid_early_job_delivery_is_accepted_without_authorizing_an_unknown_incident(tmp_path):
    raw = json.dumps(
        {
            "action": "completed",
            "repository": {"full_name": "owner/repo"},
            "workflow_job": {
                "id": 92,
                "run_id": 91,
                "name": "lint",
                "head_sha": "a" * 40,
                "head_branch": "master",
                "status": "completed",
                "conclusion": "failure",
            },
        }
    ).encode()
    status, result = _request(
        directory=tmp_path,
        CONTENT_LENGTH=str(len(raw)),
        **{
            "wsgi.input": io.BytesIO(raw),
            "HTTP_X_GITHUB_EVENT": "workflow_job",
            "HTTP_X_GITHUB_DELIVERY": "delivery-one",
            "HTTP_X_HUB_SIGNATURE_256": "sha256="
            + hmac.new(b"host-configured", raw, hashlib.sha256).hexdigest(),
        },
    )
    assert status == "202 Accepted"
    assert result["status"] == "ignored"


def test_registered_leaf_is_acknowledged_before_its_recovery_principal_completes(tmp_path):
    _, raw = _registered_leaf_request(directory=tmp_path)
    effects: list[str] = []
    (
        recovery_started,
        recovery_done,
        allow_recovery,
        response_started,
        request_done,
        responses,
        request,
    ) = _deliver_pending_callback(
        directory=tmp_path,
        raw=raw,
        effects=effects,
    )
    try:
        assert recovery_started.wait(timeout=2)
        assert response_started.wait(timeout=0.2)
        assert request_done.wait(timeout=0.2)
        assert responses == ["202 Accepted"]
        assert effects == []
    finally:
        allow_recovery.set()
        request.join(timeout=2)
    assert recovery_done.wait(timeout=2)
    assert effects
