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


@pytest.mark.parametrize(
    "changes",
    [{"release_tag": ""}, {"source_sha": ""}, {"irreversible": True}, {"irreversible": 1}],
)
def test_invalid_release_attribution_never_acknowledges(tmp_path, changes):
    registration = _registration()
    _seed(tmp_path, registration)
    assert (
        _controller(tmp_path)
        .acknowledge_adoption(registration=registration, attribution=_attribution(**changes))
        .status
        == "refused"
    )


def test_complete_landed_chain_attribution_can_name_nonterminal_source(tmp_path):
    registration = _registration()
    _seed(tmp_path, registration)
    earlier_source = _attribution(source_sha="f" * 40)
    assert (
        _controller(
            tmp_path,
            verify_attribution=lambda reg, attr: attr == earlier_source and reg == registration,
        )
        .acknowledge_adoption(registration=registration, attribution=earlier_source)
        .status
        == "acknowledged"
    )
    assert (
        _controller(tmp_path, verify_attribution=lambda *_: False)
        .acknowledge_adoption(registration=registration, attribution=earlier_source)
        .status
        == "refused"
    )


def test_corrupt_controller_receipts_refuse_without_replacement(tmp_path):
    registration = _registration()
    _seed(tmp_path, registration, release_attribution=[])
    assert (
        _controller(tmp_path)
        .acknowledge_adoption(registration=registration, attribution=_attribution())
        .status
        == "refused"
    )


def test_foreign_attempt_attribution_is_ignored_and_corruption_refuses_recovery(tmp_path):
    registration = _registration()
    _seed(tmp_path, registration)
    controller = _controller(tmp_path)
    assert (
        controller.acknowledge_adoption(
            registration=registration, attribution=_attribution()
        ).status
        == "acknowledged"
    )
    with repository_lock(directory=tmp_path, repository=registration.repository) as path:
        record = load_record(path=path)
        entries = record["release_attribution"]
        original = next(iter(entries.values()))
        entries["foreign-attempt"] = {**original, "registration": {}}
        save_record(path=path, record=record)
    assert (
        controller.reopen(
            registration=registration, regression_id="related", evidence="proof"
        ).status
        == "reopened"
    )
    with repository_lock(directory=tmp_path, repository=registration.repository) as path:
        record = load_record(path=path)
        original = next(
            value for value in record["release_attribution"].values() if value["registration"]
        )
        original["attribution"]["release_tag"] = ""
        save_record(path=path, record=record)
    assert (
        controller.reopen(
            registration=registration, regression_id="another", evidence="proof"
        ).status
        == "refused"
    )
