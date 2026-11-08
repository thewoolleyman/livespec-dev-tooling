"""Exercise real observer fencing, restart and canonical consumer recovery."""

from __future__ import annotations

from dataclasses import replace

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


def test_attribution_survives_restart_before_adoption_ack(tmp_path):
    registration = _registration()
    _seed(tmp_path, registration)
    seen = []
    controller = _controller(tmp_path, record_canonical=lambda *args: seen.append(args) or "ack")
    assert (
        controller.acknowledge_adoption(
            registration=registration, attribution=_attribution()
        ).status
        == "acknowledged"
    )
    assert len(seen) == 1
    with repository_lock(directory=tmp_path, repository=registration.repository) as path:
        record = load_record(path=path)
    assert record["foreign"] == 17
    assert record["release_attribution"]
    assert (
        _controller(tmp_path)
        .acknowledge_adoption(registration=registration, attribution=_attribution())
        .status
        == "acknowledged"
    )


def test_recovery_fences_stale_adoption_and_owns_installed_consumers(tmp_path):
    registration = _registration()
    _seed(tmp_path, registration)
    controller = _controller(tmp_path)
    assert (
        controller.acknowledge_adoption(
            registration=registration, attribution=_attribution()
        ).status
        == "acknowledged"
    )
    intent = _intent(registration)
    with repository_lock(directory=tmp_path, repository=registration.repository) as path:
        record = load_record(path=path)
        record["actions"] = {
            intent.action_id: {
                "registration": registration_record(registration=registration),
                "status": "completed",
                "receipt": "exact-revert-sha",
            }
        }
        save_record(path=path, record=record)
    assert (
        controller.acknowledge_adoption(
            registration=registration, attribution=_attribution(consumer_repository="owner/late")
        ).status
        == "fenced"
    )
    assert controller.recover(intent=intent).status == "reconciled"
    assert controller.recover(intent=intent).status == "reconciled"


def test_irreversible_adoption_refuses_an_unverified_compensation_string(tmp_path):
    registration = _registration()
    _seed(tmp_path, registration)
    controller = _controller(tmp_path)
    published = []
    attribution = _attribution(irreversible=True, compensation_receipt="safe:existing")
    assert (
        controller.acknowledge_adoption(
            registration=registration, attribution=_attribution(irreversible=True)
        ).status
        == "refused"
    )
    assert (
        controller.acknowledge_adoption(
            registration=registration,
            attribution=attribution,
        ).status
        == "refused"
    )
    assert (
        controller.run_queued_adoption(
            registration=registration,
            attribution=attribution,
            publish=lambda *args: published.append(args) or "published",
        ).status
        == "refused"
    )
    assert published == []


def test_late_regression_reopens_canonical_chain_and_fences_cleanup(tmp_path):
    registration = _registration()
    _seed(tmp_path, registration)
    controller = _controller(tmp_path)
    assert (
        controller.acknowledge_adoption(
            registration=registration, attribution=_attribution()
        ).status
        == "acknowledged"
    )
    assert (
        controller.reopen(
            registration=registration,
            regression_id="other-pr:53/job:7",
            evidence="attribution:verified",
        ).status
        == "reopened"
    )
    assert (
        controller.acknowledge_adoption(
            registration=registration, attribution=_attribution()
        ).status
        == "fenced"
    )


def test_queued_dispatch_checks_shared_fence_immediately_before_effect(tmp_path):
    registration = _registration()
    _seed(tmp_path, registration)
    calls = []
    controller = _controller(tmp_path)
    assert (
        controller.run_queued_adoption(
            registration=registration,
            attribution=_attribution(),
            publish=lambda *args: calls.append(args) or "published-pin-carrier",
        ).status
        == "published"
    )
    assert len(calls) == 1
    with repository_lock(directory=tmp_path, repository=registration.repository) as path:
        record = load_record(path=path)
        record["actions"] = {
            "recover": {
                "registration": registration_record(registration=registration),
                "status": "pending",
                "receipt": None,
            }
        }
        save_record(path=path, record=record)
    assert (
        controller.run_queued_adoption(
            registration=registration,
            attribution=_attribution(),
            publish=lambda *args: calls.append(args) or "wrong-stale-adoption",
        ).status
        == "fenced"
    )
    assert len(calls) == 1
