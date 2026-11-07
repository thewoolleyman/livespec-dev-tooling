"""POST /reconcile refuses anything but one exact retained action and its current fence."""

from __future__ import annotations

import io
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

from livespec_dev_tooling import incident_observer_reconcile as reconcile
from livespec_dev_tooling._incident_observer_store import (
    load_record,
    repository_lock,
    save_record,
)
from livespec_dev_tooling.incident_observer_reconcile import ObserverReconcile
from livespec_dev_tooling.incident_observer_service import ControllerService
from tests.livespec_dev_tooling import test_incident_recovery_principal as principal_tests
from tests.livespec_dev_tooling.test_incident_recovery_principal import REPOSITORY, World

world = principal_tests.world

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-gho3w4


def _payload(*, world: World, **changes: object) -> dict[str, Any]:
    return {
        "repository": REPOSITORY,
        "action_id": world.intent.action_id,
        "retry_publish": False,
        **changes,
    }


def _execute(*, world: World, **changes: object) -> dict[str, Any]:
    return ObserverReconcile(installation=world.installation).execute(
        path="/reconcile", payload=_payload(world=world, **changes)
    )


def _edit(*, world: World, change: Any) -> None:
    settings = world.installation
    with repository_lock(directory=settings.state, repository=REPOSITORY) as path:
        record = load_record(path=path)
        change(record)
        save_record(path=path, record=record)


def _status(*, world: World) -> str:
    return json.loads(Path(world.record).read_text())["actions"][world.intent.action_id]["status"]


@pytest.mark.parametrize(
    "changes",
    [
        {"action_id": "short"},
        {"action_id": 7},
        {"retry_publish": "true"},
        {"retry_publish": 1},
        {"receipt": "caller-chosen"},
    ],
)
def test_a_malformed_request_or_a_caller_receipt_refuses(world: World, changes: object) -> None:
    reply = _execute(world=world, **changes)
    assert reply == {
        "status": "refused",
        "reason": "exact repository, action_id and retry_publish required",
    }
    assert _status(world=world) == "pending"


def test_the_query_credential_cannot_reconcile(world: World) -> None:
    application = ControllerService(installation=world.installation, recover=Mock())
    body = json.dumps(_payload(world=world)).encode()
    statuses: list[str] = []
    environ = {
        "PATH_INFO": "/reconcile",
        "REQUEST_METHOD": "POST",
        "CONTENT_LENGTH": str(len(body)),
        "HTTP_AUTHORIZATION": "Bearer " + world.installation.query_secret.decode(),
        "wsgi.input": io.BytesIO(body),
    }
    _ = b"".join(application(environ, lambda status, _headers: statuses.append(status)))
    assert statuses == ["403 Forbidden"]
    assert _status(world=world) == "pending"


def test_an_unknown_action_refuses(world: World) -> None:
    reply = _execute(world=world, action_id="f" * 64)
    assert reply["reason"] == "unknown exact action receipt"


@pytest.mark.parametrize("registration", [None, "other-operation"])
def test_an_action_whose_authority_is_not_its_own_refuses(world: World, registration: Any) -> None:
    def tamper(record: dict[str, Any]) -> None:
        action = record["actions"][world.intent.action_id]
        if registration is None:
            del action["registration"]
        else:
            action["registration"]["operation_id"] = registration

    _edit(world=world, change=tamper)
    assert _execute(world=world)["reason"] == "missing immutable action authority"


def test_no_receipt_leaves_the_action_pending_and_no_publication(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    world.client(monkeypatch)
    reply = _execute(world=world)
    assert reply["status"] == "pending"
    assert reply["action_id"] == world.intent.action_id
    assert _status(world=world) == "pending"
    assert world.forge.count("POST", "git/commits") == 0


def test_an_unobservable_lookup_is_no_receipt_not_a_failure(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    forge = Mock()
    forge.read_exact_receipt.side_effect = OSError("reserved")
    monkeypatch.setattr(reconcile, "ProcessInverseForge", Mock(return_value=forge))
    assert _execute(world=world)["status"] == "pending"


def test_a_retry_with_no_landed_effect_starts_exactly_one_revert(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    world.client(monkeypatch)
    reply = _execute(world=world, retry_publish=True)
    assert reply["status"] == "completed", reply
    assert _status(world=world) == "completed"
    assert len(world.reverts()) == 1


def test_a_retry_the_principal_cannot_finish_stays_pending(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    world.client(monkeypatch, connect=principal_tests.no_app)
    reply = _execute(world=world, retry_publish=True)
    assert reply["status"] == "pending"
    assert _status(world=world) == "pending"
    assert world.reverts() == []


def test_a_retry_refuses_once_the_registration_is_no_longer_the_actions(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    world.client(monkeypatch)
    _edit(world=world, change=lambda record: record.update(registration=None))
    reply = _execute(world=world, retry_publish=True)
    assert reply["reason"] == "incident registration changed before the retry"
    assert _status(world=world) == "pending"
    assert world.reverts() == []


def test_a_regression_caused_action_keeps_its_cause_and_no_completion(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    regression = {
        "attempt_id": "recovery-1",
        "operation_id": "recovery-1#reverting",
        "generation": 9,
        "owner": "controller",
        "receipt_digest": "a" * 64,
    }

    def reopened(record: dict[str, Any]) -> None:
        record["actions"][world.intent.action_id].update(completion=None, regression=regression)

    _edit(world=world, change=reopened)
    forge = Mock()
    forge.read_exact_receipt.return_value = "exact-receipt"
    monkeypatch.setattr(reconcile, "ProcessInverseForge", Mock(return_value=forge))
    assert _execute(world=world)["receipt"] == "exact-receipt"
    intent = forge.read_exact_receipt.call_args.kwargs["intent"]
    assert intent.completion is None
    assert asdict(intent.regression) == regression
