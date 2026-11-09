"""The controller collects a reverted incident's original run with no operator command."""

import json
import sys
import time
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import Mock

import pytest

from livespec_dev_tooling import incident_observer_service as service
from livespec_dev_tooling import incident_original_run_watch as watch
from livespec_dev_tooling._incident_observer_store import (
    load_record,
    read_registration,
    repository_lock,
    save_record,
)
from livespec_dev_tooling.incident_observer import recovery_action_id
from livespec_dev_tooling.incident_original_run_flows import EntryPorts
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


def in_progress(world: World) -> None:
    world.read.return_value = flows.run(
        world,
        "in_progress",
        flows.job("test", "failure", 2),
        flows.job("late-leg", None, 5, "in_progress"),
    )


def test_an_unfinished_original_run_is_retried_until_terminal_then_recorded_once(
    world: World,
) -> None:
    record_action(world, status="completed", receipt="published-revert")
    _ = land_revert(world)
    in_progress(world)
    early = [tick(world), tick(world)]
    world.read.return_value = flows.run(world, "completed", *flows.FINAL)
    finished = tick(world)
    after = [tick(world), tick(world)]
    assert [t.status for t in early] == ["waiting", "waiting"]
    assert "in-progress" in early[0].detail
    assert world.comments != [] and len(world.comments) == 1
    assert finished.status == "collected"
    assert [t.status for t in after] == ["done", "done"]
    assert len(world.comments) == 1
    assert world.read.call_count == 3


def test_a_revert_the_branch_does_not_carry_yet_keeps_waiting(world: World) -> None:
    record_action(world, status="completed", receipt="published-revert")
    sha = commit(world.repo, {"elsewhere": "x\n"}, "master moves on again")
    _ = git(world.repo, "update-ref", "refs/remotes/origin/master", sha)
    result = tick(world)
    assert (result.status, "revert" in result.detail) == ("waiting", True)
    world.read.assert_not_called()


def test_a_restart_during_collection_resumes_it_and_leaves_one_record(world: World) -> None:
    record_action(world, status="completed", receipt="published-revert")
    _ = land_revert(world)
    healthy = world.ports()
    outage = replace(
        healthy,
        canonical=replace(healthy.canonical, ledger=Mock(side_effect=OSError("tenant down"))),
    )
    interrupted = watch_once(state_dir=world.state, repository=REPOSITORY, ports=outage)
    assert interrupted.status == "refused"
    assert world.comments == []
    assert len(stored(world)) == 2
    resumed = tick(world)
    again = tick(world)
    assert (resumed.status, again.status) == ("collected", "done")
    assert len(world.comments) == 1
    assert len(stored(world)) == 2


def watcher(world: World, *, ports: object = None) -> Any:
    factory = ports if ports is not None else world.ports
    return watch.OriginalRunWatcher(
        state_dir=world.state,
        repository=REPOSITORY,
        ports=cast("Callable[[], EntryPorts | None]", factory),
        interval_seconds=0.0,
    )


def test_the_watcher_builds_ports_only_when_a_collection_is_owed(world: World) -> None:
    factory = Mock(side_effect=world.ports)
    idle = watcher(world, ports=factory).tick()
    record_action(world, status="completed", receipt="published-revert")
    _ = land_revert(world)
    first = watcher(world, ports=factory).tick()
    done = watcher(world, ports=factory).tick()
    assert (idle.status, first.status, done.status) == ("idle", "collected", "idle")
    factory.assert_called_once_with()


def test_a_missing_credential_waits_instead_of_collecting(world: World) -> None:
    record_action(world, status="completed", receipt="published-revert")
    _ = land_revert(world)
    result = watcher(world, ports=lambda: None).tick()
    assert (result.status, "credential" in result.detail) == ("waiting", True)
    world.read.assert_not_called()


def test_the_started_watcher_collects_in_the_background_and_survives_a_failed_tick(
    world: World,
) -> None:
    record_action(world, status="completed", receipt="published-revert")
    _ = land_revert(world)
    calls: list[int] = []

    def flaky() -> EntryPorts:
        calls.append(1)
        if len(calls) == 1:
            raise OSError("reference clone unavailable")
        return world.ports()

    running = watcher(world, ports=flaky)
    thread = running.start()
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline and not world.comments:
        time.sleep(0.01)
    running.stop.set()
    thread.join(timeout=30)
    assert (thread.daemon, thread.is_alive()) == (True, False)
    assert len(world.comments) == 1
    assert len(calls) >= 2


def test_the_installed_watcher_binds_the_installation_and_the_service_starts_it(
    world: World, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    settings = SimpleNamespace(state=world.state, repository=REPOSITORY, repo=world.repo)
    bound = Mock(return_value=world.ports())
    monkeypatch.setattr(watch, "bound_ports", bound)
    installed = watch.installed_watcher(installation=cast("Any", settings))
    assert (installed.state_dir, installed.repository) == (world.state, REPOSITORY)
    assert installed.interval_seconds == 60.0
    record_action(world, status="completed", receipt="published-revert")
    _ = land_revert(world)
    assert installed.tick().status == "collected"
    bound.assert_called_once_with(installation=settings)

    started = Mock()
    monkeypatch.setattr(service, "installed_watcher", Mock(return_value=started))
    application = SimpleNamespace(installation=settings)
    monkeypatch.setattr(sys, "argv", ["observer-service", "--config", str(tmp_path)])
    monkeypatch.setattr(service.sys, "flags", SimpleNamespace(isolated=1))
    monkeypatch.setattr(service.ControllerService, "installed", lambda **_: application)
    order: list[str] = []
    started.start.side_effect = lambda: order.append("watcher")

    class Server:
        def __enter__(self) -> "Server":
            return self

        def __exit__(self, *_: object) -> bool:
            return False

        def serve_forever(self) -> None:
            order.append("serve")

    settings.port = 8765
    monkeypatch.setattr(service, "make_server", lambda *_a, **_k: Server())
    assert service.main() == 0
    assert order == ["watcher", "serve"]
