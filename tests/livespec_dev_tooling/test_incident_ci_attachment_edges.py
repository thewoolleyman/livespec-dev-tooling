"""Attachment refuses conflicts, drift and races; existing writers preserve its subtree."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import replace
from types import SimpleNamespace

import pytest

from livespec_dev_tooling import incident_ci_attachment as attachment_module
from livespec_dev_tooling import incident_ci_identity as identity_module
from livespec_dev_tooling import incident_observer_invalidation as invalidation_module
from livespec_dev_tooling._incident_ci_attachment_store import attachment_receipt
from livespec_dev_tooling._incident_observer_store import (
    load_record,
    read_observer_arm,
    repository_lock,
    save_record,
)
from livespec_dev_tooling._incident_observer_types import ObserverRegistration
from livespec_dev_tooling.incident_ci_identity_policy import load_identity_policy
from livespec_dev_tooling.incident_ci_payload import decode_authority
from livespec_dev_tooling.incident_observer_admission import arm_before_merge, bind_after_merge
from livespec_dev_tooling.incident_observer_invalidation import ObserverCiInvalidation
from tests.livespec_dev_tooling import test_incident_ci_attachment as red_tests
from tests.livespec_dev_tooling import test_incident_ci_identity as identity_tests
from tests.livespec_dev_tooling import test_incident_ci_oidc_refusals as refusal_tests

trusted = identity_tests.trusted
correlated = identity_tests.correlated
authenticated = identity_tests.authenticated
call = red_tests.call

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-si6uu7


@pytest.fixture
def attached(authenticated):
    application, query, token, records, calls, effects = authenticated
    application.installation.release = "v1.0.0"
    application.installation.revision = "b" * 40
    (status, _), receipt = call(application, "/ci/attach", query, token)
    assert status == "202 Accepted", receipt
    return SimpleNamespace(
        application=application,
        query=query,
        token=token,
        records=records,
        calls=calls,
        effects=effects,
        receipt=receipt,
    )


def mutate(application, change):
    settings = application.installation
    with repository_lock(directory=settings.state, repository=settings.repository) as path:
        record = load_record(path=path)
        change(record)
        save_record(path=path, record=record)


def stored(application):
    settings = application.installation
    with repository_lock(directory=settings.state, repository=settings.repository) as path:
        return load_record(path=path)


def attach(application, query, token):
    return call(application, "/ci/attach", query, token)[1]


def test_query_and_control_credentials_cannot_attach(attached):
    settings = attached.application.installation
    before = stored(attached.application)
    for secret in (settings.query_secret, settings.control_secret):
        result = attach(attached.application, attached.query, secret.decode())
        assert result["status"] == "refused"
    assert stored(attached.application) == before


def test_missing_policy_bad_query_and_bearer_refuse(attached):
    application, query, token = attached.application, attached.query, attached.token
    verifier = attachment_module.CiJobAttachment(installation=application.installation)
    assert verifier.execute(authorization=token, payload=vars(query))["status"] == "refused"
    for payload in (vars(query) | {"extra": 1}, vars(query) | {"repository": "other/repo"}):
        result = verifier.execute(authorization="Bearer " + token, payload=payload)
        assert result["status"] == "refused"
    application.installation.ci_identity_policy = None
    assert attach(application, query, token)["status"] == "refused"
    assert verifier.execute(authorization="Bearer " + token, payload=vars(query)) == {
        "schema": 1,
        "status": "refused",
        "reason": "protected CI identity policy unavailable",
    }


def test_conflicting_signed_claims_and_query_refuse_without_new_slot(attached, trusted):
    application, query = attached.application, attached.query
    conflicting = refusal_tests.resign(trusted, claims=trusted[3] | {"head_ref": "other"})
    assert attach(application, query, conflicting)["reason"] == (
        "CI attachment slot conflicts with immutable binding"
    )
    assert attach(application, replace(query, arm_id="f" * 64), attached.token)["status"] == (
        "refused"
    )
    tree = stored(application)["ci_job_attachments"]
    assert list(tree["attachments"]) == [attached.receipt["attachment_id"]]


def test_changed_policy_digest_and_expired_token_cannot_recover(attached, monkeypatch):
    application, query, token = attached.application, attached.query, attached.token
    policy = application.installation.ci_identity_policy
    policy.path.write_text(json.dumps(json.loads(policy.path.read_bytes()), indent=1))
    descriptor = {
        "path": str(policy.path),
        "sha256": hashlib.sha256(policy.path.read_bytes()).hexdigest(),
    }
    reloaded = load_identity_policy(descriptor=descriptor, repository="owner/repo")
    assert reloaded is not None and reloaded.digest != policy.digest
    application.installation.ci_identity_policy = reloaded
    assert attach(application, query, token)["status"] == "refused"
    application.installation.ci_identity_policy = policy
    policy.path.write_bytes(b"tampered")
    assert attach(application, query, token)["status"] == "refused"
    monkeypatch.setattr(time, "time", lambda: 1700000400)
    assert attach(application, query, token)["status"] == "refused"


@pytest.mark.parametrize("change", ["bound", "invalidated", "rearmed"])
def test_recovery_survives_bind_invalidation_and_rearm_but_fresh_attach_refuses(
    attached, trusted, change
):
    application, query = attached.application, attached.query
    if change == "bound":
        mutate(application, lambda record: record.update(observer_arm_bound=True))
    elif change == "invalidated":
        mutate(application, lambda record: record.update(observer_arm_invalidated={"x": 1}))
    else:
        rearm(application)
    assert attach(application, query, attached.token) == attached.receipt
    other = refusal_tests.resign(trusted, claims=trusted[3] | {"check_run_id": "914"})
    assert attach(application, query, other)["status"] == "refused"
    assert len(stored(application)["ci_job_attachments"]["attachments"]) == 1


def rearm(application):
    settings = application.installation
    arm = read_observer_arm(record=stored(application))
    result = arm_before_merge(
        directory=settings.state,
        arm=replace(arm, generation=arm.generation + 1),
        expected_arm_id=stored(application)["observer_arm_id"],
        authorize_current=lambda _: True,
        released_controller=lambda *_: True,
    )
    assert result.status == "armed"


def test_fresh_attachment_refuses_arm_change_during_forge_reads(authenticated, monkeypatch):
    application, query, token, *_ = authenticated
    application.installation.release, application.installation.revision = "v1", "b" * 40
    original = identity_module.CiJobVerifier.verify

    def bound_meanwhile(verifier):
        result = original(verifier)
        mutate(application, lambda record: record.update(observer_arm_bound=True))
        return result

    monkeypatch.setattr(identity_module.CiJobVerifier, "verify", bound_meanwhile)
    assert attach(application, query, token)["reason"] == (
        "CI identity observations changed or unavailable"
    )
    assert "ci_job_attachments" not in stored(application)


@pytest.mark.parametrize("change", ["bound", "rearmed", "expired", "policy"])
def test_persistence_boundary_rechecks_arm_token_and_policy(authenticated, monkeypatch, change):
    application, query, token, *_ = authenticated
    application.installation.release, application.installation.revision = "v1", "b" * 40
    original = attachment_module.verify_ci_invocation

    def race(**kwargs):
        verified = original(**kwargs)
        if change == "bound":
            mutate(application, lambda record: record.update(observer_arm_bound=True))
        elif change == "rearmed":
            rearm(application)
        elif change == "expired":
            monkeypatch.setattr(time, "time", lambda: 1700000300)
        else:
            application.installation.ci_identity_policy.path.write_bytes(b"tampered")
        return verified

    monkeypatch.setattr(attachment_module, "verify_ci_invocation", race)
    assert attach(application, query, token)["reason"] == (
        "CI identity, policy or retained arm changed"
    )
    assert "ci_job_attachments" not in stored(application)


def test_concurrent_identical_commit_returns_first_receipt_and_conflict_refuses(
    authenticated, monkeypatch
):
    application, query, token, *_ = authenticated
    application.installation.release, application.installation.revision = "v1", "b" * 40
    original = attachment_module.verify_ci_invocation
    winner = {}

    def concurrent(**kwargs):
        verified = original(**kwargs)
        if not winner:
            winner["started"] = True
            winner["receipt"] = attach(application, query, token)
        return verified

    monkeypatch.setattr(attachment_module, "verify_ci_invocation", concurrent)
    first = attach(application, query, token)
    assert first == winner["receipt"] and first["status"] == "attached"

    slot = first["attachment_id"]
    other = attachment_receipt(binding=first["binding"] | {"head_ref": "other"})
    assert other["attachment_id"] == slot

    def conflicting(record):
        record["ci_job_attachments"] = {
            "schema": 1,
            "attachments": {
                slot: {
                    "binding": other["binding"],
                    "binding_digest": other["binding_digest"],
                    "receipt": other,
                    "attached_at": 1,
                    "observations": [],
                }
            },
            "collections": {},
        }

    def replaced(**kwargs):
        verified = original(**kwargs)
        mutate(application, conflicting)
        return verified

    mutate(application, lambda record: record.pop("ci_job_attachments"))
    monkeypatch.setattr(attachment_module, "verify_ci_invocation", replaced)
    assert attach(application, query, token)["reason"] == (
        "CI attachment slot holds another immutable binding"
    )


def test_actual_job_cannot_attach_to_another_signed_check(authenticated):
    application, query, token, *_ = authenticated
    application.installation.release, application.installation.revision = "v1", "b" * 40
    first = attach(application, query, token)
    other = attachment_receipt(binding=first["binding"] | {"check_run_id": 999})
    mutate(
        application,
        lambda record: record.update(
            ci_job_attachments={
                "schema": 1,
                "attachments": {
                    other["attachment_id"]: {
                        "binding": other["binding"],
                        "binding_digest": other["binding_digest"],
                        "receipt": other,
                        "attached_at": 1,
                        "observations": [],
                    }
                },
                "collections": {},
            }
        ),
    )
    assert attach(application, query, token)["reason"] == (
        "CI job is already attached to another signed check"
    )


def test_capacity_refuses_without_pruning(authenticated, monkeypatch):
    application, query, token, *_ = authenticated
    application.installation.release, application.installation.revision = "v1", "b" * 40
    monkeypatch.setattr(attachment_module, "_MAX_ATTACHMENTS", 0)
    assert attach(application, query, token)["reason"] == (
        "CI attachment capacity exhausted; nothing was pruned"
    )


def test_malformed_subtree_refuses_attach_but_existing_routes_still_work(attached):
    application, query = attached.application, attached.query
    mutate(application, lambda record: record.update(ci_job_attachments=[]))
    result = attach(application, query, attached.token)
    assert result["reason"] == "CI attachment state or observations unavailable"
    settings = application.installation
    (status, _), admitted = call(application, "/admitted", query, settings.query_secret.decode())
    assert status == "202 Accepted" and admitted["status"] == "admitted"
    assert stored(application)["ci_job_attachments"] == []


def test_existing_rearm_bind_and_invalidation_writers_preserve_subtree(attached, monkeypatch):
    application, query = attached.application, attached.query
    settings = application.installation
    subtree = stored(application)["ci_job_attachments"]
    record = stored(application)
    arm = read_observer_arm(record=record)
    monkeypatch.setattr(
        invalidation_module, "CurrentAuthorityReader", lambda **_: lambda _arm: True
    )
    settings.repo, settings.reader, settings.reader_release = settings.state, ("x",), "r"
    result = ObserverCiInvalidation(installation=settings).execute(
        payload={
            "repository": "owner/repo",
            "arm_id": record["observer_arm_id"],
            "incident_item_id": arm.incident_item_id,
            "attempt_id": arm.attempt_id,
            "generation": arm.generation,
            "owner": arm.owner,
            "phase": arm.phase,
            "incident_operation_id": arm.operation_id,
            "pr_number": arm.pr_number,
            "base_sha": arm.base_sha,
            "head_sha": arm.head_sha,
            "receipt_digest": query.receipt_digest,
            "operation_id": "invalidate-1",
        }
    )
    assert result["status"] == "invalidated"
    assert stored(application)["ci_job_attachments"] == subtree
    rearm(application)
    assert stored(application)["ci_job_attachments"] == subtree
    arm = read_observer_arm(record=stored(application))
    bound = bind_after_merge(
        directory=settings.state,
        arm=arm,
        registration=ObserverRegistration(
            repository=arm.repository,
            incident_item_id=arm.incident_item_id,
            attempt_id=arm.attempt_id,
            operation_id=arm.operation_id,
            generation=arm.generation,
            owner=arm.owner,
            phase=arm.phase,
            head_sha="9" * 40,
            run_id=1,
            required_jobs=arm.required_jobs,
            controller_release=arm.controller_release,
            controller_revision=arm.controller_revision,
            candidate_revision=arm.head_sha,
            authority_receipt=arm.authority_receipt,
        ),
        verify_merged_run=lambda *_: True,
    )
    assert bound.status == "admitted"
    assert stored(application)["ci_job_attachments"] == subtree
    assert attach(application, query, attached.token) == attached.receipt


def test_receipt_is_rejected_by_existing_authority_consumers(attached):
    assert decode_authority(payload=json.dumps(attached.receipt)) is None
    assert attached.effects == []
