"""The merge of an armed attempt is recorded one generation after the arm.

`/bind` fulfils a pre-merge grant without a fresh canonical read, so a registration
keeps the arm's generation, whose attempt has nothing landed yet. The canonical
`record-merge` action records the landed commits on the next generation, and that
is the record `collect` authenticates the original run against.
"""

from collections.abc import Mapping
from dataclasses import replace
from typing import Any

import pytest

from livespec_dev_tooling._incident_observer_store import (
    load_record,
    read_registration,
    registration_record,
    repository_lock,
    save_record,
)
from livespec_dev_tooling._incident_run_types import CanonicalRefusalError, RunEvidence
from livespec_dev_tooling.incident_original_run_flows import EvidenceRefusal
from tests.livespec_dev_tooling import test_incident_original_run_flows as flows
from tests.livespec_dev_tooling.test_incident_original_run_flows import REPOSITORY, World, attempt

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-3rsnqb
world = flows.world
_ARM_GENERATION = 3
_HEAD = "b" * 40


def _arm_registration(world: World) -> None:
    """The registration `/bind` retains: the arm's phase and generation, never a later one."""
    with repository_lock(directory=world.state, repository=REPOSITORY) as path:
        record = load_record(path=path)
        registration = read_registration(record=record)
        assert registration is not None
        armed = replace(registration, phase="repair", generation=_ARM_GENERATION)
        record["registration"] = registration_record(registration=armed)
        save_record(path=path, record=record)


def _chain(world: World, **merged: object) -> Any:
    """The real chain's two generations, read by their exact identities."""

    def read(action: str, query: Mapping[str, object], _payload: Mapping[str, str]) -> Any:
        assert action == "read-history"
        common = {"generation": query["generation"], "head": _HEAD}
        if query["generation"] == _ARM_GENERATION:
            return attempt(world, landed_commits=[], **common)
        assert query["phase"] == "master-observation"
        assert query["operation"] == "attempt-1#master-observation"
        assert query["generation"] == _ARM_GENERATION + 1
        return attempt(world, **{**common, **merged})

    return read


def _refusal(result: object) -> str:
    assert isinstance(result, EvidenceRefusal), result
    return result.code


def test_collect_authenticates_the_merge_on_the_generation_after_the_arm(world: World) -> None:
    _arm_registration(world)
    world.authority.side_effect = _chain(world)
    collected = flows.gather(world)
    assert isinstance(collected, RunEvidence), collected
    assert collected.original.generation == _ARM_GENERATION
    assert collected.original.merge_sha == world.shas["merge"]


@pytest.mark.parametrize(
    "merged",
    [
        {"attempt_id": "attempt-2"},
        {"owner": "someone-else"},
        {"pr_number": 13},
        {"head": "c" * 40},
        {"landed_commits": []},
        {"landed_commits": ["f" * 40]},
    ],
)
def test_collect_refuses_a_next_generation_naming_anything_else(
    world: World, merged: dict[str, object]
) -> None:
    _arm_registration(world)
    world.authority.side_effect = _chain(world, **merged)
    code = _refusal(flows.gather(world))
    assert code == "incident-original-run-refused"
    assert world.comments == []


def test_collect_refuses_when_the_merge_was_never_recorded(world: World) -> None:
    _arm_registration(world)
    arm = _chain(world)

    def read(action: str, query: Mapping[str, object], payload: Mapping[str, str]) -> Any:
        if query["generation"] != _ARM_GENERATION:
            raise CanonicalRefusalError(code="incident-authority-identity-mismatch", detail="none")
        return arm(action, query, payload)

    world.authority.side_effect = read
    assert _refusal(flows.gather(world)) == "incident-authority-identity-mismatch"
    assert world.comments == []


def test_collect_refuses_a_next_generation_with_no_attempt(world: World) -> None:
    _arm_registration(world)
    arm = _chain(world)

    def read(action: str, query: Mapping[str, object], payload: Mapping[str, str]) -> Any:
        return arm(action, query, payload) if query["generation"] == _ARM_GENERATION else {}

    world.authority.side_effect = read
    assert _refusal(flows.gather(world)) == "incident-original-run-refused"


def test_a_registration_whose_own_generation_names_the_merge_needs_one_read(world: World) -> None:
    collected = flows.gather(world)
    assert isinstance(collected, RunEvidence), collected
    reads = [call for call in world.authority.call_args_list if call.args[0] == "read-history"]
    # One for the pull request number, one for the authorization.
    assert len(reads) == 2


def test_collect_refuses_an_arm_generation_naming_another_owner(world: World) -> None:
    _arm_registration(world)
    world.authority.side_effect = lambda *_: attempt(world, owner="someone-else")
    assert _refusal(flows.gather(world)) == "incident-original-run-refused"
    assert world.comments == []
