"""Controlled early-delivery, restart, outage and generation-fence scenarios."""

from __future__ import annotations

import hashlib
import hmac
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Event

import pytest

import livespec_dev_tooling.incident_observer as controller
from livespec_dev_tooling._incident_observer_types import JobCallback, ObserverRegistration
from livespec_dev_tooling.incident_observer import (
    admit_observer,
    handle_job_callback,
    reconcile_action_receipt,
    route_ordinary_action,
)

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-47ij37
_SECRET = b"observer-controller-fixture"


@pytest.fixture
def registration():
    return ObserverRegistration(
        repository="owner/repo",
        incident_item_id="incident-1",
        attempt_id="repair-1",
        operation_id="operation-1",
        generation=1,
        owner="recovery-controller",
        phase="repair",
        head_sha="a" * 40,
        run_id=91,
        required_jobs=("coverage", "lint"),
        controller_release="v1.2.3",
        controller_revision="b" * 40,
        candidate_revision="c" * 40,
        authority_receipt=b"canonical-verified-receipt-1",
    )


def _admit(*, directory, registration, **overrides):
    args = {
        "directory": directory,
        "registration": registration,
        "expected_generation": None,
        "authorize_current": lambda value: value == registration,
        "released_controller": lambda tag, revision: tag == "v1.2.3" and revision == "b" * 40,
    }
    args.update(overrides)
    return admit_observer(**args)


def _delivery(*, registration, **job_changes):
    job = {
        "id": 92,
        "run_id": registration.run_id,
        "head_sha": registration.head_sha,
        "head_branch": registration.branch,
        "name": "coverage",
        "conclusion": "failure",
        "status": "completed",
    }
    job.update(job_changes)
    body = json.dumps(
        {
            "action": "completed",
            "repository": {"full_name": registration.repository},
            "workflow_job": job,
        }
    ).encode()
    return JobCallback(
        body=body,
        signature="sha256=" + hmac.new(_SECRET, body, hashlib.sha256).hexdigest(),
        event="workflow_job",
        delivery_id="job-" + str(job["id"]),
    )


def _handle(*, directory, registration, recover=lambda _: "revert-sha", **job_changes):
    return handle_job_callback(
        directory=directory,
        delivery=_delivery(registration=registration, **job_changes),
        webhook_secret=_SECRET,
        recover=recover,
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"authorize_current": lambda _: False},
        {"released_controller": lambda *_: False},
    ],
)
def test_admission_requires_canonical_current_authority_and_verified_release(
    tmp_path, registration, changes
):
    assert (
        _admit(directory=tmp_path / "controller", registration=registration, **changes).status
        == "refused"
    )
    assert not (tmp_path / "controller").exists()


@pytest.mark.parametrize(
    "changes",
    [
        {"authority_receipt": b""},
        {"required_jobs": ()},
        {"controller_revision": "c" * 40},
    ],
)
def test_incomplete_or_candidate_tree_observer_cannot_admit_merge(tmp_path, registration, changes):
    assert (
        _admit(directory=tmp_path, registration=replace(registration, **changes)).status
        == "refused"
    )


def test_registration_is_idempotent_and_generation_changes_are_compare_and_swap(
    tmp_path, registration
):
    assert _admit(directory=tmp_path, registration=registration).status == "admitted"
    assert _admit(directory=tmp_path, registration=registration).status == "admitted"
    second = replace(registration, generation=2, operation_id="operation-2")
    assert _admit(directory=tmp_path, registration=second).status == "refused"
    assert (
        _admit(
            directory=tmp_path,
            registration=replace(registration, operation_id="other"),
            expected_generation=1,
        ).status
        == "refused"
    )
    assert (
        _admit(directory=tmp_path, registration=second, expected_generation=1).status == "admitted"
    )


def test_unauthenticated_callback_never_reads_the_recovery_store(tmp_path, registration):
    result = handle_job_callback(
        directory=tmp_path / "absent",
        delivery=replace(_delivery(registration=registration), signature="forged"),
        webhook_secret=_SECRET,
        recover=lambda _: pytest.fail("unauthorized effect"),
    )
    assert result.status == "refused"
    assert not (tmp_path / "absent").exists()


def test_unregistered_repository_is_not_an_incident(tmp_path, registration):
    assert _handle(directory=tmp_path, registration=registration).status == "ignored"


@pytest.mark.parametrize(
    "changes",
    [
        {"head_sha": "d" * 40},
        {"head_branch": "feature"},
        {"run_id": 999},
        {"name": "ci-green"},
        {"conclusion": "success"},
        {"conclusion": "cancelled"},
    ],
)
def test_wrong_or_nonfailing_job_cannot_recover(tmp_path, registration, changes):
    _admit(directory=tmp_path, registration=registration)
    result = _handle(
        directory=tmp_path,
        registration=registration,
        recover=lambda _: pytest.fail("wrong event"),
        **changes,
    )
    assert result.status == "ignored"


def test_first_failure_does_not_wait_for_workflow_or_cancel_other_legs(tmp_path, registration):
    _admit(directory=tmp_path, registration=registration)
    effects = []
    workflow = {"status": "in_progress", "remaining_job": "running"}

    def recover(intent):
        assert workflow["status"] == "in_progress"
        persisted = next(tmp_path.glob("*.json")).read_text()
        assert intent.action_id in persisted and '"pending"' in persisted
        assert intent.registration.authority_receipt == registration.authority_receipt
        effects.append(intent.action_id)
        return "revert-sha"

    first = _handle(directory=tmp_path, registration=registration, recover=recover)
    duplicate = _handle(
        directory=tmp_path, registration=registration, id=93, name="lint", recover=recover
    )
    assert first.status == duplicate.status == "completed"
    assert first.action_id == duplicate.action_id
    assert len(effects) == 1
    assert workflow == {"status": "in_progress", "remaining_job": "running"}


def test_timeout_retains_intent_and_blocks_retries_and_generation_replacement(
    tmp_path, registration
):
    _admit(directory=tmp_path, registration=registration)
    pending = _handle(directory=tmp_path, registration=registration, recover=lambda _: None)
    assert pending.status == "pending"
    assert (
        _handle(
            directory=tmp_path,
            registration=registration,
            recover=lambda _: pytest.fail("duplicate effect"),
        ).status
        == "pending"
    )
    assert (
        _admit(
            directory=tmp_path,
            registration=replace(registration, generation=2),
            expected_generation=1,
        ).status
        == "unresolved"
    )
    result = reconcile_action_receipt(
        directory=tmp_path,
        repository=registration.repository,
        action_id=pending.action_id,
        read_exact_receipt=lambda _: None,
        publish_receipt=lambda *_: pytest.fail("no receipt"),
    )
    assert result.status == "pending"


def test_outage_recovery_reconciles_exact_original_receipt_after_correction(tmp_path, registration):
    _admit(directory=tmp_path, registration=registration)
    first = _handle(directory=tmp_path, registration=registration, recover=lambda _: None)
    published = []
    assert (
        reconcile_action_receipt(
            directory=tmp_path,
            repository=registration.repository,
            action_id="unknown",
            read_exact_receipt=lambda _: pytest.fail("unknown action"),
            publish_receipt=lambda *_: False,
        ).status
        == "refused"
    )
    # The recovery provider is independent of both the tenant and its wrapper.
    recovered = reconcile_action_receipt(
        directory=tmp_path,
        repository=registration.repository,
        action_id=first.action_id,
        read_exact_receipt=lambda key: "revert-sha" if key == first.action_id else None,
        publish_receipt=lambda *_: False,
    )
    assert recovered.status == "completed"
    second = replace(
        registration,
        generation=2,
        operation_id="operation-2",
        head_sha="d" * 40,
        run_id=99,
        authority_receipt=b"canonical-receipt-2",
    )
    assert (
        _admit(directory=tmp_path, registration=second, expected_generation=1).status == "admitted"
    )
    assert _handle(directory=tmp_path, registration=registration).status == "ignored"
    assert _handle(directory=tmp_path, registration=second).status == "completed"

    def publish(receipt, action, effect):
        published.append((receipt, action, effect))
        return True

    assert (
        reconcile_action_receipt(
            directory=tmp_path,
            repository=registration.repository,
            action_id=first.action_id,
            read_exact_receipt=lambda _: pytest.fail("already recovered"),
            publish_receipt=publish,
        ).status
        == "reconciled"
    )
    assert published == [(registration.authority_receipt, first.action_id, "revert-sha")]
    assert (
        reconcile_action_receipt(
            directory=tmp_path,
            repository=registration.repository,
            action_id=first.action_id,
            read_exact_receipt=lambda _: pytest.fail("already recovered"),
            publish_receipt=lambda *_: pytest.fail("duplicate reconciliation"),
        ).status
        == "reconciled"
    )


def test_ordinary_reconciler_shares_repository_ownership_and_retains_other_policy(
    tmp_path, registration
):
    def normal():
        return "ordinary-action"

    args = {
        "directory": tmp_path,
        "repository": registration.repository,
        "head_sha": registration.head_sha,
        "run_id": registration.run_id,
        "perform": normal,
    }
    assert route_ordinary_action(**args).status == "ordinary"
    _admit(directory=tmp_path, registration=registration)
    args["perform"] = lambda: pytest.fail("incident must precede rerun or classify")
    assert route_ordinary_action(**args).status == "incident-owned"
    assert (
        route_ordinary_action(**(args | {"run_id": 100, "perform": normal})).receipt
        == "ordinary-action"
    )
    assert (
        route_ordinary_action(**(args | {"head_sha": "d" * 40, "perform": normal})).status
        == "ordinary"
    )


def test_concurrent_deliveries_issue_only_one_effect(tmp_path, registration):
    _admit(directory=tmp_path, registration=registration)
    entered, release = Event(), Event()
    effects = []

    def recover(intent):
        entered.set()
        assert release.wait(timeout=2)
        effects.append(intent.action_id)
        return "one-revert"

    with ThreadPoolExecutor(max_workers=2) as pool:
        one = pool.submit(_handle, directory=tmp_path, registration=registration, recover=recover)
        assert entered.wait(timeout=2)
        two = pool.submit(
            _handle, directory=tmp_path, registration=registration, recover=recover, id=93
        )
        release.set()
        assert one.result(timeout=2).action_id == two.result(timeout=2).action_id
    assert len(effects) == 1


@pytest.mark.parametrize("corrupt", [[], {"registration": []}, {"registration": {}}])
def test_corrupt_controller_state_cannot_be_read_as_unregistered(tmp_path, registration, corrupt):
    _admit(directory=tmp_path, registration=registration)
    path = next(tmp_path.glob("*.json"))
    path.write_text(json.dumps(corrupt))
    with pytest.raises(TypeError, match="invalid"):
        _handle(
            directory=tmp_path,
            registration=registration,
            recover=lambda _: pytest.fail("corrupt authority"),
        )


def test_noncooperating_generation_change_is_rechecked_immediately_before_effect(
    tmp_path, registration, monkeypatch
):
    _admit(directory=tmp_path, registration=registration)
    original = controller.load_record
    reads = []

    def changed(*, path):
        record = original(path=path)
        reads.append(path)
        if len(reads) == 2:
            record["registration"]["generation"] = 2
        return record

    monkeypatch.setattr(controller, "load_record", changed)
    result = _handle(
        directory=tmp_path,
        registration=registration,
        recover=lambda _: pytest.fail("stale generation effect"),
    )
    assert result.status == "refused"


def test_reconciliation_never_substitutes_current_authority_for_missing_action_receipt(
    tmp_path, registration
):
    _admit(directory=tmp_path, registration=registration)
    first = _handle(directory=tmp_path, registration=registration)
    path = next(tmp_path.glob("*.json"))
    record = json.loads(path.read_bytes())
    record["actions"][first.action_id]["registration"] = None
    path.write_text(json.dumps(record))
    result = reconcile_action_receipt(
        directory=tmp_path,
        repository=registration.repository,
        action_id=first.action_id,
        read_exact_receipt=lambda _: pytest.fail("missing immutable authority"),
        publish_receipt=lambda *_: pytest.fail("wrong publication"),
    )
    assert result.status == "refused"
