"""Collected outcomes append durable non-authorizing history without blocking recovery."""

from __future__ import annotations

import io
import json
import threading
import time

import pytest

from livespec_dev_tooling import incident_ci_job_collection as collection_module
from livespec_dev_tooling.incident_ci_job_collection import CiJobCollection
from livespec_dev_tooling.incident_ci_payload import decode_authority
from livespec_dev_tooling.incident_forge_reads import ForgeReads
from livespec_dev_tooling.incident_observer_service import ControllerService
from tests.livespec_dev_tooling import test_incident_ci_attachment_edges as edge_tests
from tests.livespec_dev_tooling import test_incident_ci_job_history as history_tests

trusted = edge_tests.trusted
correlated = edge_tests.correlated
authenticated = edge_tests.authenticated
attached = edge_tests.attached
conclude = history_tests.conclude
stored = edge_tests.stored
mutate = edge_tests.mutate

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-si6uu7
_FALSE = ("authorizes_current_effects", "ci_admission", "authorizes_merge", "normal_factory_proof")


def post(application, path, payload, secret):
    body = json.dumps(payload).encode()
    response = []
    environ = {
        "PATH_INFO": path,
        "REQUEST_METHOD": "POST",
        "CONTENT_LENGTH": str(len(body)),
        "HTTP_AUTHORIZATION": "Bearer " + secret.decode(),
        "wsgi.input": io.BytesIO(body),
    }
    raw = b"".join(application(environ, lambda status, _: response.append(status)))
    return response[0], json.loads(raw)


def collect(fixture, collection_id, *, application=None, attachment_id=None):
    application = application or fixture.application
    payload = {
        "repository": "owner/repo",
        "attachment_id": attachment_id or fixture.receipt["attachment_id"],
        "collection_id": collection_id,
    }
    return post(application, "/ci/jobs/collect", payload, application.installation.control_secret)


def inspect(fixture, *, secret=None):
    settings = fixture.application.installation
    payload = {"repository": "owner/repo", "attachment_id": fixture.receipt["attachment_id"]}
    return post(fixture.application, "/ci/jobs/inspect", payload, secret or settings.query_secret)


def test_collection_is_durable_idempotent_and_non_authorizing(attached):
    conclude(attached.records)
    status, result = collect(attached, "collect-1")
    assert status == "202 Accepted" and result["status"] == "observed"
    assert all(result[key] is False for key in _FALSE)
    assert result["observation"]["status"] == "successful"
    assert result["observation"]["sequence"] == 1
    assert decode_authority(payload=json.dumps(result)) is None
    calls = len(attached.calls)
    restarted = ControllerService(
        installation=attached.application.installation, recover=attached.application.recover
    )
    assert collect(attached, "collect-1", application=restarted) == (status, result)
    assert len(attached.calls) == calls
    status, inspected = inspect(attached)
    assert status == "202 Accepted" and inspected["status"] == "inspected"
    assert inspected["attachment"] == attached.receipt
    assert inspected["observations"] == [result["observation"]]
    assert inspected["observation_count"] == 1 and all(inspected[k] is False for k in _FALSE)


def test_role_separation_and_exact_locators(attached):
    settings = attached.application.installation
    payload = {
        "repository": "owner/repo",
        "attachment_id": attached.receipt["attachment_id"],
        "collection_id": "c",
    }
    application = attached.application
    for path, secret in (
        ("/ci/jobs/collect", settings.query_secret),
        ("/ci/jobs/inspect", settings.control_secret),
    ):
        assert post(application, path, payload, secret)[0] == "403 Forbidden"
    assert post(application, "/ci/jobs/collect", payload, attached.token.encode())[1]["status"] == (
        "refused"
    )
    assert "ci_job_attachments" in stored(application)
    assert stored(application)["ci_job_attachments"]["collections"] == {}
    handler = CiJobCollection(installation=settings)
    for path, change in (
        ("/ci/jobs/collect", {"attachment_id": "x"}),
        ("/ci/jobs/collect", {"collection_id": "-bad"}),
        ("/ci/jobs/collect", {"attachment_id": "0" * 64}),
        ("/ci/jobs/collect", {"extra": 1}),
        ("/ci/jobs/inspect", {}),
        ("/ci/jobs/other", {}),
    ):
        assert handler.execute(path=path, payload=payload | change)["status"] == "refused"
    inspected = {"repository": "owner/repo"}
    for attachment_id in ("x", "0" * 64):
        result = handler.execute(
            path="/ci/jobs/inspect", payload=inspected | {"attachment_id": attachment_id}
        )
        assert result["status"] == "refused"


def test_history_preserves_pending_terminal_and_late_unavailable(attached, monkeypatch):
    records = attached.records
    conclude(records, job=("in_progress", None), check=("in_progress", None))
    assert collect(attached, "c1")[1]["observation"]["status"] == "pending"
    conclude(records)
    assert collect(attached, "c2")[1]["observation"]["status"] == "successful"
    monkeypatch.setattr(ForgeReads, "installed", classmethod(lambda _cls, **_: lambda _path: None))
    assert collect(attached, "c3")[1]["observation"]["status"] == "unavailable"
    conclude(records, job=("in_progress", None), check=("in_progress", None))
    history = inspect(attached)[1]["observations"]
    assert [row["status"] for row in history] == ["pending", "successful", "unavailable"]
    assert [row["sequence"] for row in history] == [1, 2, 3]


def test_contradictory_terminal_observation_is_explicit_conflict(attached):
    conclude(attached.records)
    assert collect(attached, "c1")[1]["observation"]["status"] == "successful"
    conclude(attached.records, job=("completed", "failure"), check=("completed", "failure"))
    observation = collect(attached, "c2")[1]["observation"]
    assert observation["status"] == "conflict"
    assert observation["facts"]["snapshot_status"] == "failed"
    assert [row["status"] for row in inspect(attached)[1]["observations"]] == [
        "successful",
        "conflict",
    ]


def test_collection_survives_policy_loss_token_expiry_and_arm_replacement(attached, monkeypatch):
    conclude(attached.records)
    attached.application.installation.ci_identity_policy = None
    monkeypatch.setattr(time, "time", lambda: 1800000000)
    edge_tests.rearm(attached.application)
    result = collect(attached, "after")[1]
    assert result["observation"]["status"] == "successful"
    assert result["observation"]["observed_at"] == 1800000000


def test_collection_id_conflict_capacity_and_attachment_change(attached, monkeypatch):
    conclude(attached.records)
    collect(attached, "c1")
    other = attached.receipt["attachment_id"][::-1]
    reused = collect(attached, "c1", attachment_id=other)[1]
    assert reused["reason"] == "collection identity conflicts with another attachment"
    monkeypatch.setattr(collection_module, "_MAX_OBSERVATIONS", 1)
    assert collect(attached, "c2")[1]["reason"] == (
        "CI observation history full; nothing was pruned"
    )
    monkeypatch.setattr(collection_module, "_MAX_OBSERVATIONS", 256)
    original = collection_module.observe_retained_job

    def removed(**kwargs):
        result = original(**kwargs)
        mutate(
            attached.application,
            lambda record: record.update(
                ci_job_attachments={"schema": 1, "attachments": {}, "collections": {}}
            ),
        )
        return result

    monkeypatch.setattr(collection_module, "observe_retained_job", removed)
    assert collect(attached, "c3")[1]["reason"] == "retained CI job attachment changed"


def test_malformed_subtree_refuses_collection_and_inspection(attached):
    mutate(attached.application, lambda record: record.update(ci_job_attachments={"schema": 2}))
    assert collect(attached, "c1")[1]["reason"] == "CI job attachment state unavailable"
    assert inspect(attached)[1]["status"] == "refused"


@pytest.fixture
def blocked(attached, monkeypatch):
    conclude(attached.records)
    gate, entered = threading.Event(), threading.Semaphore(0)
    original = attached.read

    def slow(path):
        if path == history_tests.CHECK:
            entered.release()
            assert gate.wait(timeout=30)
        return original(path)

    monkeypatch.setattr(ForgeReads, "installed", classmethod(lambda _cls, **_: slow))
    return attached, gate, entered


def test_recovery_and_existing_routes_progress_while_collection_io_blocks(blocked):
    attached, gate, entered = blocked
    results = []
    worker = threading.Thread(target=lambda: results.append(collect(attached, "slow")))
    worker.start()
    assert entered.acquire(timeout=30)
    settings = attached.application.installation
    admitted = post(attached.application, "/admitted", vars(attached.query), settings.query_secret)
    assert admitted[1]["status"] == "admitted"
    assert edge_tests.attach(attached.application, attached.query, attached.token) == (
        attached.receipt
    )
    edge_tests.rearm(attached.application)
    rearmed = stored(attached.application)["observer_arm_id"]
    gate.set()
    worker.join(timeout=30)
    assert results[0][1]["observation"]["status"] == "successful"
    assert stored(attached.application)["observer_arm_id"] == rearmed


def test_concurrent_identical_collections_commit_once(blocked):
    attached, gate, entered = blocked
    results = []
    workers = [
        threading.Thread(target=lambda: results.append(collect(attached, "same"))) for _ in range(2)
    ]
    for worker in workers:
        worker.start()
    assert entered.acquire(timeout=30) and entered.acquire(timeout=30)
    gate.set()
    for worker in workers:
        worker.join(timeout=30)
    assert len(results) == 2 and results[0] == results[1]
    assert inspect(attached)[1]["observation_count"] == 1
