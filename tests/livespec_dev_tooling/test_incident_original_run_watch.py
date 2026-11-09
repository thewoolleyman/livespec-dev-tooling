"""The controller collects a reverted incident's original run with no operator command."""

import json
from pathlib import Path
from typing import cast

import pytest

from livespec_dev_tooling._incident_observer_store import (
    load_record,
    read_registration,
    repository_lock,
    save_record,
)
from livespec_dev_tooling.incident_observer import recovery_action_id
from livespec_dev_tooling.incident_original_run_watch import WatchTick, watch_once
from tests.livespec_dev_tooling import test_incident_original_run_flows as flows
from tests.livespec_dev_tooling.test_incident_original_run_flows import (
    REPOSITORY,
    World,
    commit,
    git,
    stored,
)

# The shared reverted-incident fixture: a real repository, controller state and ports.
world = flows.world


def action_id(world: World) -> str:
    with repository_lock(directory=world.state, repository=REPOSITORY) as path:
        registration = read_registration(record=load_record(path=path))
    assert registration is not None
    return recovery_action_id(registration=registration)


def record_action(world: World, *, status: str, receipt: str | None) -> None:
    identity = action_id(world)
    with repository_lock(directory=world.state, repository=REPOSITORY) as path:
        record = load_record(path=path)
        actions = cast("dict[str, object]", record.setdefault("actions", {}))
        actions[identity] = {"status": status, "receipt": receipt}
        save_record(path=path, record=record)


def land_revert(world: World) -> str:
    """The controller's inverse commit, as the recovery principal publishes it."""
    message = f"Revert complete incident PR #12\n\nIncident-Action: {action_id(world)}\n"
    sha = commit(world.repo, {"reverted": "again\n"}, message)
    _ = git(world.repo, "update-ref", "refs/remotes/origin/master", sha)
    return sha


def tick(world: World) -> WatchTick:
    return watch_once(state_dir=world.state, repository=REPOSITORY, ports=world.ports())


def test_collects_without_an_operator_command_once_the_revert_has_landed(world: World) -> None:
    record_action(world, status="completed", receipt="published-revert")
    revert = land_revert(world)
    result = tick(world)
    assert result.status == "collected"
    assert len(world.comments) == 1
    body = json.loads(world.comments[0]["text"].split("\n", 1)[1])
    assert (body["run_id"], body["revert_sha"], body["terminal"]) == (42, revert, True)
    retained = list(stored(world).values())
    assert [row["original"]["revert_sha"] for row in retained if "original" in row] == [revert]


@pytest.mark.parametrize(
    ("status", "receipt"),
    [("pending", None), ("completed", None), ("completed", "rollback-conflict:abc:owner:o:head:h")],
)
def test_an_attempt_without_a_landed_revert_is_left_alone(
    world: World, status: str, receipt: str | None
) -> None:
    record_action(world, status=status, receipt=receipt)
    _ = land_revert(world)
    assert tick(world).status == "idle"
    world.read.assert_not_called()
    assert world.comments == []


def test_no_recorded_action_is_idle_and_a_revert_not_yet_on_master_waits(world: World) -> None:
    assert tick(world).status == "idle"
    record_action(world, status="completed", receipt="published-revert")
    waiting = tick(world)
    assert (waiting.status, "revert" in waiting.detail) == ("waiting", True)
    world.read.assert_not_called()


def test_an_unregistered_repository_is_idle(world: World, tmp_path: Path) -> None:
    result = watch_once(state_dir=tmp_path, repository=REPOSITORY, ports=world.ports())
    assert result.status == "idle"
