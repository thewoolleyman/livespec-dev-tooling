"""A journaled rollback-conflict reaches the canonical incident chain exactly once.

The reader in these tests is a real child process standing in for the installed
`incident_authority.py`. It keeps a small chain that behaves the way the
orchestrator's actions do: `reopen-regression` moves a merged attempt to `reverting`
and refuses a stale or ineligible observation, `record-rollback-conflict` accepts ONLY
a `reverting` generation and recovers an exact retry instead of adding a second
transition, and both refuse a payload that is not the canonical encoding. It can be
taken down to model an unavailable tenant. The recovery principal, its journal and a
reference clone are the real ones from the recovery-principal tests.
"""

from __future__ import annotations

import hashlib
import io
import json
import sys
import textwrap
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import pytest
from returns.pipeline import is_successful
from returns.unsafe import unsafe_perform_io

import livespec_dev_tooling.incident_authority_client as authority_client
import livespec_dev_tooling.incident_observer_service as service
from livespec_dev_tooling._incident_observer_store import repository_lock, save_record
from livespec_dev_tooling._incident_observer_types import (
    LeafCompletion,
    ObserverRegistration,
    RecoveryIntent,
    RegressionReopen,
)
from livespec_dev_tooling.incident_conflict_chain import (
    ConflictChain,
    replay_conflict,
)
from livespec_dev_tooling.incident_inverse import (
    observer_inverse_callback,
    recover_incident_inverse,
)
from livespec_dev_tooling.incident_observer_service import ControllerService
from tests.livespec_dev_tooling import test_incident_observer_control as control_tests
from tests.livespec_dev_tooling import test_incident_recovery_principal as principal_tests
from tests.livespec_dev_tooling.test_incident_recovery_principal import (
    REPOSITORY,
    World,
    _observer_record,
)

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-fdquen

# The real principal, its publication ledger, a forge and a reference clone.
world = principal_tests.world
controller = control_tests.controller

_RECEIPT = "rollback-conflict:exact-action-1:owner:controller-owner:head:" + "a" * 40
_REVERT_RECEIPT = "recovery-inverse:exact-action-1:commit:" + "a" * 40

# A stateful stand-in for the orchestrator chain. It mirrors `plan_reopen`
# (`_incident_recovery_plan.py`), `record_rollback_conflict`
# (`commands/_incident_rollback_conflict.py`) and their `operation_digest`, so the
# eligibility, staleness, canonical-payload and recovery rules are the real ones.
_READER = textwrap.dedent(
    """
    import hashlib, json, sys, time
    from pathlib import Path

    here = Path(sys.argv[0]).parent
    argv = sys.argv[1:]
    action, flags = argv[0], dict(zip(argv[1::2], argv[2::2]))
    mode = (here / "mode").read_text() if (here / "mode").exists() else "up"
    if mode == "down" or (mode == "record-down" and action == "record-rollback-conflict"):
        sys.exit(1)
    if mode == "hang":
        time.sleep(30)
    if mode == "garbage":
        print("not json")
        sys.exit(0)
    with (here / "calls.jsonl").open("a") as calls:
        calls.write(json.dumps({"action": action, **flags}) + "\\n")


    def say(result, *, refused=False, current=False):
        print(json.dumps({
            "schema": 1, "status": "refused" if refused else "verified",
            "authorizes_current_effects": current and not refused,
            "normal_factory_proof": False, "result": result}))
        sys.exit(78 if refused else 0)


    def refuse(code, detail):
        say({"code": code, "detail": detail}, refused=True)


    def canonical(text):
        try:
            return json.dumps(json.loads(text), sort_keys=True, separators=(",", ":")) == text
        except ValueError:
            return False


    def digest(prefix, value):
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        return prefix + "-" + hashlib.sha256(encoded).hexdigest()[:24]


    def tamper(attempt, tag):
        field = mode.removeprefix(tag) if mode.startswith(tag) else None
        changes = {
            "phase": {"phase": "collecting-failures" if attempt["phase"] == "reverting" else "reverting"},
            "generation": {"generation": attempt["generation"] - 1},
            "owner": {"owner": "someone-else"},
            "item": {"item_id": "other-item"},
            "repository": {"repository": "other/repo"},
            "attempt": {"attempt_id": "other-attempt"},
        }
        return {**attempt, **changes.get(field, {})}


    history = json.loads((here / "history.json").read_text())
    item = json.loads((here / "item.json").read_text())
    query = {"attempt_id": flags["--attempt"], "phase": flags["--phase"],
             "operation_id": flags["--operation"], "generation": int(flags["--generation"]),
             "owner": flags["--owner"]}
    matched = next(
        (a for a in history
         if a["item_id"] == flags["--item"] and all(a[k] == v for k, v in query.items())),
        None)
    if matched is None:
        refuse("incident-authority-identity-mismatch", flags["--item"])
    current = matched is history[-1]
    if action == "read-current":
        say({"attempt": matched, "is_current": current}, current=True)


    def save(attempt, status):
        history.append(attempt)
        item["status"] = status
        (here / "history.json").write_text(json.dumps(history))
        (here / "item.json").write_text(json.dumps(item))


    if action == "reopen-regression":
        attributed = (here / "attributed.txt").read_text()
        if flags["--attributed-json"] != attributed or not canonical(flags["--finding-json"]):
            refuse("incident-action-invalid-payload", "--finding-json")
        finding = json.loads(flags["--finding-json"])
        if sorted(finding) != ["attributed_commit", "failed_head", "master_healthy",
                               "run_id", "subject", "surface"]:
            refuse("incident-action-invalid-payload", "--finding-json")
        if not current:
            refuse("incident-reopen-stale-observation", matched["item_id"])
        if matched["phase"] not in ("master-observation", "repayment-admission", "closed"):
            refuse("incident-reopen-not-eligible", matched["phase"])
        if finding["surface"] != "trunk" or finding["attributed_commit"] not in matched["landed_commits"]:
            refuse("incident-regression-unattributed", finding["run_id"])
        name = digest("recovery", {"item_id": matched["item_id"],
                                   "operation_id": matched["operation_id"],
                                   "generation": matched["generation"], "finding": finding})
        reopened = {**matched, "attempt_id": name, "phase": "reverting",
                    "operation_id": name + "#reverting",
                    "generation": matched["generation"] + 1, "owner": flags["--principal"]}
        save(reopened, "active")
        say({"operation_id": name, "lifecycle_state": "active",
             "reading": {"attempt": tamper(reopened, "reopen-reply-")}})
    if action == "record-rollback-conflict":
        payload = flags["--rollback-conflict-json"]
        if not canonical(payload):
            refuse("incident-action-invalid-payload", "--rollback-conflict-json")
        if matched["phase"] != "reverting":
            refuse("incident-rollback-conflict-not-eligible", matched["phase"])
        name = digest("rollback-conflict", {
            "item_id": matched["item_id"], "operation_id": matched["operation_id"],
            "generation": matched["generation"], "conflict": json.loads(payload)})
        operation = name + "#rollback-conflict"
        recorded = next((a for a in history if a["operation_id"] == operation), None)
        if recorded is None:
            if not current:
                refuse("incident-authority-changed", matched["item_id"])
            recorded = {**matched, "phase": "rollback-conflict", "operation_id": operation,
                        "generation": matched["generation"] + 1}
            save(recorded, "blocked")
            seen = json.loads((here / "transitions.json").read_text()) \\
                if (here / "transitions.json").exists() else []
            (here / "transitions.json").write_text(json.dumps([*seen, payload]))
        state = "blocked"
        if mode == "reply-lifecycle":
            state = "active"
        say({"operation_id": name, "lifecycle_state": state,
             "reading": {"attempt": tamper(recorded, "reply-")}})
    refuse("incident-unknown-action", action)
    """
)


def _registration(*, phase="master-observation"):
    return ObserverRegistration(
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


def _intent(*, regression=None, phase="master-observation", completion=True):
    registration = _registration(phase=phase)
    leaf = LeafCompletion(
        delivery_id="delivery-1",
        repository="owner/repo",
        head_sha=registration.head_sha,
        branch="master",
        run_id=81,
        job_id=82,
        job_name="tests",
        conclusion="failure",
    )
    return RecoveryIntent(
        action_id="exact-action-1",
        registration=registration,
        completion=leaf if completion and regression is None else None,
        regression=regression,
    )


def _attempt(*, registration, history=()):
    return [
        {
            "repository": registration.repository,
            "item_id": registration.incident_item_id,
            "attempt_id": registration.attempt_id,
            "phase": registration.phase,
            "operation_id": registration.operation_id,
            "generation": registration.generation,
            "owner": registration.owner,
            "landed_commits": [registration.head_sha],
        },
        *history,
    ]


class Chain:
    """The canonical chain behind a real reader process the test can take down."""

    def __init__(self, *, directory, registration, history=(), approved=True):
        self.directory = directory
        script = directory / "reader.py"
        script.write_text(_READER)
        (directory / "history.json").write_text(
            json.dumps(_attempt(registration=registration, history=history))
        )
        (directory / "item.json").write_text(json.dumps({"status": "active"}))
        (directory / "attributed.txt").write_text(registration.authority_receipt.decode())
        self.registration = registration
        self.writer = ConflictChain(
            command=(sys.executable, str(script)),
            repo=directory,
            release="v0.298.0",
            installed_reader_approved=lambda _release, _command: approved,
        )

    def mode(self, value):
        (self.directory / "mode").write_text(value)

    def down(self, *, down):
        self.mode("down" if down else "up")

    def calls(self):
        path = self.directory / "calls.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def actions(self):
        return [call["action"] for call in self.calls()]

    def history(self):
        return json.loads((self.directory / "history.json").read_text())

    def status(self):
        return json.loads((self.directory / "item.json").read_text())["status"]

    def transitions(self):
        path = self.directory / "transitions.json"
        return json.loads(path.read_text()) if path.exists() else []

    def read_current(self):
        """The canonical read-current of the incident item, as the orchestrator answers it."""
        last = self.history()[-1]
        done = authority_client.call_authority(
            command=self.writer.command,
            action="read-current",
            flags={
                "repo": self.directory,
                "repository": last["repository"],
                "item": last["item_id"],
                "attempt": last["attempt_id"],
                "phase": last["phase"],
                "operation": last["operation_id"],
                "generation": last["generation"],
                "owner": last["owner"],
            },
            cwd=self.directory,
        )
        return done.unwrap()


@pytest.fixture
def chain(tmp_path):
    directory = tmp_path / "chain"
    directory.mkdir()
    return Chain(directory=directory, registration=_registration())


def _chain(tmp_path, *, registration, history=(), approved=True):
    directory = tmp_path / "other-chain"
    directory.mkdir()
    return Chain(directory=directory, registration=registration, history=history, approved=approved)


def test_a_first_failure_overlap_reopens_the_regression_then_records_the_conflict(chain):
    intent = _intent()
    assert chain.writer.record(intent=intent, receipt=_RECEIPT) is True
    assert chain.actions() == ["reopen-regression", "record-rollback-conflict"]
    reopen, conflict_call = chain.calls()
    registration = intent.registration
    assert reopen["--attributed-json"] == registration.authority_receipt.decode()
    assert reopen["--principal"] == registration.owner
    assert (reopen["--phase"], reopen["--generation"], reopen["--attempt"]) == (
        registration.phase,
        str(registration.generation),
        registration.attempt_id,
    )
    finding = json.loads(reopen["--finding-json"])
    assert finding == {
        "attributed_commit": registration.head_sha,
        "failed_head": registration.head_sha,
        "master_healthy": False,
        "run_id": "81",
        "subject": intent.action_id,
        "surface": "trunk",
    }
    assert reopen["--finding-json"] == json.dumps(finding, sort_keys=True, separators=(",", ":"))
    _, reverting, blocked = chain.history()
    assert reverting["phase"] == "reverting" and reverting["owner"] == registration.owner
    assert (conflict_call["--attempt"], conflict_call["--operation"]) == (
        reverting["attempt_id"],
        reverting["operation_id"],
    )
    assert (conflict_call["--phase"], conflict_call["--generation"]) == (
        "reverting",
        str(registration.generation + 1),
    )
    assert (blocked["phase"], blocked["generation"], blocked["owner"]) == (
        "rollback-conflict",
        registration.generation + 2,
        registration.owner,
    )
    assert chain.status() == "blocked"
    sent = json.loads(conflict_call["--rollback-conflict-json"])
    assert sent["receipt"] == _RECEIPT
    assert _RECEIPT in sent["release_condition"]
    assert set(sent) == {"receipt", "release_condition"}


def test_read_current_returns_the_conflict_at_the_next_generation_with_its_owner(chain):
    assert chain.writer.record(intent=_intent(), receipt=_RECEIPT) is True
    reading = chain.read_current()
    assert reading["is_current"] is True
    attempt = reading["attempt"]
    assert (attempt["phase"], attempt["generation"], attempt["owner"]) == (
        "rollback-conflict",
        4,
        "controller-owner",
    )
    (payload,) = chain.transitions()
    assert json.loads(payload)["receipt"] == _RECEIPT


def test_a_reopened_attempt_is_named_by_its_reverting_generation_without_a_second_reopen(tmp_path):
    regression = RegressionReopen(
        attempt_id="attempt-2",
        operation_id="operation-2",
        generation=5,
        owner="reopen-owner",
        receipt_digest="d" * 64,
    )
    reverting = {
        **_attempt(registration=_registration())[0],
        "attempt_id": "attempt-2",
        "phase": "reverting",
        "operation_id": "operation-2",
        "generation": 5,
        "owner": "reopen-owner",
    }
    other = _chain(tmp_path, registration=_registration(), history=[reverting])
    assert other.writer.record(intent=_intent(regression=regression), receipt=_RECEIPT) is True
    (call,) = other.calls()
    assert call["action"] == "record-rollback-conflict"
    assert (call["--attempt"], call["--operation"], call["--generation"], call["--owner"]) == (
        "attempt-2",
        "operation-2",
        "5",
        "reopen-owner",
    )
    assert call["--phase"] == "reverting"


def test_a_registration_already_at_reverting_is_not_reopened(tmp_path):
    other = _chain(tmp_path, registration=_registration(phase="reverting"))
    assert other.writer.record(intent=_intent(phase="reverting"), receipt=_RECEIPT) is True
    assert other.actions() == ["record-rollback-conflict"]


def test_repeating_the_same_conflict_leaves_exactly_one_transition(chain):
    assert chain.writer.record(intent=_intent(), receipt=_RECEIPT) is True
    assert chain.writer.record(intent=_intent(), receipt=_RECEIPT) is True
    assert chain.actions() == [
        "reopen-regression",
        "record-rollback-conflict",
        "reopen-regression",
        "record-rollback-conflict",
    ]
    assert len(chain.transitions()) == 1
    assert [attempt["phase"] for attempt in chain.history()] == [
        "master-observation",
        "reverting",
        "rollback-conflict",
    ]


def test_a_conflict_write_lost_after_the_reopen_is_finished_by_the_next_attempt(chain):
    chain.mode("record-down")
    assert chain.writer.record(intent=_intent(), receipt=_RECEIPT) is False
    assert chain.history()[-1]["phase"] == "reverting" and chain.transitions() == []
    chain.mode("up")
    assert chain.writer.record(intent=_intent(), receipt=_RECEIPT) is True
    assert len(chain.transitions()) == 1 and chain.status() == "blocked"
    assert [attempt["phase"] for attempt in chain.history()] == [
        "master-observation",
        "reverting",
        "rollback-conflict",
    ]


def test_a_conflict_recorded_while_the_tenant_is_down_reaches_the_chain_when_it_returns(chain):
    chain.down(down=True)
    assert chain.writer.record(intent=_intent(), receipt=_RECEIPT) is False
    assert chain.transitions() == [] and chain.calls() == []
    chain.down(down=False)
    assert chain.writer.record(intent=_intent(), receipt=_RECEIPT) is True
    assert len(chain.transitions()) == 1


def test_a_hung_reader_is_bounded_and_records_nothing(chain, monkeypatch):
    monkeypatch.setattr(authority_client, "AUTHORITY_CALL_CEILING_SECONDS", 1)
    chain.mode("hang")
    assert chain.writer.record(intent=_intent(), receipt=_RECEIPT) is False
    assert chain.transitions() == []


def test_a_non_json_reply_is_never_a_recorded_conflict(chain):
    chain.mode("garbage")
    assert chain.writer.record(intent=_intent(), receipt=_RECEIPT) is False


@pytest.mark.parametrize(
    "tamper", ["lifecycle", "phase", "generation", "owner", "item", "repository", "attempt"]
)
def test_a_reply_that_does_not_prove_the_blocked_next_generation_is_not_a_record(chain, tamper):
    chain.mode("reply-" + tamper)
    assert chain.writer.record(intent=_intent(), receipt=_RECEIPT) is False


@pytest.mark.parametrize("tamper", ["phase", "generation", "owner", "item", "repository"])
def test_a_reopen_reply_that_is_not_the_reverting_generation_is_not_used(chain, tamper):
    chain.mode("reopen-reply-" + tamper)
    assert chain.writer.record(intent=_intent(), receipt=_RECEIPT) is False
    assert chain.actions() == ["reopen-regression"]


def test_a_reply_missing_its_result_keys_is_not_a_record(tmp_path):
    script = tmp_path / "bare.py"
    script.write_text(
        "import json\n"
        "print(json.dumps({'schema': 1, 'status': 'verified', 'authorizes_current_effects': "
        "False, 'normal_factory_proof': False, 'result': {}}))\n"
    )
    chain = ConflictChain(
        command=(sys.executable, str(script)),
        repo=tmp_path,
        release="v1",
        installed_reader_approved=lambda _release, _command: True,
    )
    assert chain.record(intent=_intent(phase="reverting"), receipt=_RECEIPT) is False


def test_a_refusal_is_named_on_stderr_and_records_nothing(tmp_path, capsys):
    other = _chain(tmp_path, registration=_registration(phase="repair"))
    assert other.writer.record(intent=_intent(phase="repair"), receipt=_RECEIPT) is False
    assert other.actions() == ["reopen-regression"] and other.transitions() == []
    assert "incident-authority-refused: incident-reopen-not-eligible" in capsys.readouterr().err


def test_a_refused_chain_that_has_moved_on_is_not_a_recorded_conflict(chain):
    assert chain.writer.record(intent=_intent(), receipt=_RECEIPT) is True
    intent = _intent()
    moved = replace(intent.registration, generation=1)
    assert (
        chain.writer.record(intent=replace(intent, registration=moved), receipt=_RECEIPT) is False
    )
    assert chain.actions()[-1] == "reopen-regression"
    assert len(chain.transitions()) == 1


def test_a_failure_with_no_cause_has_nothing_to_attribute_and_calls_nothing(chain):
    assert chain.writer.record(intent=_intent(completion=False), receipt=_RECEIPT) is False
    assert chain.calls() == []


def test_an_authority_receipt_that_is_not_text_is_refused_before_any_call(chain):
    intent = _intent()
    broken = replace(intent.registration, authority_receipt=b"\xff\xfe")
    assert (
        chain.writer.record(intent=replace(intent, registration=broken), receipt=_RECEIPT) is False
    )
    assert chain.calls() == []


def test_an_unapproved_reader_is_never_run(tmp_path):
    other = _chain(tmp_path, registration=_registration(), approved=False)
    assert other.writer.record(intent=_intent(), receipt=_RECEIPT) is False
    assert other.calls() == []


def test_a_missing_reader_is_an_unavailable_tenant(tmp_path):
    chain = ConflictChain.installed(
        command=(str(tmp_path / "absent"),), release="v1", repo=tmp_path
    )
    assert chain.record(intent=_intent(), receipt=_RECEIPT) is False


def test_an_empty_reader_command_never_runs_anything(tmp_path):
    chain = ConflictChain.installed(command=(), release="v1", repo=tmp_path)
    assert chain.record(intent=_intent(), receipt=_RECEIPT) is False


def test_the_installed_reader_is_approved_only_for_its_own_release_and_command(tmp_path):
    chain = ConflictChain.installed(command=("/installed/reader",), release="v1", repo=tmp_path)
    assert chain.installed_reader_approved("v1", ("/installed/reader",)) is True
    assert chain.installed_reader_approved("v2", ("/installed/reader",)) is False
    assert chain.installed_reader_approved("v1", ("/other/reader",)) is False
    assert chain == ConflictChain.installed(
        command=("/installed/reader",), release="v1", repo=tmp_path
    )


def test_only_a_conflict_receipt_is_ever_replayed_onto_the_chain(chain):
    replay_conflict(intent=_intent(), receipt=_REVERT_RECEIPT, chain=chain.writer)
    replay_conflict(intent=_intent(), receipt=None, chain=chain.writer)
    replay_conflict(intent=_intent(), receipt=_RECEIPT, chain=None)
    assert chain.calls() == []
    replay_conflict(intent=_intent(), receipt=_RECEIPT, chain=chain.writer)
    assert len(chain.transitions()) == 1


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


def _first_failure(world: World) -> None:
    """Present the registration as the master-observation attempt a first failure meets."""
    intent = world.intent
    arm = replace(intent.observer_arm, phase="master-observation")
    registration = replace(intent.registration, phase="master-observation")
    world.intent = replace(intent, registration=registration, observer_arm=arm)
    save_record(path=world.record, record=_observer_record(world.intent))


@pytest.fixture
def failing(world: World, tmp_path):
    _first_failure(world)
    directory = tmp_path / "chain"
    directory.mkdir()
    return world, Chain(directory=directory, registration=world.intent.registration)


def test_a_genuine_overlap_blocks_the_item_at_rollback_conflict_on_the_next_generation(
    failing, monkeypatch: pytest.MonkeyPatch
) -> None:
    world, chain = failing
    _overlap(world)
    outcome = _recover(world, monkeypatch, chain=chain.writer)
    registration = world.intent.registration
    assert outcome.status == "rollback-conflict"
    (sent,) = [json.loads(raw) for raw in chain.transitions()]
    assert sent["receipt"] == outcome.receipt
    assert f"owner:{registration.owner}" in sent["receipt"]
    attempt = chain.read_current()["attempt"]
    assert (attempt["phase"], attempt["owner"], attempt["item_id"]) == (
        "rollback-conflict",
        registration.owner,
        registration.incident_item_id,
    )
    assert attempt["generation"] == registration.generation + 2
    assert chain.status() == "blocked"
    assert chain.actions()[:2] == ["reopen-regression", "record-rollback-conflict"]


def test_repeating_the_conflict_after_a_restart_leaves_exactly_one_transition(
    failing, monkeypatch: pytest.MonkeyPatch
) -> None:
    world, chain = failing
    _overlap(world)
    first = _recover(world, monkeypatch, chain=chain.writer)
    again = _recover(world, monkeypatch, chain=chain.writer)
    resumed = observer_inverse_callback(
        repo_root=world.installation.repo, forge=world.client(monkeypatch), chain=chain.writer
    )
    assert resumed(world.intent) == first.receipt
    assert again.receipt == first.receipt
    assert len(chain.transitions()) == 1
    assert [attempt["phase"] for attempt in chain.history()].count("rollback-conflict") == 1


def test_a_conflict_recorded_while_the_tenant_is_down_reaches_the_chain_once_it_returns(
    failing, monkeypatch: pytest.MonkeyPatch
) -> None:
    world, chain = failing
    _overlap(world)
    chain.down(down=True)
    outage = _recover(world, monkeypatch, chain=chain.writer)
    assert outage.status == "rollback-conflict" and outage.receipt
    assert chain.transitions() == [] and chain.status() == "active"
    chain.down(down=False)
    returned = _recover(world, monkeypatch, chain=chain.writer)
    assert returned.receipt == outage.receipt
    assert len(chain.transitions()) == 1 and chain.status() == "blocked"


def test_a_moved_head_with_no_overlap_recomputes_and_never_enters_rollback_conflict(
    failing, monkeypatch: pytest.MonkeyPatch
) -> None:
    world, chain = failing

    def move() -> None:
        world.push_later(path="keep.txt", text="kept and later changed\n")

    world.forge.hooks[("POST", "trees")] = move
    outcome = _recover(world, monkeypatch, chain=chain.writer)
    assert outcome.status == "reverted"
    assert chain.calls() == [] and chain.transitions() == []
    assert [attempt["phase"] for attempt in chain.history()] == ["master-observation"]
    assert chain.status() == "active"


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
    failing, monkeypatch: pytest.MonkeyPatch
) -> None:
    world, chain = failing
    _overlap(world)
    _ = _recover(world, monkeypatch, chain=None)
    _use_reader(world=world, chain=chain)
    chain.down(down=True)
    outage = _post(world=world, retry=False)
    assert outage["status"] == "completed" and chain.transitions() == []
    chain.down(down=False)
    landed = _post(world=world, retry=False)
    assert landed["status"] == "reconciled" and landed["receipt"] == outage["receipt"]
    assert len(chain.transitions()) == 1 and chain.status() == "blocked"
    calls = len(chain.calls())
    assert _post(world=world, retry=False)["status"] == "reconciled"
    assert len(chain.calls()) == calls and len(chain.transitions()) == 1


def test_a_reverted_action_is_never_replayed_as_a_conflict_by_reconcile(
    failing, monkeypatch: pytest.MonkeyPatch
) -> None:
    world, chain = failing
    outcome = _recover(world, monkeypatch, chain=None)
    assert outcome.status == "reverted"
    _use_reader(world=world, chain=chain)
    replay = _post(world=world, retry=False)
    assert replay["status"] == "completed" and replay["receipt"] == outcome.receipt
    assert chain.calls() == []


def test_an_explicit_retry_that_finds_the_overlap_records_it_on_the_chain(
    failing, monkeypatch: pytest.MonkeyPatch
) -> None:
    world, chain = failing
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
    assert captured[0]["chain"] == ConflictChain.installed(
        command=installation.reader, release=installation.reader_release, repo=installation.repo
    )
    assert captured[0]["chain"].installed_reader_approved(
        installation.reader_release, installation.reader
    )


def test_the_derived_reverting_identity_matches_the_chains_own_digest(chain):
    """A retry after a lost write names the generation the chain's digest produced."""
    assert chain.writer.record(intent=_intent(), receipt=_RECEIPT) is True
    reverting = chain.history()[1]
    expected = hashlib.sha256(
        json.dumps(
            {
                "item_id": "incident-1",
                "operation_id": "operation-1",
                "generation": 2,
                "finding": json.loads(chain.calls()[0]["--finding-json"]),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()[:24]
    assert reverting["attempt_id"] == "recovery-" + expected
    assert Path(chain.directory / "reader.py").exists()
