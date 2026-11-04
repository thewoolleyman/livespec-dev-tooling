"""Exercise real observer fencing, restart and canonical consumer recovery."""

from __future__ import annotations

from dataclasses import replace

import pytest

from livespec_dev_tooling._incident_observer_store import (
    load_record,
    registration_record,
    repository_lock,
    save_record,
)
from livespec_dev_tooling._incident_observer_types import (
    LeafCompletion,
    ObserverRegistration,
    RecoveryIntent,
)
from livespec_dev_tooling.incident_release_recovery import (
    IncidentReleaseRecovery,
    ReleaseAttribution,
)

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-vg36aq


def _registration():
    return ObserverRegistration(
        repository="owner/source",
        incident_item_id="incident-1",
        attempt_id="attempt-1",
        operation_id="operation-1",
        generation=1,
        owner="controller",
        phase="repair",
        head_sha="a" * 40,
        run_id=91,
        required_jobs=("coverage",),
        controller_release="v1",
        controller_revision="b" * 40,
        candidate_revision="c" * 40,
        authority_receipt=b"canonical-exact-receipt",
    )


def _attribution(**changes):
    value = ReleaseAttribution(
        source_sha="a" * 40,
        release_tag="v2",
        image_digest="sha256:" + "d" * 64,
        pin_carrier="owner/consumer#27",
        consumer_repository="owner/consumer",
        installed_revision="e" * 40,
        installation_receipt="installed:verified",
    )
    return replace(value, **changes)


def _controller(directory, **changes):
    values = dict(
        directory=directory,
        authorize_current=lambda _: True,
        verify_attribution=lambda *_: True,
        record_canonical=lambda *_: "canonical-adopted",
        recover_canonical=lambda *_: "consumer-correction-owned",
        reopen_canonical=lambda *_: "canonical-reopened",
    )
    values.update(changes)
    return IncidentReleaseRecovery(**values)


def _seed(directory, registration, **changes):
    with repository_lock(directory=directory, repository=registration.repository) as path:
        record = {"registration": registration_record(registration=registration), "foreign": 17}
        record.update(changes)
        save_record(path=path, record=record)


def _intent(registration):
    return RecoveryIntent(
        action_id="recover-exact-1",
        registration=registration,
        completion=LeafCompletion(
            delivery_id="delivery",
            repository=registration.repository,
            head_sha=registration.head_sha,
            branch="master",
            run_id=91,
            job_id=4,
            job_name="coverage",
            conclusion="failure",
        ),
    )


def _action(directory, subject, **changes):
    registration = subject
    intent = _intent(registration)
    with repository_lock(directory=directory, repository=registration.repository) as path:
        record = load_record(path=path)
        record["actions"] = {
            intent.action_id: {
                "registration": registration_record(registration=registration),
                "status": "completed",
                "receipt": "exact-revert",
                **changes,
            }
        }
        save_record(path=path, record=record)
    return intent


def _mutate(directory, subject, **changes):
    registration = subject
    with repository_lock(directory=directory, repository=registration.repository) as path:
        record = load_record(path=path)
        record.update(changes)
        save_record(path=path, record=record)


def test_mutable_action_reconciliation_and_new_consumer_do_not_repeat_old_correction(tmp_path):
    registration = _registration()
    _seed(tmp_path, registration)
    calls = []
    controller = _controller(
        tmp_path, recover_canonical=lambda *args: calls.append(args) or "owned"
    )
    first = _attribution()
    assert (
        controller.acknowledge_adoption(registration=registration, attribution=first).status
        == "acknowledged"
    )
    intent = _action(tmp_path, registration)
    assert controller.recover(intent=intent).status == "reconciled"
    _action(tmp_path, registration, reconciled=True)
    assert controller.recover(intent=intent).status == "reconciled"
    assert len(calls) == 1
    second = _attribution(consumer_repository="owner/second", pin_carrier="owner/second#7")
    assert (
        controller.acknowledge_adoption(registration=registration, attribution=second).status
        == "fenced"
    )
    assert controller.recover(intent=intent).status == "reconciled"
    assert len(calls) == 2
    assert {args[1][0].consumer_repository for args in calls} == {"owner/consumer", "owner/second"}
    assert calls[0][2] != calls[1][2]


def test_old_history_receipts_survive_registration_replacement(tmp_path):
    registration = _registration()
    _seed(tmp_path, registration)
    controller = _controller(tmp_path)
    assert (
        controller.acknowledge_adoption(
            registration=registration, attribution=_attribution()
        ).status
        == "acknowledged"
    )
    intent = _action(tmp_path, registration)
    newer = replace(registration, generation=2, attempt_id="corrected")
    _mutate(tmp_path, registration, registration=registration_record(registration=newer))
    assert controller.recover(intent=intent).status == "reconciled"
    assert (
        controller.reopen(
            registration=registration, regression_id="other-pr", evidence="verified"
        ).status
        == "reopened"
    )
    assert (
        controller.run_queued_adoption(
            registration=registration,
            attribution=_attribution(),
            publish=lambda *_: pytest.fail("stale publish"),
        ).status
        == "fenced"
    )


def test_canonical_receipt_is_retained_if_generation_moves_during_effect(tmp_path):
    registration = _registration()
    _seed(tmp_path, registration)
    newer = replace(registration, generation=2)

    def publish(*_):
        _mutate(tmp_path, registration, registration=registration_record(registration=newer))
        return "known-exact-effect"

    controller = _controller(tmp_path, record_canonical=publish)
    assert (
        controller.acknowledge_adoption(
            registration=registration, attribution=_attribution()
        ).status
        == "fenced"
    )
    with repository_lock(directory=tmp_path, repository=registration.repository) as path:
        record = load_record(path=path)
    assert next(iter(record["release_attribution"].values()))["receipt"] == "known-exact-effect"


@pytest.mark.parametrize(
    ("changes", "status"),
    [
        ({}, "refused"),
        ({"status": "pending"}, "pending"),
        ({"receipt": ""}, "pending"),
        ({"registration": {}}, "refused"),
    ],
)
def test_recovery_never_assigns_consumers_without_exact_inverse_receipt(tmp_path, changes, status):
    registration = _registration()
    _seed(tmp_path, registration)
    if changes:
        _action(tmp_path, registration, **changes)
    assert _controller(tmp_path).recover(intent=_intent(registration)).status == status


def test_empty_history_and_empty_regression_evidence_refuse(tmp_path):
    registration = _registration()
    _seed(tmp_path, registration)
    _action(tmp_path, registration)
    controller = _controller(tmp_path)
    assert controller.recover(intent=_intent(registration)).status == "refused"
    assert (
        controller.reopen(registration=registration, regression_id="", evidence="").status
        == "refused"
    )
    assert (
        controller.reopen(
            registration=registration, regression_id="related", evidence="proof"
        ).status
        == "refused"
    )


def test_unknown_canonical_adoption_and_consumer_correction_are_pending(tmp_path):
    registration = _registration()
    _seed(tmp_path, registration)
    controller = _controller(
        tmp_path,
        record_canonical=lambda *_: "",
        recover_canonical=lambda *_: "",
        reopen_canonical=lambda *_: "",
    )
    assert (
        controller.acknowledge_adoption(
            registration=registration, attribution=_attribution()
        ).status
        == "pending"
    )
    assert (
        controller.acknowledge_adoption(
            registration=registration, attribution=_attribution()
        ).status
        == "pending"
    )
    _action(tmp_path, registration)
    assert controller.recover(intent=_intent(registration)).status == "pending"
    assert (
        controller.reopen(
            registration=registration, regression_id="related", evidence="proof"
        ).status
        == "pending"
    )


def test_duplicate_related_regression_recovers_same_exact_receipt(tmp_path):
    registration = _registration()
    _seed(tmp_path, registration)
    calls = []
    controller = _controller(
        tmp_path, reopen_canonical=lambda *args: calls.append(args) or "same-chain-reopened"
    )
    assert (
        controller.acknowledge_adoption(
            registration=registration, attribution=_attribution()
        ).status
        == "acknowledged"
    )
    for _ in range(2):
        assert (
            controller.reopen(
                registration=registration,
                regression_id="related-pr:9/job:7",
                evidence="verified-diff",
            ).receipt
            == "same-chain-reopened"
        )
    assert len(calls) == 1
