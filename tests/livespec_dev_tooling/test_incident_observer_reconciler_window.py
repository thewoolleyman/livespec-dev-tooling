"""The master-health reconciler's ownership answer covers its whole pass.

Review finding F2 on livespec-dev-tooling#3915: the observer answered
incident-owned only for one exact head SHA and run id, while a reconciler pass
reruns the newest failing run and reverts the culprit at the bottom of the red
episode. An ordinary red run landing after a registered incident commit was
answered `ordinary`, and the reconciler then reverted the incident commit while
the observer was reverting it too. These tests pin the window-keyed answer, the
unresolved-recovery fence and the bounded wait on a busy fence.
"""

from __future__ import annotations

from threading import Event, Thread
from unittest.mock import Mock

import pytest

from livespec_dev_tooling._incident_observer_store import (
    registration_record,
    repository_lock,
    save_record,
)
from livespec_dev_tooling._incident_observer_types import ObserverRegistration
from livespec_dev_tooling.incident_observer import (
    RECONCILER_FENCE_WAIT_SECONDS,
    route_ordinary_action,
    route_reconciler_window,
)

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-ariayn
_REPOSITORY = "owner/repo"
_INCIDENT = "a" * 40
_LATER = "d" * 40


@pytest.fixture
def registration():
    return ObserverRegistration(
        repository=_REPOSITORY,
        incident_item_id="incident-1",
        attempt_id="repair-1",
        operation_id="operation-1",
        generation=1,
        owner="recovery-controller",
        phase="repair",
        head_sha=_INCIDENT,
        run_id=4242,
        required_jobs=("coverage", "lint"),
        controller_release="v1.2.3",
        controller_revision="b" * 40,
        candidate_revision="c" * 40,
        authority_receipt=b"canonical-verified-receipt-1",
    )


def _store(*, directory, record):
    with repository_lock(directory=directory, repository=_REPOSITORY) as path:
        save_record(path=path, record=record)


def _ask(*, directory, window, perform):
    return route_reconciler_window(
        directory=directory,
        repository=_REPOSITORY,
        window_shas=frozenset(window),
        perform=perform,
    )


def test_a_registered_incident_commit_anywhere_in_the_window_owns_the_pass(tmp_path, registration):
    """The F2 race: ordinary run 5000 on a later commit, incident commit below it."""
    _store(
        directory=tmp_path,
        record={"registration": registration_record(registration=registration)},
    )
    perform = Mock(return_value="ordinary-action")

    owned = _ask(directory=tmp_path, window={_LATER, _INCIDENT}, perform=perform)
    outside = _ask(directory=tmp_path, window={_LATER}, perform=perform)

    assert (owned.status, owned.reason) == (
        "incident-owned",
        "independent incident controller owns repository action",
    )
    assert (outside.status, outside.receipt) == ("ordinary", "ordinary-action")
    assert perform.call_count == 1


def test_an_unbound_pre_merge_arm_owns_the_pass_and_a_bound_one_does_not(tmp_path):
    perform = Mock(return_value="ordinary-action")
    _store(directory=tmp_path, record={"observer_arm_id": "f" * 64})
    unbound = _ask(directory=tmp_path, window={_LATER}, perform=perform)
    _store(directory=tmp_path, record={"observer_arm_id": "f" * 64, "observer_arm_bound": True})
    bound = _ask(directory=tmp_path, window={_LATER}, perform=perform)

    assert (unbound.status, unbound.reason) == (
        "incident-owned",
        "pre-merge observer owns repository action",
    )
    assert bound.status == "ordinary"
    assert perform.call_count == 1


def test_a_recovery_with_an_unknown_outcome_owns_every_ordinary_answer(tmp_path, registration):
    """Ownership is keyed on the repository while a recovery effect is unresolved."""
    record = {
        "registration": registration_record(registration=registration),
        "actions": {"action-1": {"status": "pending"}},
    }
    _store(directory=tmp_path, record=record)
    perform = Mock(return_value="ordinary-action")

    window = _ask(directory=tmp_path, window={_LATER}, perform=perform)
    exact = route_ordinary_action(
        directory=tmp_path,
        repository=_REPOSITORY,
        head_sha=_LATER,
        run_id=5000,
        perform=perform,
    )
    reason = "an incident recovery action with an unknown outcome owns repository action"

    assert (window.status, window.reason) == ("incident-owned", reason)
    assert (exact.status, exact.reason) == ("incident-owned", reason)
    assert perform.call_count == 0


def test_a_settled_recovery_returns_the_pass_to_ordinary_policy(tmp_path, registration):
    record = {
        "registration": registration_record(registration=registration),
        "actions": {"action-1": {"status": "completed", "receipt": "revert-sha"}},
    }
    _store(directory=tmp_path, record=record)

    answer = _ask(directory=tmp_path, window={_LATER}, perform=lambda: "ordinary-action")

    assert (answer.status, answer.receipt) == ("ordinary", "ordinary-action")


def test_a_repository_with_no_incident_record_runs_ordinary_policy(tmp_path):
    answer = _ask(directory=tmp_path, window=set(), perform=lambda: "ordinary-action")

    assert (answer.status, answer.reason, answer.receipt) == (
        "ordinary",
        "ordinary reconciler policy retained",
        "ordinary-action",
    )


def test_a_fence_held_past_the_bound_is_the_observer_acting(tmp_path):
    """A busy fence answers incident-owned within the bound, never ordinary."""
    held = Event()
    release = Event()

    def hold():
        with repository_lock(directory=tmp_path, repository=_REPOSITORY):
            held.set()
            _ = release.wait(timeout=30)

    holder = Thread(target=hold)
    holder.start()
    _ = held.wait(timeout=30)
    perform = Mock(return_value="ordinary-action")
    answer = route_reconciler_window(
        directory=tmp_path,
        repository=_REPOSITORY,
        window_shas=frozenset({_LATER}),
        perform=perform,
        wait_seconds=0.2,
    )
    release.set()
    holder.join(timeout=30)

    assert (answer.status, answer.reason) == (
        "incident-owned",
        "repository action fence is held by the incident observer",
    )
    assert perform.call_count == 0
    assert 0 < RECONCILER_FENCE_WAIT_SECONDS <= 60
