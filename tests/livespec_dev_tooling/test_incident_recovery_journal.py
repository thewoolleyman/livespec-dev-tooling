"""Retained recovery authority and durable non-authorizing journal behavior."""

from __future__ import annotations

import base64
import hashlib
import json
import sys
from dataclasses import asdict, replace
from threading import Barrier, Thread

import pytest

from livespec_dev_tooling._incident_inverse_types import (
    InverseConflictRequest,
    InversePlan,
    InversePublishRequest,
    LandedIncident,
)
from livespec_dev_tooling._incident_observer_store import registration_record, save_record
from livespec_dev_tooling._incident_observer_types import (
    LeafCompletion,
    ObserverArm,
    ObserverRegistration,
    RecoveryIntent,
)
from livespec_dev_tooling.incident_controller_installation import ControllerInstallation
from livespec_dev_tooling.incident_recovery_journal import RecoveryJournal

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-dln3ac


def _wire(value):
    return json.loads(
        json.dumps(
            value,
            sort_keys=True,
            default=lambda item: base64.b64encode(item).decode("ascii"),
        )
    )


def _arm():
    return ObserverArm(
        repository="owner/repo",
        incident_item_id="incident-1",
        attempt_id="attempt-1",
        operation_id="operation-1",
        generation=3,
        owner="controller-owner",
        phase="repair",
        pr_number=71,
        base_sha="a" * 40,
        head_sha="b" * 40,
        required_jobs=("tests",),
        controller_release="v1.171.0",
        controller_revision="c" * 40,
        authority_receipt=b"retained-canonical-authority",
    )


def _intent():
    arm = _arm()
    registration = ObserverRegistration(
        repository=arm.repository,
        incident_item_id=arm.incident_item_id,
        attempt_id=arm.attempt_id,
        operation_id=arm.operation_id,
        generation=arm.generation,
        owner=arm.owner,
        phase=arm.phase,
        head_sha="d" * 40,
        run_id=81,
        required_jobs=arm.required_jobs,
        controller_release=arm.controller_release,
        controller_revision=arm.controller_revision,
        candidate_revision=arm.head_sha,
        authority_receipt=arm.authority_receipt,
    )
    completion = LeafCompletion(
        delivery_id="delivery-1",
        repository=registration.repository,
        head_sha=registration.head_sha,
        branch="master",
        run_id=registration.run_id,
        job_id=82,
        job_name="tests",
        conclusion="failure",
    )
    identity = f"{arm.repository}:{arm.operation_id}:{arm.generation}:recover"
    return RecoveryIntent(
        action_id=hashlib.sha256(identity.encode()).hexdigest(),
        registration=registration,
        completion=completion,
        observer_arm=arm,
    )


def _scope(intent):
    arm = intent.observer_arm
    assert arm is not None
    return LandedIncident(
        repository=arm.repository,
        pr_number=arm.pr_number,
        original_base_sha=arm.base_sha,
        original_head_sha=arm.head_sha,
        before_sha="e" * 40,
        merge_sha=intent.registration.head_sha,
        landed_commits=(intent.registration.head_sha,),
        landed_trees=("f" * 40,),
        patch_sha256="1" * 64,
        changed_paths=("product.py",),
        authority_sha256=hashlib.sha256(arm.authority_receipt).hexdigest(),
    )


def _record(intent):
    arm = asdict(intent.observer_arm)
    arm["authority_receipt"] = intent.observer_arm.authority_receipt.hex()
    action = {
        "status": "pending",
        "registration": registration_record(registration=intent.registration),
        "completion": asdict(intent.completion),
        "receipt": None,
        "observer_arm": arm,
        "observer_arm_id": hashlib.sha256(json.dumps(arm, sort_keys=True).encode()).hexdigest(),
    }
    return {**action, "actions": {intent.action_id: action}}


@pytest.fixture
def protected(tmp_path):
    state, repo = tmp_path / "state", tmp_path / "reference"
    state.mkdir(mode=0o700)
    repo.mkdir(mode=0o700)
    for name in ("recovery-journal", "recovery-journal-contexts"):
        (state / name).mkdir(mode=0o700)
    intent = _intent()
    path = state / (hashlib.sha256(intent.registration.repository.encode()).hexdigest() + ".json")
    save_record(path=path, record=_record(intent))
    installation = ControllerInstallation(
        repository=intent.registration.repository,
        repo=repo,
        state=state,
        reader=(sys.executable,),
        reader_release="v0.284.0",
        principal=(sys.executable,),
        release=intent.registration.controller_release,
        revision=intent.registration.controller_revision,
        jobs=intent.registration.required_jobs,
        webhook_secret=b"unused-webhook-fixture",
        control_secret=b"unused-control-fixture",
        query_secret=b"unused-query-fixture",
        port=8765,
        config=state.parent / "controller.json",
    )
    return RecoveryJournal(installation=installation), installation, intent, path


def _publish(intent, *, message="Revert incident"):
    return InversePublishRequest(
        intent=intent,
        plan=InversePlan(
            scope=_scope(intent),
            expected_head="2" * 40,
            tree_sha="3" * 40,
            inverse_patch=b"controlled binary inverse\x00\xff",
        ),
        message=message,
    )


def _conflict(intent):
    head = "2" * 40
    return InverseConflictRequest(
        intent=intent,
        scope=_scope(intent),
        expected_head=head,
        reason="independently authenticated overlapping change",
        receipt=f"rollback-conflict:{intent.action_id}:owner:{intent.registration.owner}:head:{head}",
    )


def _context(installation, request):
    path = installation.state / "recovery-journal-contexts" / (request.intent.action_id + ".json")
    # Controlled protected scope fixture, not production forge authentication.
    path.write_text(json.dumps({"schema": 1, "request": _wire(asdict(request))}))
    path.chmod(0o600)
    return path


def test_lookup_requires_exact_retained_action_not_current_top_level_arm(protected):
    journal, _, intent, path = protected
    assert journal.lookup(intent=intent).status == "absent"
    wrong = replace(intent, registration=replace(intent.registration, owner="another-owner"))
    assert journal.lookup(intent=wrong).status == "refused"
    record = json.loads(path.read_text())
    record["registration"]["generation"] = 100
    record["observer_arm"]["head_sha"] = "9" * 40
    save_record(path=path, record=record)
    result = journal.lookup(intent=intent)
    assert result.status == "absent" and result.receipt is None
    assert result.authorizes_current_effects is False


def test_exact_concurrent_reservation_survives_restart_and_conflicting_bytes(protected):
    journal, installation, intent, _ = protected
    request = _publish(intent)
    barrier, results = Barrier(2), []

    def reserve():
        barrier.wait(timeout=3)
        results.append(journal.reserve(request=request))

    workers = [Thread(target=reserve) for _ in range(2)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(3)
        assert not worker.is_alive()
    assert len(results) == 2 and results[0] == results[1]
    assert results[0].status == "reserved" and results[0].authorizes_current_effects is False
    restarted = RecoveryJournal(installation=installation)
    assert restarted.reserve(request=request) == results[0]
    assert (
        restarted.reserve(request=_publish(intent, message="conflicting bytes")).status == "refused"
    )
    assert restarted.lookup(intent=intent).status == "reserved"


def test_conflict_needs_independent_context_then_recovers_its_exact_receipt(protected):
    journal, installation, intent, _ = protected
    request = _conflict(intent)
    assert journal.record_conflict(request=request).status == "refused"
    _context(installation, request)
    result = journal.record_conflict(request=request)
    assert result.status == "recorded" and result.receipt == request.receipt
    assert result.authorizes_current_effects is False
    restarted = RecoveryJournal(installation=installation)
    assert restarted.record_conflict(request=request) == result
    assert restarted.lookup(intent=intent).receipt == result.receipt
    assert (
        restarted.record_conflict(request=replace(request, reason="different claim")).status
        == "refused"
    )


def test_completed_action_missing_journal_is_unavailable_and_cannot_gain_terminal_result(protected):
    journal, installation, intent, path = protected
    record = json.loads(path.read_text())
    record["actions"][intent.action_id].update(status="completed", receipt="prior-effect")
    save_record(path=path, record=record)
    request = _conflict(intent)
    _context(installation, request)
    assert journal.lookup(intent=intent).status == "unavailable"
    assert journal.reserve(request=_publish(intent)).status == "refused"
    assert journal.record_conflict(request=request).status == "refused"
