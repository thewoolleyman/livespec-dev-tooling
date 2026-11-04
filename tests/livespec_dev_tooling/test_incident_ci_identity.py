"""Controller identity is exact, nonauthorizing, and unavailable without host policy."""

from __future__ import annotations

import hashlib
import io
import json
import time
from dataclasses import replace
from types import SimpleNamespace

import pytest

from livespec_dev_tooling import incident_ci_identity as identity_module
from livespec_dev_tooling._incident_observer_types import ObserverArm
from livespec_dev_tooling.incident_ci_payload import decode_authority
from livespec_dev_tooling.incident_observer_admission import arm_before_merge
from livespec_dev_tooling.incident_observer_service import ControllerService
from tests.livespec_dev_tooling import test_incident_ci_identity_policy as policy_tests
from tests.livespec_dev_tooling import test_incident_ci_job_identity as job_tests

trusted = policy_tests.trusted

correlated = job_tests.correlated

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-rqhqnb


@pytest.fixture
def authenticated(trusted, correlated, tmp_path, monkeypatch):
    _, policy, token, *_ = trusted
    verifier, records, calls = correlated
    arm = ObserverArm(
        repository="owner/repo",
        incident_item_id="fixture",
        attempt_id="repair",
        operation_id="operation",
        generation=1,
        owner="controller",
        phase="repair",
        base_sha=verifier.query.base_sha,
        head_sha=verifier.query.head_sha,
        pr_number=55,
        required_jobs=("coverage",),
        controller_release="v1.0.0",
        controller_revision="b" * 40,
        authority_receipt=b"fixture-only-canonical-receipt",
    )
    settings = SimpleNamespace(
        repository="owner/repo",
        state=tmp_path / "state",
        ci_identity_policy=policy,
        control_secret=b"control" * 8,
        query_secret=b"query" * 8,
        webhook_secret=b"webhook" * 8,
    )
    result = arm_before_merge(
        directory=settings.state,
        arm=arm,
        expected_arm_id=None,
        authorize_current=lambda _: True,
        released_controller=lambda *_: True,
    )
    query = replace(
        verifier.query,
        arm_id=result.receipt,
        receipt_digest=hashlib.sha256(arm.authority_receipt).hexdigest(),
    )
    monkeypatch.setattr(time, "time", lambda: 1700000010)
    effects = []
    return (
        ControllerService(
            installation=settings, recover=lambda intent: effects.append(intent) or "effect"
        ),
        query,
        token,
        records,
        calls,
        effects,
    )


def request(application, query, token, *, body=None, method="POST"):
    body = json.dumps(vars(query)).encode() if body is None else body
    response = []
    environ = {
        "PATH_INFO": "/ci/identity",
        "REQUEST_METHOD": method,
        "CONTENT_LENGTH": str(len(body)),
        "HTTP_AUTHORIZATION": "Bearer " + token,
        "wsgi.input": io.BytesIO(body),
    }
    raw = b"".join(
        application(environ, lambda status, headers: response.append((status, dict(headers))))
    )
    return response[0], json.loads(raw)


def test_exact_controller_result_never_grants_incident_authority(authenticated):
    application, query, token, _, calls, effects = authenticated
    (status, headers), result = request(application, query, token)
    assert status == "202 Accepted" and headers["Cache-Control"] == "no-store"
    assert set(result) == {
        "schema",
        "status",
        "identity",
        "policy_sha256",
        "authorizes_current_effects",
        "ci_admission",
        "authorizes_merge",
        "normal_factory_proof",
    }
    assert result["status"] == "authenticated" and result["schema"] == 1
    assert all(
        result[key] is False
        for key in (
            "authorizes_current_effects",
            "ci_admission",
            "authorizes_merge",
            "normal_factory_proof",
        )
    )
    assert result["identity"] | vars(query) == result["identity"]
    assert result["identity"]["job_id"] == 1011 and result["identity"]["check_run_id"] == 913
    assert result["identity"]["merge_sha"] != query.head_sha
    assert token not in json.dumps(result) and "signature" not in json.dumps(result)
    assert decode_authority(payload=json.dumps(result)) is None
    assert calls and effects == []
    assert (
        request(application, query, application.installation.query_secret.decode())[1]["status"]
        == "refused"
    )
    assert (
        request(application, query, application.installation.control_secret.decode())[1]["status"]
        == "refused"
    )


@pytest.mark.parametrize(
    "body",
    [b"[]", b"{", b'{"repository":"owner/repo","repository":"other"}', b'{"n":NaN}', b"x" * 65537],
)
def test_strict_http_boundary_rejects_bad_body_without_forge(authenticated, body):
    application, query, token, _, calls, _ = authenticated
    assert request(application, query, token, body=body)[0][0] == "403 Forbidden"
    assert calls == []


def test_policy_absence_or_wrong_method_never_reads_body_or_forge(authenticated):
    application, query, token, _, calls, _ = authenticated
    assert request(application, query, token, method="GET")[1]["status"] == "refused"
    application.installation.ci_identity_policy = None
    assert request(application, query, token)[1]["status"] == "refused"
    assert (
        identity_module.CiIdentityVerifier(installation=application.installation).execute(
            authorization="Bearer " + token, payload=vars(query)
        )["status"]
        == "refused"
    )
    assert calls == []


@pytest.mark.parametrize(
    "change",
    [{"extra": 1}, {"pr_number": True}, {"repository": 1}, {"arm_id": "x"}, {"head_sha": "x"}],
)
def test_exact_query_refuses_before_external_reads(authenticated, change):
    application, query, token, _, calls, _ = authenticated
    result = identity_module.CiIdentityVerifier(installation=application.installation).execute(
        authorization="Bearer " + token, payload=vars(query) | change
    )
    assert result["status"] == "refused" and calls == []


def test_stale_arm_policy_and_expiry_rechecked_after_external_reads(authenticated, monkeypatch):
    application, query, token, _, _, _ = authenticated
    original = identity_module.CiJobVerifier.verify

    def changed(verifier):
        result = original(verifier)
        application.installation.ci_identity_policy.path.write_text("tampered")
        return result

    monkeypatch.setattr(identity_module.CiJobVerifier, "verify", changed)
    assert request(application, query, token)[1]["status"] == "refused"


def test_unavailable_retained_state_is_generic_refusal(authenticated, monkeypatch):
    application, query, token, _, calls, _ = authenticated

    def unavailable(**_kwargs):
        raise OSError("controlled private failure")

    monkeypatch.setattr(identity_module, "observer_arm_admitted", unavailable)
    result = request(application, query, token)[1]
    assert result["status"] == "refused" and "private" not in json.dumps(result) and calls == []


def test_existing_current_and_admitted_consumers_reject_authenticated_identity(
    authenticated, monkeypatch
):
    from livespec_dev_tooling import incident_ci_authority

    application, query, token, *_ = authenticated
    result = request(application, query, token)[1]

    class Connection:
        def request(self, *_args, **_kwargs):
            pass

        def getresponse(self):
            return SimpleNamespace(status=202, read=lambda _: json.dumps(result).encode())

        def close(self):
            pass

    monkeypatch.setattr(
        incident_ci_authority.http.client, "HTTPSConnection", lambda *_args, **_kwargs: Connection()
    )
    boundary = incident_ci_authority.CiAuthorityBoundary(
        observer_url="https://controlled.fixture",
        observer_token=application.installation.query_secret.decode(),
    )
    assert not boundary.current(query=vars(query))
    assert not boundary.admitted(query=vars(query))
