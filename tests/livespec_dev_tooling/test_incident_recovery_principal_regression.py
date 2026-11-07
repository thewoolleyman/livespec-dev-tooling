"""A `/recover` regression-caused action reverts the registered attempt's exact landed patch.

`POST /recover` (livespec-dev-tooling-52qsvq) persists the registration's single
action with `completion: None` and a verified `regression` cause, then calls the
same `recover`. The principal derives scope from the registration and its arm,
never from the leaf, so it reverts exactly the landed commits of the attempt
the reopen names, under the same action id a leaf failure would have used.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, replace

from livespec_dev_tooling._incident_observer_store import save_record
from livespec_dev_tooling._incident_observer_types import RegressionReopen
from tests.livespec_dev_tooling.test_incident_recovery_principal import (
    _observer_record,
    git,
)
from tests.livespec_dev_tooling.test_incident_recovery_principal import (
    world as world_fixture,
)

world = world_fixture


def test_regression_reopen_reverts_the_exact_landed_attempt_as_the_recovery_app(world, monkeypatch):
    registration = world.intent.registration
    regression = RegressionReopen(
        attempt_id=registration.attempt_id,
        operation_id=registration.operation_id,
        generation=registration.generation + 1,
        owner=registration.owner,
        receipt_digest=hashlib.sha256(b"verified reverting generation").hexdigest(),
    )
    record = _observer_record(world.intent)
    world.intent = replace(world.intent, completion=None, regression=regression)
    action = record["actions"][world.intent.action_id]
    action.update(completion=None, regression=asdict(regression))
    save_record(path=world.record, record=record)
    incident_head = world.forge.master()
    outcome = world.recovered(monkeypatch)
    head = world.forge.master()
    facts = (
        outcome.status == "reverted",
        outcome.receipt == f"recovery-inverse:{world.intent.action_id}:commit:{head}",
        git(world.bare, "rev-parse", head + "^") == incident_head,
        git(world.bare, "rev-parse", head + "^{tree}")
        == git(world.bare, "rev-parse", world.before + "^{tree}"),
        len(world.reverts()) == 1,
        world.forge.count("PATCH", "git/refs/heads/master") == 1,
    )
    assert all(facts), facts
