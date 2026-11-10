"""The publication's back-off, terminal state and revalidation, on the real observer state.

The end-to-end paths (a conflict written outside the fence, landing once, backing off
through an outage) are in `test_incident_conflict_chain.py`; these pin the outcome
bookkeeping itself.
"""

from __future__ import annotations

import json

from livespec_dev_tooling._incident_conflict_generation import ChainWrite
from livespec_dev_tooling.incident_conflict_publication import (
    ConflictPublication,
    backoff_seconds,
    is_due,
    record_outcome,
)
from tests.livespec_dev_tooling import test_incident_conflict_chain as chain_tests
from tests.livespec_dev_tooling.test_incident_conflict_chain import (
    REPOSITORY,
    Clock,
    _journal,
    _settle,
    failing,
)

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-fdquen

world = chain_tests.world
__all__ = ["failing", "world"]


def _action(world):
    return json.loads(world.record.read_text())["actions"][world.intent.action_id]


def _outcome(world, *, receipt, outcome, clock):
    return record_outcome(
        state=world.installation.state,
        repository=REPOSITORY,
        action_id=world.intent.action_id,
        receipt=receipt,
        outcome=outcome,
        clock=clock,
    )


def _deferred_conflict(failing, monkeypatch):
    """A journaled conflict whose first write met an unavailable tenant."""
    world, chain = failing
    _journal(world, chain, monkeypatch)
    chain.down(down=True)
    assert "deferred" in _settle(world, automatic=True).reason
    return world, chain


def test_back_off_and_due_time_follow_the_attempt_count():
    assert backoff_seconds(attempts=0) == 300
    assert backoff_seconds(attempts=6) == 3600
    assert not is_due(action={"sweep": {"terminal": "half-reopen: x", "next_at": 0.0}}, now=1.0)


def test_a_lookup_that_found_no_receipt_backs_off_the_unsettled_action(failing):
    world, _ = failing
    clock = Clock()
    published = _outcome(
        world, receipt=None, outcome=ChainWrite.retry(reason="receipt-unavailable"), clock=clock
    )
    state = _action(world)["sweep"]
    assert published.status == "deferred" and published.reason == "receipt-unavailable"
    assert (state["attempts"], state["next_at"], state["last"]) == (
        1,
        clock.now + 300,
        "receipt-unavailable",
    )


def test_a_terminal_outcome_is_journaled_once_and_kept_against_a_later_retry(failing, monkeypatch):
    world, chain = _deferred_conflict(failing, monkeypatch)
    receipt = _action(world)["receipt"]
    clock = Clock()
    first = _outcome(
        world, receipt=receipt, outcome=ChainWrite.terminal(reason="superseded: x"), clock=clock
    )
    later = _outcome(
        world, receipt=receipt, outcome=ChainWrite.retry(reason="tenant-unavailable"), clock=clock
    )
    state = _action(world)["sweep"]
    assert (first.status, later.status, later.reason) == ("terminal", "terminal", "superseded: x")
    assert state["terminal"] == "superseded: x" and state["attempts"] == 2
    assert not _action(world).get("reconciled")
    chain.down(down=False)
    publication = ConflictPublication(
        state=world.installation.state, repository=REPOSITORY, chain=chain.writer, clock=clock
    )
    calls = len(chain.calls())
    replay = publication.publish(intent=world.intent, receipt=receipt, automatic=False)
    assert replay.status == "terminal" and len(chain.calls()) == calls


def test_a_landed_outcome_marks_the_action_reconciled(failing, monkeypatch):
    world, _ = _deferred_conflict(failing, monkeypatch)
    receipt = _action(world)["receipt"]
    landed = _outcome(world, receipt=receipt, outcome=ChainWrite.landed(), clock=Clock())
    assert landed.status == "reconciled" and _action(world)["reconciled"] is True
