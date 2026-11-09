"""Hosted query credentials cannot mutate authority and fresh reads fence CI."""

from __future__ import annotations

import hashlib
import io
import json
import subprocess
from types import SimpleNamespace

import pytest

from livespec_dev_tooling._incident_observer_store import (
    load_record,
    repository_lock,
    save_record,
)
from livespec_dev_tooling._incident_observer_types import ObserverArm
from livespec_dev_tooling.incident_observer_admission import arm_before_merge
from livespec_dev_tooling.incident_observer_service import ControllerService

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-47ij37


@pytest.fixture
def provisioned(tmp_path, monkeypatch):
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
    arm = ObserverArm(
        repository="owner/repo",
        incident_item_id="incident-1",
        attempt_id="repair-1",
        operation_id="operation-1",
        generation=1,
        owner="owner",
        phase="repair",
        pr_number=55,
        base_sha="e" * 40,
        head_sha="c" * 40,
        required_jobs=("coverage",),
        controller_release="v1.169.0",
        controller_revision="b" * 40,
        authority_receipt=json.dumps(attempt, sort_keys=True, separators=(",", ":")).encode(),
    )
    settings = SimpleNamespace(
        repository=arm.repository,
        repo=tmp_path / "reference",
        state=tmp_path / "protected",
        reader=("/installed/reader",),
        reader_release="v0.282.0",
        control_secret=b"control" * 8,
        query_secret=b"query" * 8,
        webhook_secret=b"webhook" * 8,
    )
    receipt = arm_before_merge(
        directory=settings.state,
        arm=arm,
        expected_arm_id=None,
        authorize_current=lambda _: True,
        released_controller=lambda *_: True,
    )
    query = {
        "repository": arm.repository,
        "arm_id": receipt.receipt,
        "pr_number": arm.pr_number,
        "base_sha": arm.base_sha,
        "head_sha": arm.head_sha,
        "receipt_digest": hashlib.sha256(arm.authority_receipt).hexdigest(),
    }
    reader_calls = []

    def reader(argv, **_kwargs):
        reader_calls.append(argv)
        reply = {
            "schema": 1,
            "status": "verified",
            "authorizes_current_effects": True,
            "result": {"is_current": True, "attempt": attempt},
        }
        return subprocess.CompletedProcess(argv, 0, json.dumps(reply), "")

    monkeypatch.setattr(subprocess, "run", reader)
    return (
        ControllerService(installation=settings, recover=lambda _: None),
        query,
        attempt,
        reader_calls,
    )


def _request(*, application, path, payload, secret=None):
    body = json.dumps(payload).encode()
    secret = application.installation.query_secret if secret is None else secret
    environ = {
        "PATH_INFO": path,
        "REQUEST_METHOD": "POST",
        "CONTENT_LENGTH": str(len(body)),
        "wsgi.input": io.BytesIO(body),
        "HTTP_AUTHORIZATION": "Bearer " + secret.decode(),
    }
    responses = []
    result = b"".join(
        application(environ, lambda status, headers: responses.append((status, headers)))
    )
    return responses[0], json.loads(result)


def test_hosted_current_query_uses_fresh_reader_and_exact_echo(provisioned):
    application, query, _, calls = provisioned
    response, result = _request(application=application, path="/current", payload=query)
    assert response[0] == "202 Accepted"
    assert ("Cache-Control", "no-store") in response[1]
    assert result == {"schema": 1, "status": "current", "query": query}
    assert len(calls) == 1
    assert calls[0][:2] == ["/installed/reader", "read-current"]
    assert _request(application=application, path="/admitted", payload=query)[1] == {
        "schema": 1,
        "status": "admitted",
        "query": query,
    }
    assert len(calls) == 1


def test_an_unbound_premerge_arm_owns_the_matching_ordinary_reconciler_action(provisioned):
    """The ordinary reconciler must leave a pre-merge observer arm alone."""
    application, _, _, _ = provisioned
    query = {"repository": "owner/repo", "head_sha": "e" * 40, "run_id": 1}

    response, result = _request(application=application, path="/ordinary-action", payload=query)

    assert response[0] == "202 Accepted"
    assert result == {
        "schema": 1,
        "status": "incident-owned",
        "reason": "pre-merge observer owns repository action",
        "query": query,
    }


def test_an_unregistered_ordinary_action_keeps_its_policy_under_the_shared_lock(
    provisioned, tmp_path
):
    """A repository with no incident record answers `ordinary` for any run."""
    application, _, _, _ = provisioned
    settings = SimpleNamespace(**(vars(application.installation) | {"state": tmp_path / "empty"}))
    quiet = ControllerService(installation=settings, recover=lambda _: None)
    query = {"repository": "owner/repo", "head_sha": "e" * 40, "run_id": 1}

    response, result = _request(application=quiet, path="/ordinary-action", payload=query)

    assert response[0] == "202 Accepted"
    assert result == {
        "schema": 1,
        "status": "ordinary",
        "reason": "ordinary reconciler policy retained",
        "query": query,
    }


@pytest.mark.parametrize(
    "query",
    [
        {"repository": "owner/repo", "head_sha": "e" * 40, "run_id": 0},
        {"repository": "owner/repo", "head_sha": "e" * 40, "run_id": True},
        {"repository": "owner/repo", "head_sha": 7, "run_id": 1},
        {"repository": "owner/repo", "head_sha": "e" * 40, "run_id": 1, "extra": "x"},
    ],
)
def test_a_malformed_ordinary_action_query_is_refused(provisioned, query):
    """Ownership queries name one exact positive workflow run."""
    application, _, _, _ = provisioned

    response, result = _request(application=application, path="/ordinary-action", payload=query)

    assert response[0] == "403 Forbidden"
    assert result == {
        "schema": 1,
        "status": "refused",
        "reason": "invalid ordinary action ownership query",
    }


@pytest.mark.parametrize("path", ["/arm", "/bind"])
def test_query_credential_cannot_mutate_retained_arm(provisioned, path):
    application, query, _, calls = provisioned
    with repository_lock(
        directory=application.installation.state, repository=query["repository"]
    ) as record_path:
        before = record_path.read_bytes()
    assert _request(application=application, path=path, payload=query)[0][0] == "403 Forbidden"
    with repository_lock(
        directory=application.installation.state, repository=query["repository"]
    ) as record_path:
        assert record_path.read_bytes() == before
    assert calls == []


@pytest.mark.parametrize("path", ["/current", "/admitted"])
def test_control_credential_is_not_a_hosted_query_credential(provisioned, path):
    application, query, _, calls = provisioned
    assert (
        _request(
            application=application,
            path=path,
            payload=query,
            secret=application.installation.control_secret,
        )[0][0]
        == "403 Forbidden"
    )
    assert calls == []


@pytest.mark.parametrize(
    "change",
    [
        {"pr_number": True},
        {"pr_number": 0},
        {"repository": "other/repo"},
        {"arm_id": "f" * 64},
        {"receipt_digest": "f" * 64},
        {"head_sha": "f" * 40},
        {"base_sha": "f" * 40},
        {"arm_id": 1},
        {"head_sha": "short"},
        {"arm_id": "short"},
        {"extra": "ignored"},
    ],
)
def test_malformed_or_wrong_exact_query_cannot_authorize(provisioned, change):
    application, query, _, calls = provisioned
    assert (
        _request(application=application, path="/current", payload=query | change)[1]["status"]
        == "refused"
    )
    assert calls == []


def test_retained_arm_does_not_make_stale_canonical_generation_current(provisioned):
    application, query, attempt, calls = provisioned
    attempt["generation"] = 2
    assert (
        _request(application=application, path="/admitted", payload=query)[1]["status"]
        == "admitted"
    )
    assert (
        _request(application=application, path="/current", payload=query)[1]["status"] == "refused"
    )
    assert len(calls) == 1


@pytest.mark.parametrize("change", ["bind", "missing", "identity"])
def test_arm_change_during_tenant_read_refuses_without_holding_effect_lock(
    provisioned, monkeypatch, change
):
    application, query, attempt, _ = provisioned

    def reader(argv, **_kwargs):
        # A separate open of the same flock would deadlock if /current kept it
        # held during the canonical process. This callback models a concurrent
        # bind/correction, not a request-created lifecycle transition.
        with repository_lock(
            directory=application.installation.state, repository=query["repository"]
        ) as record_path:
            record = load_record(path=record_path)
            if change == "bind":
                record["observer_arm_bound"] = True
            elif change == "missing":
                record.pop("observer_arm")
            else:
                assert change == "identity"
                record["observer_arm_id"] = "f" * 64
            save_record(path=record_path, record=record)
        reply = {
            "schema": 1,
            "status": "verified",
            "authorizes_current_effects": True,
            "result": {"is_current": True, "attempt": attempt},
        }
        return subprocess.CompletedProcess(argv, 0, json.dumps(reply), "")

    monkeypatch.setattr(subprocess, "run", reader)
    assert (
        _request(application=application, path="/current", payload=query)[1]["status"] == "refused"
    )


@pytest.mark.parametrize("change", ["bind", "missing"])
def test_initial_missing_or_bound_arm_refuses_before_reader(provisioned, change):
    application, query, _, calls = provisioned
    with repository_lock(
        directory=application.installation.state, repository=query["repository"]
    ) as record_path:
        record = load_record(path=record_path)
        if change == "bind":
            record["observer_arm_bound"] = True
        else:
            assert change == "missing"
            record.pop("observer_arm")
        save_record(path=record_path, record=record)
    assert (
        _request(application=application, path="/current", payload=query)[1]["status"] == "refused"
    )
    assert calls == []


@pytest.mark.parametrize("change", ["path", "repository"])
def test_public_query_adapter_refuses_unknown_operation_and_foreign_scope(provisioned, change):
    from livespec_dev_tooling.incident_observer_query import ObserverQuery

    application, query, _, calls = provisioned
    path = "/unknown" if change == "path" else "/current"
    if change == "repository":
        query["repository"] = "foreign/repo"
    assert (
        ObserverQuery(installation=application.installation).execute(path=path, payload=query)[
            "status"
        ]
        == "refused"
    )
    assert calls == []


def test_unavailable_canonical_reader_refuses_without_mutation(provisioned, monkeypatch):
    application, query, _, _ = provisioned
    monkeypatch.setattr(
        subprocess, "run", lambda argv, **_: subprocess.CompletedProcess(argv, 1, "", "outage")
    )
    assert (
        _request(application=application, path="/current", payload=query)[1]["status"] == "refused"
    )
