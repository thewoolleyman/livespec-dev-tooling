"""The hosted endpoint has no request-driven authority or registration path."""

from __future__ import annotations

import hashlib
import hmac
import io
import json

import pytest

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
