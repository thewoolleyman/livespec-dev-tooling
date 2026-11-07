"""POST /reconcile resolves an unknown recovery outcome with exactly one revert commit."""

from __future__ import annotations

import io
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

from livespec_dev_tooling.incident_observer_service import ControllerService
from tests.livespec_dev_tooling import test_incident_recovery_principal as principal_tests
from tests.livespec_dev_tooling.test_incident_recovery_principal import REPOSITORY, World

# The real principal, its publication ledger, a forge and a reference clone.
world = principal_tests.world

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-gho3w4


def _post(*, world: World, retry: bool) -> tuple[str, dict[str, Any]]:
    application = ControllerService(installation=world.installation, recover=Mock())
    body = json.dumps(
        {"repository": REPOSITORY, "action_id": world.intent.action_id, "retry_publish": retry}
    ).encode()
    statuses: list[str] = []
    secret = world.installation.control_secret.decode()
    environ = {
        "PATH_INFO": "/reconcile",
        "REQUEST_METHOD": "POST",
        "CONTENT_LENGTH": str(len(body)),
        "HTTP_AUTHORIZATION": "Bearer " + secret,
        "wsgi.input": io.BytesIO(body),
    }
    reply = b"".join(application(environ, lambda status, _headers: statuses.append(status)))
    return statuses[0], json.loads(reply)


def _action(*, world: World) -> dict[str, Any]:
    return json.loads(Path(world.record).read_text())["actions"][world.intent.action_id]


def test_an_unobserved_ref_update_is_retried_as_its_one_recorded_commit(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    world.client(monkeypatch)
    world.forge.hooks[("PATCH", "master")] = principal_tests.raise_oserror
    request = {
        "request": asdict(principal_tests.publish_request(world, principal_tests.plan_for(world)))
    }
    _ = world.call("publish", request)
    _, cleared = _post(world=world, retry=False)
    still_pending = _action(world=world)["status"]
    moved_early = world.forge.master() != world.merge
    status, retried = _post(world=world, retry=True)
    _, repeated = _post(world=world, retry=False)
    facts = (
        cleared["status"] == "pending",
        still_pending == "pending",
        not moved_early,
        status == "202 Accepted",
        retried["status"] == "completed",
        repeated["receipt"] == retried["receipt"] == _action(world=world)["receipt"],
        _action(world=world)["status"] == "completed",
        world.forge.count("POST", "git/commits") == 1,
        len(world.reverts()) == 1,
    )
    assert all(facts), (cleared, retried, repeated, facts)


def test_a_lost_reply_is_cleared_by_its_exact_receipt_with_no_retry(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    world.client(monkeypatch)
    world.forge.lost_patch_reply = True
    request = {
        "request": asdict(principal_tests.publish_request(world, principal_tests.plan_for(world)))
    }
    _ = world.call("publish", request)
    world.forge.lost_patch_reply = False
    status, cleared = _post(world=world, retry=False)
    facts = (
        status == "202 Accepted",
        cleared["status"] == "completed",
        cleared["receipt"] == _action(world=world)["receipt"],
        world.forge.count("POST", "git/commits") == 1,
        len(world.reverts()) == 1,
    )
    assert all(facts), (cleared, facts)
