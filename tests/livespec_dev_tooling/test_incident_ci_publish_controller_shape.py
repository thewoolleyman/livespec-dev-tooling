"""The publisher sends the controller exactly the aggregate shape it verifies."""

from __future__ import annotations

import json
import re

from livespec_dev_tooling.incident_ci_publish import publish

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-uoumll

_CONTROLLER_KEYS = {
    "status",
    "head_sha",
    "scope",
    "passed",
    "failed",
    "missing",
    "deferred",
    "context_name",
}
_CONTROLLER_REASON = re.compile(r"[A-Za-z0-9:_.-]{1,128}")
_SPACED = "incident-policy:not-applicable: tdd-trailers-or-pull-request-event-admission"
_PRODUCED = {
    "attribution": [["check-format", ["check-python"]]],
    "conditional": [],
    "context_name": "ci-green",
    "deferred": [
        {"name": "check-coverage", "reason": "incident-policy:coverage"},
        {"name": "check-red-green-replay", "reason": _SPACED},
    ],
    "failed": [],
    "head_sha": "c" * 40,
    "missing": [],
    "passed": ["check-format"],
    "scope": "f" * 64,
    "status": "passed",
}
_QUERY = {
    "repository": "owner/repo",
    "arm_id": "a" * 64,
    "pr_number": 55,
    "base_sha": "b" * 40,
    "head_sha": "c" * 40,
    "receipt_digest": "d" * 64,
}


def _sent_aggregate():
    bodies = []

    def send(*, url, token, body, connect_to):
        _ = (url, token, connect_to)
        bodies.append(json.loads(body))
        return 202, b'{"status":"published","aggregate_digest":"' + b"e" * 64 + b'"}'

    publish(
        environ={"LIVESPEC_INCIDENT_OBSERVER_URL": "https://observer.example:8443/"},
        release="v1.2.3",
        aggregate=json.dumps(_PRODUCED),
        query=json.dumps(_QUERY),
        send=send,
        token_source=lambda **_: "oidc-jwt",
    )
    return bodies[0]["aggregate"]


def test_the_published_aggregate_carries_only_the_keys_the_controller_verifies():
    sent = _sent_aggregate()
    reasons = [row["reason"] for row in sent["deferred"]]
    expected = "incident-policy:not-applicable:tdd-trailers-or-pull-request-event-admission"
    assert all(
        [
            set(sent) == _CONTROLLER_KEYS,
            all(_CONTROLLER_REASON.fullmatch(reason) for reason in reasons),
            reasons[1] == expected,
        ]
    )
