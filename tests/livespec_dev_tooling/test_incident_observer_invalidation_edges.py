"""Adversarial store, retry and unlocked-authority races for CI revocation."""

from __future__ import annotations

from dataclasses import asdict, replace
from threading import Barrier, Event, Thread, current_thread

import pytest

from livespec_dev_tooling._incident_observer_store import repository_lock, save_record
from livespec_dev_tooling.incident_observer_invalidation import ObserverCiInvalidation
from tests.livespec_dev_tooling.test_incident_observer_invalidation import (
    _arm,
    _callback,
    _invalidate,
    _record,
    _reply,
    _request,
)
from tests.livespec_dev_tooling.test_incident_observer_invalidation import (
    provisioned as provisioned_fixture,
)

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-wanebl


@pytest.fixture
def provisioned(tmp_path, monkeypatch):
    return provisioned_fixture.__wrapped__(tmp_path, monkeypatch)


def _provision_control(*, application, arm):
    application.installation.release = arm.controller_release
    application.installation.revision = arm.controller_revision
    application.installation.jobs = arm.required_jobs


def _arm_payload(*, arm, expected):
    value = asdict(arm)
    for key in ("required_jobs", "controller_release", "controller_revision"):
        value.pop(key)
    return value | dict(authority_receipt=arm.authority_receipt.hex(), expected_arm_id=expected)


@pytest.mark.parametrize("metadata", ["same", "jobs", "release"])
def test_arm_read_started_before_invalidation_cannot_rearm_same_generation(
    provisioned, monkeypatch, metadata
):
    application, arm, query, payload, attempt, _, _ = provisioned
    _provision_control(application=application, arm=arm)
    if metadata == "jobs":
        application.installation.jobs = ("changed",)
    elif metadata == "release":
        application.installation.release = "v1.171.0"
    entered, release = Event(), Event()

    def reader(argv, **_kwargs):
        if current_thread().name == "arm-worker":
            entered.set()
            assert release.wait(3)
        return _reply(argv=argv, attempt=attempt)

    monkeypatch.setattr("subprocess.run", reader)
    results = []
    worker = Thread(
        name="arm-worker",
        target=lambda: results.append(
            _request(
                application=application,
                path="/arm",
                payload=_arm_payload(arm=arm, expected=query["arm_id"]),
            )
        ),
    )
    worker.start()
    assert entered.wait(3)
    try:
        assert _invalidate(application=application, payload=payload)[1]["status"] == "invalidated"
    finally:
        release.set()
        worker.join(3)
    assert not worker.is_alive() and results[0][1]["status"] == "refused"
    assert _record(application=application)["observer_arm_invalidated"] is not None


def test_new_arm_during_invalidation_read_is_preserved(provisioned, monkeypatch):
    application, arm, query, payload, attempt, _, _ = provisioned
    entered, release = Event(), Event()
    old_attempt = attempt.copy()

    def reader(argv, **_kwargs):
        entered.set()
        assert release.wait(3)
        return _reply(argv=argv, attempt=old_attempt)

    monkeypatch.setattr("subprocess.run", reader)
    results = []
    worker = Thread(
        target=lambda: results.append(_invalidate(application=application, payload=payload))
    )
    worker.start()
    assert entered.wait(3)
    try:
        newer = replace(arm, generation=2, head_sha="d" * 40)
        assert (
            _arm(settings=application.installation, arm=newer, expected=query["arm_id"]).status
            == "armed"
        )
        before = _record(application=application)
    finally:
        release.set()
        worker.join(3)
    assert not worker.is_alive() and results[0][1]["status"] == "refused"
    assert _record(application=application) == before


def test_identical_concurrent_retries_recover_one_receipt(provisioned, monkeypatch):
    application, _, _, payload, attempt, _, _ = provisioned
    barrier = Barrier(2)

    def reader(argv, **_kwargs):
        barrier.wait(timeout=3)
        return _reply(argv=argv, attempt=attempt)

    monkeypatch.setattr("subprocess.run", reader)
    replies = []
    workers = [
        Thread(target=lambda: replies.append(_invalidate(application=application, payload=payload)))
        for _ in range(2)
    ]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(3)
        assert not worker.is_alive()
    assert len(replies) == 2 and replies[0][1] == replies[1][1]
    assert replies[0][1]["status"] == "invalidated"
    assert len(_record(application=application)["ci_invalidations"]) == 1


@pytest.mark.parametrize(
    "change",
    ["list", "entry", "fields", "request", "invalid-request", "operation", "result", "result-type"],
)
def test_corrupt_history_refuses_without_rewriting_it(provisioned, change):
    application, _, _, payload, _, _, _ = provisioned
    assert _invalidate(application=application, payload=payload)[1]["status"] == "invalidated"
    record = _record(application=application)
    history = record["ci_invalidations"]
    entry = history[payload["operation_id"]]
    if change == "list":
        record["ci_invalidations"] = []
    elif change == "entry":
        history[payload["operation_id"]] = []
    elif change == "fields":
        entry["extra"] = True
    elif change == "request":
        entry["request"] = []
    elif change == "invalid-request":
        entry["request"]["generation"] = True
    elif change == "operation":
        entry["request"]["operation_id"] = "another"
    elif change == "result-type":
        entry["result"]["schema"] = True
    else:
        assert change == "result"
        entry["result"]["receipt"] = "f" * 64
    with repository_lock(
        directory=application.installation.state, repository=payload["repository"]
    ) as path:
        save_record(path=path, record=record)
        before = path.read_bytes()
    assert _invalidate(application=application, payload=payload)[1]["status"] == "refused"
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    "change",
    [{"operation_id": "bad operation"}, {"operation_id": 1}, {"generation": 0}, {"pr_number": 0}],
)
def test_additional_malformed_operation_refuses_before_reader(provisioned, change):
    application, _, _, payload, _, calls, _ = provisioned
    assert _invalidate(application=application, payload=payload | change)[1]["status"] == "refused"
    assert calls == []


def test_direct_control_cannot_invalidate_foreign_repository_or_missing_arm(provisioned):
    application, _, _, payload, _, calls, _ = provisioned
    handler = ObserverCiInvalidation(installation=application.installation)
    assert handler.execute(payload=payload | {"repository": "foreign/repo"})["status"] == "refused"
    with repository_lock(
        directory=application.installation.state, repository=payload["repository"]
    ) as path:
        save_record(path=path, record={})
    assert _invalidate(application=application, payload=payload)[1]["status"] == "refused"
    assert calls == []


def test_invalidation_does_not_destroy_exact_delayed_merge_fulfillment(provisioned, monkeypatch):
    application, arm, query, payload, _, _, effects = provisioned
    assert _invalidate(application=application, payload=payload)[1]["status"] == "invalidated"
    binding = dict(repository=arm.repository, head_sha="a" * 40, run_id=91)
    monkeypatch.setattr(
        "livespec_dev_tooling.incident_observer_control.MergedRunVerifier.__call__",
        lambda *_: False,
    )
    assert (
        _request(application=application, path="/bind", payload=binding)[1]["status"] == "refused"
    )
    assert _record(application=application)["registration"] is None
    monkeypatch.setattr(
        "livespec_dev_tooling.incident_observer_control.MergedRunVerifier.__call__", lambda *_: True
    )
    assert (
        _request(application=application, path="/bind", payload=binding)[1]["status"] == "admitted"
    )
    assert _callback(application=application)["status"] == "completed" and len(effects) == 1
    assert (
        _request(
            application=application,
            path="/admitted",
            payload=query,
            secret=application.installation.query_secret,
        )[1]["status"]
        == "refused"
    )
