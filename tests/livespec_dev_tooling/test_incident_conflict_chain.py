"""A journaled rollback-conflict reaches the canonical incident chain exactly once.

The reader in these tests is a real child process standing in for the installed
`incident_authority.py`: it keeps one transition per distinct payload, the way the
orchestrator's `record-rollback-conflict` recovers an exact retry, and it can be
taken down to model an unavailable tenant. The recovery principal, its journal and a
reference clone are the real ones from the recovery-principal tests.
"""

from __future__ import annotations

import io
import json
import sys
import textwrap
from dataclasses import replace
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import pytest
from returns.pipeline import is_successful
from returns.unsafe import unsafe_perform_io

import livespec_dev_tooling.incident_observer_service as service
from livespec_dev_tooling._incident_observer_store import repository_lock
from livespec_dev_tooling._incident_observer_types import (
    ObserverRegistration,
    RecoveryIntent,
    RegressionReopen,
)
from livespec_dev_tooling.incident_conflict_chain import ConflictChain
from livespec_dev_tooling.incident_inverse import (
    observer_inverse_callback,
    recover_incident_inverse,
)
from livespec_dev_tooling.incident_observer_service import ControllerService
from tests.livespec_dev_tooling import test_incident_observer_control as control_tests
from tests.livespec_dev_tooling import test_incident_recovery_principal as principal_tests
from tests.livespec_dev_tooling.test_incident_recovery_principal import REPOSITORY, World

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-fdquen

# The real principal, its publication ledger, a forge and a reference clone.
world = principal_tests.world
controller = control_tests.controller

_RECEIPT = "rollback-conflict:exact-action-1:owner:controller-owner:head:" + "a" * 40

_READER = textwrap.dedent(
    """
    import json, sys, time
    from pathlib import Path

    here = Path(sys.argv[0]).parent
    argv = sys.argv[1:]
    action, flags = argv[0], dict(zip(argv[1::2], argv[2::2]))
    mode = (here / "mode").read_text() if (here / "mode").exists() else "up"
    if mode == "down":
        sys.exit(1)
    if mode == "hang":
        time.sleep(30)
    if mode == "garbage":
        print("not json")
        sys.exit(0)
    with (here / "calls.jsonl").open("a") as calls:
        calls.write(json.dumps({"action": action, **flags}) + "\\n")
    if action != "record-rollback-conflict" or flags["--phase"] != "reverting":
        print(json.dumps({"schema": 1, "status": "refused", "authorizes_current_effects": False,
                          "normal_factory_proof": False,
                          "result": {"code": "incident-rollback-conflict-not-eligible",
                                     "detail": flags["--phase"]}}))
        sys.exit(78)
    state = here / "transitions.json"
    seen = json.loads(state.read_text()) if state.exists() else []
    if flags["--rollback-conflict-json"] not in seen:
        seen.append(flags["--rollback-conflict-json"])
        state.write_text(json.dumps(seen))
    phase = "reverting" if mode == "stalled" else "rollback-conflict"
    print(json.dumps({
        "schema": 1, "status": "verified", "authorizes_current_effects": False,
        "normal_factory_proof": False,
        "result": {"operation_id": "op", "lifecycle_state": "blocked",
                   "reading": {"attempt": {
                       "repository": flags["--repository"], "item_id": flags["--item"],
                       "phase": phase, "generation": int(flags["--generation"]) + 1,
                       "owner": flags["--owner"]}}},
    }))
    """
)


def _intent(*, regression=None, phase="reverting"):
    registration = ObserverRegistration(
        repository="owner/repo",
        incident_item_id="incident-1",
        attempt_id="attempt-1",
        operation_id="operation-1",
        generation=2,
        owner="controller-owner",
        phase=phase,
        head_sha="b" * 40,
        run_id=81,
        required_jobs=("tests",),
        controller_release="v1.2.3",
        controller_revision="f" * 40,
        candidate_revision="c" * 40,
        authority_receipt=b"canonical receipt",
    )
    return RecoveryIntent(
        action_id="exact-action-1", registration=registration, regression=regression
    )


@pytest.fixture
def reader(tmp_path):
    script = tmp_path / "reader.py"
    script.write_text(_READER)
    chain = ConflictChain(command=(sys.executable, str(script)), repo=tmp_path, timeout_seconds=2)

    class Reader:
        def __init__(self):
            self.chain = chain

        def mode(self, value):
            (tmp_path / "mode").write_text(value)

        def calls(self):
            path = tmp_path / "calls.jsonl"
            return (
                [json.loads(line) for line in path.read_text().splitlines()]
                if path.exists()
                else []
            )

        def transitions(self):
            path = tmp_path / "transitions.json"
            return json.loads(path.read_text()) if path.exists() else []

    return Reader()


def test_a_genuine_overlap_is_written_with_its_owner_receipt_and_release_condition(reader):
    assert reader.chain.record(intent=_intent(), receipt=_RECEIPT) is True
    (call,) = reader.calls()
    assert call["action"] == "record-rollback-conflict"
    assert (call["--repository"], call["--item"], call["--attempt"]) == (
        "owner/repo",
        "incident-1",
        "attempt-1",
    )
    assert (call["--phase"], call["--operation"], call["--generation"], call["--owner"]) == (
        "reverting",
        "operation-1",
        "2",
        "controller-owner",
    )
    conflict = json.loads(call["--rollback-conflict-json"])
    assert conflict["receipt"] == _RECEIPT
    assert _RECEIPT in conflict["release_condition"]
    assert set(conflict) == {"receipt", "release_condition"}


def test_a_reopened_attempt_is_named_by_its_reverting_generation(reader):
    regression = RegressionReopen(
        attempt_id="attempt-2",
        operation_id="operation-2",
        generation=5,
        owner="reopen-owner",
        receipt_digest="d" * 64,
    )
    intent = _intent(regression=regression, phase="master-observation")
    assert reader.chain.record(intent=intent, receipt=_RECEIPT) is True
    (call,) = reader.calls()
    assert (call["--attempt"], call["--operation"], call["--generation"], call["--owner"]) == (
        "attempt-2",
        "operation-2",
        "5",
        "reopen-owner",
    )
    assert call["--phase"] == "reverting"


def test_repeating_the_same_conflict_leaves_exactly_one_transition(reader):
    assert reader.chain.record(intent=_intent(), receipt=_RECEIPT) is True
    assert reader.chain.record(intent=_intent(), receipt=_RECEIPT) is True
    assert len(reader.calls()) == 2
    assert len(reader.transitions()) == 1


def test_a_conflict_recorded_while_the_tenant_is_down_reaches_the_chain_when_it_returns(reader):
    reader.mode("down")
    assert reader.chain.record(intent=_intent(), receipt=_RECEIPT) is False
    assert reader.transitions() == []
    reader.mode("up")
    assert reader.chain.record(intent=_intent(), receipt=_RECEIPT) is True
    assert len(reader.transitions()) == 1


@pytest.mark.parametrize("mode", ["garbage", "stalled", "hang"])
def test_an_unverified_reply_is_never_a_recorded_conflict(reader, mode):
    reader.mode(mode)
    assert reader.chain.record(intent=_intent(), receipt=_RECEIPT) is False


def test_a_chain_that_refuses_the_phase_is_not_a_recorded_conflict(reader):
    assert (
        reader.chain.record(intent=_intent(phase="master-observation"), receipt=_RECEIPT) is False
    )
    assert reader.transitions() == []


def test_a_missing_reader_is_an_unavailable_tenant(tmp_path):
    chain = ConflictChain(command=(str(tmp_path / "absent"),), repo=tmp_path)
    assert chain.record(intent=_intent(), receipt=_RECEIPT) is False


def test_an_empty_reader_command_never_runs_anything(tmp_path):
    assert (
        ConflictChain(command=(), repo=tmp_path).record(intent=_intent(), receipt=_RECEIPT) is False
    )


_CHAIN_READER = textwrap.dedent(
    """
    import json, sys
    from pathlib import Path

    here = Path(sys.argv[0]).parent
    if (here / "down").exists():
        sys.exit(1)
    argv = sys.argv[1:]
    flags = dict(zip(argv[1::2], argv[2::2]))
    with (here / "calls.jsonl").open("a") as calls:
        calls.write(json.dumps(flags) + "\\n")
    state = here / "transitions.json"
    seen = json.loads(state.read_text()) if state.exists() else []
    if flags["--rollback-conflict-json"] not in seen:
        seen.append(flags["--rollback-conflict-json"])
        state.write_text(json.dumps(seen))
    print(json.dumps({
        "schema": 1, "status": "verified", "authorizes_current_effects": False,
        "normal_factory_proof": False,
        "result": {"operation_id": "op", "lifecycle_state": "blocked",
                   "reading": {"attempt": {
                       "repository": flags["--repository"], "item_id": flags["--item"],
                       "phase": "rollback-conflict", "generation": int(flags["--generation"]) + 1,
                       "owner": flags["--owner"]}}},
    }))
    """
)


class Chain:
    """The canonical chain behind a real reader process the test can take down."""

    def __init__(self, *, directory):
        self.directory = directory
        script = directory / "reader.py"
        script.write_text(_CHAIN_READER)
        self.writer = ConflictChain(command=(sys.executable, str(script)), repo=directory)

    def down(self, *, down):
        marker = self.directory / "down"
        marker.touch() if down else marker.unlink()

    def transitions(self):
        path = self.directory / "transitions.json"
        return json.loads(path.read_text()) if path.exists() else []

    def calls(self):
        path = self.directory / "calls.jsonl"
        return path.read_text().splitlines() if path.exists() else []


@pytest.fixture
def chain(tmp_path):
    directory = tmp_path / "chain"
    directory.mkdir()
    return Chain(directory=directory)


def _recover(world: World, monkeypatch: pytest.MonkeyPatch, *, chain: ConflictChain | None):
    forge = world.client(monkeypatch)
    with repository_lock(
        directory=world.installation.state, repository=REPOSITORY, existing_only=True
    ):
        result = recover_incident_inverse(
            repo_root=world.installation.repo, intent=world.intent, forge=forge, chain=chain
        )
    assert is_successful(result), result
    return unsafe_perform_io(result.unwrap())


def _overlap(world: World) -> str:
    world.push_later(
        path="shared.txt",
        text=(world.author / "shared.txt").read_text().replace("incident first", "later edit"),
    )
    return world.forge.master()


def test_a_genuine_overlap_is_written_to_the_chain_with_its_owner_and_receipt(
    world: World, chain: Chain, monkeypatch: pytest.MonkeyPatch
) -> None:
    _overlap(world)
    outcome = _recover(world, monkeypatch, chain=chain.writer)
    (conflict,) = [json.loads(raw) for raw in chain.transitions()]
    registration = world.intent.registration
    assert outcome.status == "rollback-conflict"
    assert conflict["receipt"] == outcome.receipt
    assert f"owner:{registration.owner}" in conflict["receipt"]
    (call,) = [json.loads(line) for line in chain.calls()]
    assert (call["--item"], call["--attempt"], call["--generation"], call["--owner"]) == (
        registration.incident_item_id,
        registration.attempt_id,
        str(registration.generation),
        registration.owner,
    )


def test_repeating_the_conflict_after_a_restart_leaves_exactly_one_transition(
    world: World, chain: Chain, monkeypatch: pytest.MonkeyPatch
) -> None:
    _overlap(world)
    first = _recover(world, monkeypatch, chain=chain.writer)
    again = _recover(world, monkeypatch, chain=chain.writer)
    resumed = observer_inverse_callback(
        repo_root=world.installation.repo, forge=world.client(monkeypatch), chain=chain.writer
    )
    assert resumed(world.intent) == first.receipt
    assert again.receipt == first.receipt
    assert len(chain.calls()) == 3
    assert len(chain.transitions()) == 1


def test_a_conflict_recorded_while_the_tenant_is_down_reaches_the_chain_once_it_returns(
    world: World, chain: Chain, monkeypatch: pytest.MonkeyPatch
) -> None:
    _overlap(world)
    chain.down(down=True)
    outage = _recover(world, monkeypatch, chain=chain.writer)
    assert outage.status == "rollback-conflict" and outage.receipt
    assert chain.transitions() == []
    chain.down(down=False)
    returned = _recover(world, monkeypatch, chain=chain.writer)
    assert returned.receipt == outage.receipt
    assert len(chain.transitions()) == 1


def test_a_moved_head_with_no_overlap_recomputes_and_never_enters_rollback_conflict(
    world: World, chain: Chain, monkeypatch: pytest.MonkeyPatch
) -> None:
    def move() -> None:
        world.push_later(path="keep.txt", text="kept and later changed\n")

    world.forge.hooks[("POST", "trees")] = move
    outcome = _recover(world, monkeypatch, chain=chain.writer)
    assert outcome.status == "reverted"
    assert chain.calls() == [] and chain.transitions() == []


def test_recovery_without_a_chain_still_journals_the_conflict(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    _overlap(world)
    outcome = _recover(world, monkeypatch, chain=None)
    assert outcome.status == "rollback-conflict" and outcome.receipt


def _post(*, world: World, retry: bool) -> dict[str, Any]:
    application = ControllerService(installation=world.installation, recover=Mock())
    body = json.dumps(
        {"repository": REPOSITORY, "action_id": world.intent.action_id, "retry_publish": retry}
    ).encode()
    environ = {
        "PATH_INFO": "/reconcile",
        "REQUEST_METHOD": "POST",
        "CONTENT_LENGTH": str(len(body)),
        "HTTP_AUTHORIZATION": "Bearer " + world.installation.control_secret.decode(),
        "wsgi.input": io.BytesIO(body),
    }
    return json.loads(b"".join(application(environ, lambda *_: None)))


def _use_reader(*, world: World, chain: Chain) -> None:
    world.installation = replace(world.installation, reader=tuple(chain.writer.command))


def test_a_journaled_conflict_is_replayed_to_the_chain_by_reconcile_until_it_lands(
    world: World, chain: Chain, monkeypatch: pytest.MonkeyPatch
) -> None:
    _overlap(world)
    _ = _recover(world, monkeypatch, chain=None)
    _use_reader(world=world, chain=chain)
    chain.down(down=True)
    outage = _post(world=world, retry=False)
    assert outage["status"] == "completed" and chain.transitions() == []
    chain.down(down=False)
    landed = _post(world=world, retry=False)
    assert landed["status"] == "reconciled" and landed["receipt"] == outage["receipt"]
    assert len(chain.transitions()) == 1
    calls = len(chain.calls())
    assert _post(world=world, retry=False)["status"] == "reconciled"
    assert len(chain.calls()) == calls and len(chain.transitions()) == 1


def test_an_explicit_retry_that_finds_the_overlap_records_it_on_the_chain(
    world: World, chain: Chain, monkeypatch: pytest.MonkeyPatch
) -> None:
    _overlap(world)
    world.client(monkeypatch)
    _use_reader(world=world, chain=chain)
    retried = _post(world=world, retry=True)
    assert retried["status"] in {"completed", "reconciled"} and retried["receipt"]
    assert len(chain.transitions()) == 1
    assert sys.executable in chain.writer.command


def test_the_installed_callback_carries_the_manifests_reader_as_its_conflict_chain(
    controller, monkeypatch, tmp_path
):
    application, _, _, _, _ = controller
    installation = application.installation
    captured = []
    monkeypatch.setattr(service.ControllerInstallation, "load", lambda **_: installation)
    modules = {
        "livespec_dev_tooling.incident_inverse": SimpleNamespace(
            observer_inverse_callback=lambda **kwargs: captured.append(kwargs)
            or application.recover
        ),
        "livespec_dev_tooling.incident_inverse_service": SimpleNamespace(
            ProcessInverseForge=lambda **_: object()
        ),
    }
    monkeypatch.setattr(service.importlib, "import_module", lambda name: modules[name])
    assert service.ControllerService.installed(config=tmp_path) == application
    assert captured[0]["chain"] == ConflictChain(
        command=installation.reader, repo=installation.repo
    )
