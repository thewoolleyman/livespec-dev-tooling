"""Exercise real observer fencing, restart and canonical consumer recovery."""

from __future__ import annotations

from dataclasses import replace

import pytest

from livespec_dev_tooling._incident_observer_store import (
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


def test_first_queued_publication_does_not_invent_future_installation_receipt(tmp_path):
    registration = _registration()
    _seed(tmp_path, registration)
    queued = _attribution(installation_receipt="")
    controller = _controller(tmp_path)
    assert (
        controller.run_queued_adoption(
            registration=registration,
            attribution=queued,
            publish=lambda *_: pytest.fail("unverified first publication"),
        ).status
        == "refused"
    )
    assert (
        controller.acknowledge_adoption(registration=registration, attribution=queued).status
        == "refused"
    )
    controller = replace(
        controller,
        verify_queued=lambda reg, attr: reg == registration and attr == queued,
        verify_attribution=lambda reg, attr: reg == registration
        and attr.installation_receipt == "real-installed-receipt",
    )
    assert (
        controller.run_queued_adoption(
            registration=registration,
            attribution=queued,
            publish=lambda *_: "real-installed-receipt",
        ).status
        == "published"
    )
    installed = replace(queued, installation_receipt="real-installed-receipt")
    assert (
        controller.acknowledge_adoption(registration=registration, attribution=installed).status
        == "acknowledged"
    )


def test_current_reader_change_inside_lock_prevents_publish(tmp_path):
    registration = _registration()
    _seed(tmp_path, registration)
    calls = []

    def current(_):
        calls.append(1)
        return len(calls) == 1

    controller = _controller(tmp_path, authorize_current=current)
    assert (
        controller.run_queued_adoption(
            registration=registration,
            attribution=_attribution(),
            publish=lambda *_: pytest.fail("stale current publish"),
        ).status
        == "fenced"
    )


@pytest.mark.parametrize("denied", ["authorize_current", "verify_attribution"])
def test_queued_dispatch_refuses_unverified_identity_before_publish(tmp_path, denied):
    registration = _registration()
    _seed(tmp_path, registration)
    controller = _controller(tmp_path, **{denied: lambda *_: False})
    assert (
        controller.run_queued_adoption(
            registration=registration,
            attribution=_attribution(),
            publish=lambda *_: pytest.fail("unauthorized publish"),
        ).status
        == "refused"
    )
