"""Fresh protected CI authentication retains one immutable non-authorizing attachment."""

from __future__ import annotations

import hashlib
import io
import json

from livespec_dev_tooling.incident_observer_service import ControllerService
from tests.livespec_dev_tooling import test_incident_ci_identity as identity_tests
from tests.livespec_dev_tooling import test_incident_ci_oidc_refusals as refusal_tests

trusted = identity_tests.trusted
correlated = identity_tests.correlated
authenticated = identity_tests.authenticated

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-si6uu7
_FALSE = ("authorizes_current_effects", "ci_admission", "authorizes_merge", "normal_factory_proof")
_SIGNED = (
    "repository",
    "repository_id",
    "repository_owner_id",
    "run_id",
    "run_attempt",
    "check_run_id",
    "job_id",
    "check_suite_id",
    "merge_sha",
    "caller_workflow_ref",
    "caller_workflow_sha",
    "reusable_workflow_ref",
    "reusable_workflow_sha",
    "arm_id",
    "pr_number",
    "base_sha",
    "head_sha",
    "receipt_digest",
)


def call(application, path, query, token):
    body = json.dumps(vars(query)).encode()
    response = []
    environ = {
        "PATH_INFO": path,
        "REQUEST_METHOD": "POST",
        "CONTENT_LENGTH": str(len(body)),
        "HTTP_AUTHORIZATION": "Bearer " + token,
        "wsgi.input": io.BytesIO(body),
    }
    raw = b"".join(
        application(environ, lambda status, headers: response.append((status, dict(headers))))
    )
    return response[0], json.loads(raw)


def test_fresh_authentication_retains_exact_attachment_across_retry_refresh_and_restart(
    authenticated, trusted
):
    application, query, token, _, _, effects = authenticated
    application.installation.release = "v1.0.0"
    application.installation.revision = "b" * 40
    (status, _), baseline = call(application, "/ci/identity", query, token)
    assert status == "202 Accepted" and baseline["status"] == "authenticated"
    path = application.installation.state / (hashlib.sha256(b"owner/repo").hexdigest() + ".json")
    before = json.loads(path.read_bytes())
    assert "ci_job_attachments" not in before

    (status, headers), attached = call(application, "/ci/attach", query, token)
    assert status == "202 Accepted" and headers["Cache-Control"] == "no-store"
    assert attached["status"] == "attached" and attached["schema"] == 1
    assert all(attached[key] is False for key in _FALSE)
    binding = attached["binding"]
    assert all(binding[key] == baseline["identity"][key] for key in _SIGNED)
    assert binding["policy_sha256"] == baseline["policy_sha256"]
    assert (binding["incident_item_id"], binding["generation"], binding["phase"]) == (
        "fixture",
        1,
        "repair",
    )
    assert (binding["controller_release"], binding["controller_revision"]) == ("v1.0.0", "b" * 40)
    assert not {"issued_at", "not_before", "expires_at", "authority_receipt"} & set(binding)

    stored = path.read_bytes()
    assert token.encode() not in stored and token.split(".")[2].encode() not in stored
    after = json.loads(stored)
    assert {key: after[key] for key in before} == before
    assert after["ci_job_attachments"]["attachments"][attached["attachment_id"]]

    assert call(application, "/ci/attach", query, token)[1] == attached
    refreshed = refusal_tests.resign(
        trusted, claims=trusted[3] | {"iat": 1700000005, "nbf": 1700000005, "exp": 1700000400}
    )
    assert refreshed != token
    restarted = ControllerService(
        installation=application.installation, recover=application.recover
    )
    assert call(restarted, "/ci/attach", query, refreshed) == ((status, headers), attached)
    assert len(json.loads(path.read_bytes())["ci_job_attachments"]["attachments"]) == 1
    assert effects == []
