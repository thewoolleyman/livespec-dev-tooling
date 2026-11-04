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
    ObserverRegistration,
)
from livespec_dev_tooling.incident_release_recovery import (
    IncidentReleaseRecovery,
    ReleaseAttribution,
    ReleaseLookup,
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


def test_unknown_publish_requires_exact_lookup_before_any_repeat(tmp_path):
    registration = _registration()
    _seed(tmp_path, registration)
    calls = []

    def lost_reply(*args):
        calls.append(args)
        raise TimeoutError

    controller = _controller(tmp_path)
    assert (
        controller.run_queued_adoption(
            registration=registration, attribution=_attribution(), publish=lost_reply
        ).status
        == "pending"
    )
    assert (
        controller.run_queued_adoption(
            registration=registration, attribution=_attribution(), publish=lost_reply
        ).status
        == "pending"
    )
    assert len(calls) == 1
    identity = calls[0][1]
    controller = replace(
        controller,
        lookup_effect=lambda operation, value: ReleaseLookup(
            operation=operation, identity=value, status="recorded", receipt="exact-published"
        ),
    )
    assert (
        controller.run_queued_adoption(
            registration=registration, attribution=_attribution(), publish=lost_reply
        ).receipt
        == "exact-published"
    )
    assert len(calls) == 1
    assert (
        controller.run_queued_adoption(
            registration=registration, attribution=_attribution(), publish=lost_reply
        ).status
        == "published"
    )
    assert identity


@pytest.mark.parametrize(
    "answer",
    ["unknown", "wrong-operation", "wrong-identity", "absent-with-receipt", "error", "malformed"],
)
def test_unusable_lookup_never_repeats_unknown_effect(tmp_path, answer):
    registration = _registration()
    _seed(tmp_path, registration)
    controller = _controller(tmp_path)
    assert (
        controller.run_queued_adoption(
            registration=registration, attribution=_attribution(), publish=lambda *_: ""
        ).status
        == "pending"
    )

    def lookup(operation, identity):
        if answer == "error":
            raise TimeoutError
        if answer == "malformed":
            return None
        return ReleaseLookup(
            operation="foreign" if answer == "wrong-operation" else operation,
            identity="foreign" if answer == "wrong-identity" else identity,
            status="absent" if answer == "absent-with-receipt" else "unknown",
            receipt="invalid" if answer == "absent-with-receipt" else "",
        )

    controller = replace(controller, lookup_effect=lookup)
    assert (
        controller.run_queued_adoption(
            registration=registration,
            attribution=_attribution(),
            publish=lambda *_: pytest.fail("duplicate effect"),
        ).status
        == "pending"
    )


def test_exact_absence_retries_but_new_fence_after_lookup_prevents_effect(tmp_path):
    registration = _registration()
    _seed(tmp_path, registration)
    controller = _controller(tmp_path)
    assert (
        controller.run_queued_adoption(
            registration=registration, attribution=_attribution(), publish=lambda *_: ""
        ).status
        == "pending"
    )

    def lookup(operation, identity):
        # The lookup is invoked under the caller-held lock. Simulate a changed
        # independent fence without recursively acquiring that same flock.
        path = next(tmp_path.glob("*.json"))
        record = load_record(path=path)
        record["actions"] = {
            "new-recovery": {
                "registration": registration_record(registration=registration),
                "status": "pending",
                "receipt": None,
            }
        }
        save_record(path=path, record=record)
        return ReleaseLookup(operation=operation, identity=identity, status="absent")

    controller = replace(controller, lookup_effect=lookup)
    assert (
        controller.run_queued_adoption(
            registration=registration,
            attribution=_attribution(),
            publish=lambda *_: pytest.fail("post-lookup stale effect"),
        ).status
        == "fenced"
    )


def test_exact_absence_allows_one_new_effect(tmp_path):
    registration = _registration()
    _seed(tmp_path, registration)
    controller = _controller(tmp_path)
    assert (
        controller.run_queued_adoption(
            registration=registration, attribution=_attribution(), publish=lambda *_: ""
        ).status
        == "pending"
    )
    controller = replace(
        controller,
        lookup_effect=lambda operation, identity: ReleaseLookup(
            operation=operation, identity=identity, status="absent"
        ),
    )
    assert (
        controller.run_queued_adoption(
            registration=registration, attribution=_attribution(), publish=lambda *_: "real-effect"
        ).status
        == "published"
    )
