"""The observer's callback ignores a non-completed job action and refuses everything else.

livespec-dev-tooling-sbxun3: the webhook is subscribed to every `workflow_job` action, so
each job also delivers `queued` and `in_progress`. Answering those 403 made the hook's
`last_response` read as an outage. A correctly signed delivery for the observer's own
repository whose action is not `completed` is answered 202 ignored and records nothing;
a bad signature, another repository, a malformed body, a missing delivery id and another
event stay 403, and a completion is still handled as before.
"""

from __future__ import annotations

import hashlib
import hmac
import io
import json
from typing import Any

import pytest

from livespec_dev_tooling import incident_observer_service as service
from tests.livespec_dev_tooling.test_incident_observer_target_branch import _installation

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-sbxun3


def _event(*, action: str, repository: str = "owner/repo") -> dict[str, Any]:
    return {
        "action": action,
        "repository": {"full_name": repository},
        "workflow_job": {
            "id": 12,
            "run_id": 91,
            "head_sha": "a" * 40,
            "head_branch": "feature",
            "name": "coverage",
            "status": action,
            "conclusion": None,
        },
    }


def _callback(
    *,
    tmp_path: Any,
    body: bytes,
    signed: bool = True,
    event: str = "workflow_job",
    delivery: str = "delivery-1",
) -> tuple[str, dict[str, Any]]:
    installation = _installation(tmp_path=tmp_path)
    secret = installation.webhook_secret if signed else b"not-the-secret"
    digest = hmac.new(secret, body, hashlib.sha256).hexdigest()
    environ = {
        "PATH_INFO": "/callback",
        "REQUEST_METHOD": "POST",
        "CONTENT_LENGTH": str(len(body)),
        "wsgi.input": io.BytesIO(body),
        "HTTP_X_HUB_SIGNATURE_256": f"sha256={digest}",
        "HTTP_X_GITHUB_EVENT": event,
        "HTTP_X_GITHUB_DELIVERY": delivery,
    }
    statuses: list[str] = []
    application = service.ControllerService(installation=installation, recover=lambda _i: "x")
    reply = b"".join(application(environ, lambda status, _headers: statuses.append(status)))
    return statuses[0], json.loads(reply)


@pytest.mark.parametrize("action", ["queued", "in_progress", "waiting"])
def test_a_signed_own_repository_job_that_is_not_completed_is_ignored(
    tmp_path: Any, action: str
) -> None:
    body = json.dumps(_event(action=action)).encode()
    status, answer = _callback(tmp_path=tmp_path, body=body)
    facts = [
        status == "202 Accepted",
        answer["status"] == "ignored",
        action in answer["reason"],
        not (tmp_path / "state").exists(),
    ]
    assert all(facts), (status, answer)


def test_a_bad_signature_is_refused_even_for_a_non_completed_action(tmp_path: Any) -> None:
    body = json.dumps(_event(action="queued")).encode()
    status, answer = _callback(tmp_path=tmp_path, body=body, signed=False)
    assert (status, answer["status"]) == ("403 Forbidden", "refused")


def test_another_repository_is_refused_even_when_correctly_signed(tmp_path: Any) -> None:
    body = json.dumps(_event(action="queued", repository="other/repo")).encode()
    status, answer = _callback(tmp_path=tmp_path, body=body)
    assert (status, answer["status"]) == ("403 Forbidden", "refused")


@pytest.mark.parametrize("body", [b"not json", b"[]", b'{"action": 7}', b'{"repository": {}}'])
def test_a_malformed_signed_body_is_refused(tmp_path: Any, body: bytes) -> None:
    status, answer = _callback(tmp_path=tmp_path, body=body)
    assert (status, answer["status"]) == ("403 Forbidden", "refused")


def test_a_delivery_with_no_id_is_refused(tmp_path: Any) -> None:
    body = json.dumps(_event(action="queued")).encode()
    status, _answer = _callback(tmp_path=tmp_path, body=body, delivery="")
    assert status == "403 Forbidden"


def test_another_event_is_refused(tmp_path: Any) -> None:
    body = json.dumps(_event(action="queued")).encode()
    status, _answer = _callback(tmp_path=tmp_path, body=body, event="ping")
    assert status == "403 Forbidden"


def test_a_completed_job_with_missing_fields_is_still_refused(tmp_path: Any) -> None:
    broken = _event(action="completed")
    del broken["workflow_job"]["name"]
    status, answer = _callback(tmp_path=tmp_path, body=json.dumps(broken).encode())
    assert (status, answer["status"]) == ("403 Forbidden", "refused")
