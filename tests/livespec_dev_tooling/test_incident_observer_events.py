"""The early observer accepts authenticated individual job completion only."""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest

from livespec_dev_tooling.incident_observer_events import verify_leaf_completion

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-47ij37
_SECRET = b"independent-controller-fixture-secret"


def _payload():
    return {
        "action": "completed",
        "repository": {"full_name": "owner/repo"},
        "workflow_job": {
            "name": "coverage (3.12)",
            "head_sha": "a" * 40,
            "head_branch": "master",
            "conclusion": "failure",
            "run_id": 91,
            "id": 92,
            "status": "completed",
        },
    }


def _verify(*, payload, **overrides):
    body = json.dumps(payload).encode()
    args = {
        "body": body,
        "signature": "sha256=" + hmac.new(_SECRET, body, hashlib.sha256).hexdigest(),
        "secret": _SECRET,
        "event": "workflow_job",
        "delivery_id": "delivery-one",
    }
    args.update(overrides)
    return verify_leaf_completion(**args)


def test_leaf_failure_arrives_while_workflow_is_still_running():
    result = _verify(payload=_payload())
    assert result is not None
    assert (result.run_id, result.job_id, result.job_name, result.conclusion) == (
        91,
        92,
        "coverage (3.12)",
        "failure",
    )


@pytest.mark.parametrize(
    "override",
    [
        {"secret": b""},
        {"event": "workflow_run"},
        {"delivery_id": ""},
        {"signature": "sha256=forged"},
        {"signature": "non-ascii-\u00e9"},
        {"body": b"x" * 1_000_001},
    ],
)
def test_invalid_authentication_or_delivery_is_refused(override):
    assert _verify(payload=_payload(), **override) is None


@pytest.mark.parametrize(
    "change",
    [
        {"action": "queued"},
        {"workflow_job": []},
        {"repository": []},
    ],
)
def test_invalid_envelope_is_refused(change):
    payload = _payload()
    payload.update(change)
    assert _verify(payload=payload) is None


@pytest.mark.parametrize(
    "change",
    [
        {"name": ""},
        {"head_sha": None},
        {"head_branch": ""},
        {"run_id": True},
        {"run_id": -1},
        {"id": "92"},
        {"id": 0},
        {"status": "in_progress"},
        {"conclusion": None},
    ],
)
def test_invalid_job_is_refused(change):
    payload = _payload()
    payload["workflow_job"].update(change)
    assert _verify(payload=payload) is None


@pytest.mark.parametrize("raw", [b"not json", b"\xff", b"[]"])
def test_authenticated_malformed_body_is_refused(raw):
    signature = "sha256=" + hmac.new(_SECRET, raw, hashlib.sha256).hexdigest()
    assert (
        verify_leaf_completion(
            body=raw,
            signature=signature,
            event="workflow_job",
            delivery_id="one",
            secret=_SECRET,
        )
        is None
    )
