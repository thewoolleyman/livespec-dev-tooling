"""A reconciled action stops refusing /arm, and a repeat answers without the principal."""

from __future__ import annotations

import json
from dataclasses import asdict, replace
from typing import Any
from unittest.mock import Mock

import pytest

from livespec_dev_tooling import incident_inverse_service as client_service
from livespec_dev_tooling._incident_observer_types import ObserverResult
from livespec_dev_tooling.incident_observer_admission import arm_before_merge
from livespec_dev_tooling.incident_observer_reconcile import ObserverReconcile
from tests.livespec_dev_tooling import test_incident_recovery_principal as principal_tests
from tests.livespec_dev_tooling.test_incident_recovery_principal import REPOSITORY, World

# The real principal, its publication ledger, a forge and a reference clone.
world = principal_tests.world

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-gho3w4


def _arm_another_incident(*, world: World, expected: str) -> ObserverResult:
    arm = replace(world.intent.observer_arm, incident_item_id="incident-2", generation=1)
    return arm_before_merge(
        directory=world.installation.state,
        arm=arm,
        expected_arm_id=expected,
        authorize_current=Mock(return_value=True),
        released_controller=Mock(return_value=True),
    )


def _reconcile(*, world: World) -> dict[str, Any]:
    payload = {
        "repository": REPOSITORY,
        "action_id": world.intent.action_id,
        "retry_publish": False,
    }
    return ObserverReconcile(installation=world.installation).execute(
        path="/reconcile", payload=payload
    )


def test_a_cleared_action_stops_refusing_arm_and_a_repeat_calls_no_principal(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    world.client(monkeypatch)
    expected = json.loads(world.record.read_text())["observer_arm_id"]
    before = _arm_another_incident(world=world, expected=expected)
    world.forge.lost_patch_reply = True
    plan = principal_tests.plan_for(world)
    _ = world.call("publish", {"request": asdict(principal_tests.publish_request(world, plan))})
    world.forge.lost_patch_reply = False
    cleared = _reconcile(world=world)
    lookup = Mock(side_effect=AssertionError("a completed action asked the principal"))
    monkeypatch.setattr(client_service.ProcessInverseForge, "read_exact_receipt", lookup)
    repeat = _reconcile(world=world)
    after = _arm_another_incident(world=world, expected=expected)
    assert (before.status, before.reason) == (
        "refused",
        "prior recovery effect requires exact receipt before correction",
    )
    assert cleared["status"] == "completed"
    assert repeat["status"] == "completed"
    assert repeat["receipt"] == cleared["receipt"]
    assert lookup.call_count == 0
    assert after.status == "armed", after
