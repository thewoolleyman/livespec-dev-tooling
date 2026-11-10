"""A journaled rollback-conflict reaches the canonical incident chain exactly once.

The reader in these tests is a real child process standing in for the installed
`incident_authority.py`. It keeps a small chain that behaves the way the
orchestrator's actions do: `reopen-regression` moves a merged attempt to `reverting`
and moves the item's claim, refusing a stale or ineligible observation;
`record-rollback-conflict` accepts ONLY a `reverting` generation, recovers an exact
retry instead of adding a second transition, and moves the claim only from the
generation it acted on; and both refuse a payload that is not the canonical
encoding. It can be taken down, slowed, or interrupted inside a reopen (the
orchestrator's non-atomic `reopen-regression`, bd-ib-hyho7h). The recovery principal,
its journal and a reference clone are the real ones from the recovery-principal tests.
"""

from __future__ import annotations

import hashlib
import io
import json
import sys
import textwrap
import time
from dataclasses import replace
from pathlib import Path
from threading import Event, Thread
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import pytest
from returns.pipeline import is_successful
from returns.unsafe import unsafe_perform_io

import livespec_dev_tooling.incident_authority_client as authority_client
import livespec_dev_tooling.incident_observer_reconcile as reconcile_module
import livespec_dev_tooling.incident_observer_service as service
from livespec_dev_tooling._incident_conflict_generation import ChainWrite
from livespec_dev_tooling._incident_observer_store import repository_lock, save_record
from livespec_dev_tooling._incident_observer_types import (
    LeafCompletion,
    ObserverRegistration,
    RecoveryIntent,
    RegressionReopen,
)
from livespec_dev_tooling.incident_conflict_chain import ConflictChain
from livespec_dev_tooling.incident_conflict_publication import (
    ConflictPublication,
    backoff_seconds,
    is_due,
    record_outcome,
)
from livespec_dev_tooling.incident_inverse import recover_incident_inverse
from livespec_dev_tooling.incident_observer_reconcile import ObserverReconcile
from livespec_dev_tooling.incident_observer_service import ControllerService
from tests.livespec_dev_tooling import test_incident_observer_control as control_tests
from tests.livespec_dev_tooling import test_incident_recovery_principal as principal_tests
from tests.livespec_dev_tooling.fixtures.incident_authority_refusals import (
    AUTHORITY_UNAVAILABLE,
    CLAIM_OUTCOMES,
    CRASH_EXIT,
    REFUSED_EXIT,
    TRANSITION_OUTCOME_UNKNOWN,
    TRANSITION_UNAVAILABLE,
    client_timeout,
    crash_stderr,
    refusal_reply,
)
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

# A stateful stand-in for the orchestrator chain. It mirrors `plan_reopen` and
# `reopen_for_regression` (`_incident_recovery_plan.py`, `incident_regression_recovery.py`),
# `record_rollback_conflict` and its `_claim` (`commands/_incident_rollback_conflict.py`)
# and their `operation_digest`, so the eligibility, staleness, canonical-payload, claim and
# recovery rules are the real ones. `item.json` holds the item's status and the operation
# its claim names.
_READER = (
    textwrap.dedent(
        """
    import hashlib, json, sys, time
    from pathlib import Path

    here = Path(sys.argv[0]).parent
    argv = sys.argv[1:]
    action, flags = argv[0], dict(zip(argv[1::2], argv[2::2]))
    mode = (here / "mode").read_text() if (here / "mode").exists() else "up"
    # An unreachable tenant answers exactly as the installed reader does: its own named
    # refusal, exit 78 (tests/livespec_dev_tooling/fixtures/incident_authority_refusals.py).
    outages = __OUTAGES__
    on_record = mode in ("record-down", "record-unknown") and action == "record-rollback-conflict"
    if mode == "down" or on_record:
        print(outages[mode])
        sys.exit(__REFUSED_EXIT__)
    if mode == "crash":
        sys.stderr.write(__CRASH__)
        sys.exit(__CRASH_EXIT__)
    if mode == "hang":
        time.sleep(30)
    if mode == "garbage":
        print("not json")
        sys.exit(0)
    if mode.startswith("slow-"):
        (here / "busy").write_text(action)
        time.sleep(float(mode.removeprefix("slow-")))
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
            "operation": {"operation_id": "other-operation"},
            "landed": {"landed_commits": []},
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
    if action == "read-history":
        if mode == "history-refused":
            refuse("incident-authority-history-unreadable", flags["--item"])
        say({"attempt": tamper(matched, "history-"), "is_current": current})


    def save(attempt, status=None, claim=None):
        history.append(attempt)
        if status is not None:
            item["status"] = status
        if claim is not None:
            item["claim"] = claim
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
        if mode == "half-reopen":
            save(reopened)
            sys.exit(1)
        save(reopened, "active", reopened["operation_id"])
        say({"operation_id": name, "lifecycle_state": "active",
             "reading": {"attempt": tamper(reopened, "reopen-reply-")}})
    if action == "record-rollback-conflict":
        payload = flags["--rollback-conflict-json"]
        if not canonical(payload):
            refuse("incident-action-invalid-payload", "--rollback-conflict-json")
        if matched["phase"] != "reverting":
            refuse("incident-rollback-conflict-not-eligible", matched["phase"])
        # Orchestrator v0.313.0 (bd-ib-hyho7h): a reverting generation whose item claim it
        # does not hold is refused BEFORE the chain write.
        if mode == "claim-not-held":
            refuse("incident-rollback-conflict-claim-not-held", item.get("claim"))
        name = digest("rollback-conflict", {
            "item_id": matched["item_id"], "operation_id": matched["operation_id"],
            "generation": matched["generation"], "conflict": json.loads(payload)})
        operation = name + "#rollback-conflict"
        recorded = next((a for a in history if a["operation_id"] == operation), None)
        if recorded is None:
            if not current:
                refuse("incident-generation-stale", matched["item_id"])
            recorded = {**matched, "phase": "rollback-conflict", "operation_id": operation,
                        "generation": matched["generation"] + 1}
            save(recorded)
            seen = json.loads((here / "transitions.json").read_text()) \\
                if (here / "transitions.json").exists() else []
            (here / "transitions.json").write_text(json.dumps([*seen, payload]))
        if item.get("claim") != operation:
            if recorded is not history[-1]:
                refuse("incident-generation-stale", matched["item_id"])
            if item.get("claim") != matched["operation_id"]:
                refuse("incident-rollback-conflict-lifecycle-refused", "claim-changed")
            if mode.startswith("claim-"):
                refuse("incident-rollback-conflict-lifecycle-refused", mode)
            item.update(status="blocked", claim=operation)
            (here / "item.json").write_text(json.dumps(item))
        state = "active" if mode == "reply-lifecycle" else item["status"]
        say({"operation_id": name, "lifecycle_state": state,
             "reading": {"attempt": tamper(recorded, "reply-")}})
    refuse("incident-unknown-action", action)
    """
    )
    .replace(
        "__OUTAGES__",
        repr(
            {
                "down": refusal_reply(
                    code=AUTHORITY_UNAVAILABLE,
                    detail="Dolt server unreachable at 127.0.0.1:3399: connection refused",
                ),
                "record-down": refusal_reply(
                    code=TRANSITION_UNAVAILABLE,
                    detail="Dolt server unreachable: connection refused",
                ),
                "record-unknown": refusal_reply(
                    code=TRANSITION_OUTCOME_UNKNOWN, detail="readback failed after the write"
                ),
            }
        ),
    )
    .replace("__REFUSED_EXIT__", str(REFUSED_EXIT))
    .replace("__CRASH__", repr(crash_stderr(action="record-rollback-conflict")))
    .replace("__CRASH_EXIT__", str(CRASH_EXIT))
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
        attempts = _attempt(registration=registration, history=history)
        (directory / "history.json").write_text(json.dumps(attempts))
        item = {"status": "active", "claim": attempts[-1]["operation_id"]}
        (directory / "item.json").write_text(json.dumps(item))
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

    def extend(self, *attempts, claim):
        (self.directory / "history.json").write_text(json.dumps([*self.history(), *attempts]))
        item = json.loads((self.directory / "item.json").read_text())
        (self.directory / "item.json").write_text(json.dumps({**item, **claim}))

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


_LANDED = ChainWrite.landed()
_TENANT = ChainWrite.retry(reason="tenant-unavailable")


def test_a_first_failure_overlap_reopens_the_regression_then_records_the_conflict(chain):
    intent = _intent()
    assert chain.writer.record(intent=intent, receipt=_RECEIPT) == _LANDED
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
    assert chain.writer.record(intent=_intent(), receipt=_RECEIPT) == _LANDED
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
    assert other.writer.record(intent=_intent(regression=regression), receipt=_RECEIPT) == _LANDED
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
    assert other.writer.record(intent=_intent(phase="reverting"), receipt=_RECEIPT) == _LANDED
    assert other.actions() == ["record-rollback-conflict"]


_UNCLAIMED_REOPEN = ChainWrite.terminal(
    reason=(
        "half-reopen: the reverting generation this conflict is owed to never took the "
        "item's claim, and this writer did not make that reopen, so it cannot repeat it "
        "(incident-rollback-conflict-claim-not-held, orchestrator bd-ib-hyho7h)"
    )
)


def test_a_regression_reopen_whose_claim_never_moved_is_terminal_and_named(tmp_path, capsys):
    """N1: the writer cannot repeat a regression's reopen, so retrying cannot help."""
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
    other.mode("claim-not-held")
    written = other.writer.record(intent=_intent(regression=regression), receipt=_RECEIPT)
    assert written == _UNCLAIMED_REOPEN
    assert other.actions() == ["record-rollback-conflict"] and other.transitions() == []
    err = capsys.readouterr().err
    assert "incident-authority-refused: incident-rollback-conflict-claim-not-held" in err


def test_a_registration_at_reverting_whose_claim_never_moved_is_terminal(tmp_path):
    other = _chain(tmp_path, registration=_registration(phase="reverting"))
    other.mode("claim-not-held")
    written = other.writer.record(intent=_intent(phase="reverting"), receipt=_RECEIPT)
    assert written == _UNCLAIMED_REOPEN
    assert other.actions() == ["record-rollback-conflict"] and other.transitions() == []


def test_a_first_failure_whose_claim_is_not_held_is_retried_through_its_own_reopen(chain):
    """The first-failure path reopens first, so a retry repeats the reopen, which completes."""
    chain.mode("claim-not-held")
    written = chain.writer.record(intent=_intent(), receipt=_RECEIPT)
    assert written == ChainWrite.retry(
        reason="conflict-refused: incident-rollback-conflict-claim-not-held"
    )
    assert chain.actions() == ["reopen-regression", "record-rollback-conflict"]
    assert chain.transitions() == []
    chain.mode("up")
    assert chain.writer.record(intent=_intent(), receipt=_RECEIPT) == _LANDED
    assert chain.status() == "blocked"


def test_repeating_the_same_conflict_leaves_exactly_one_transition(chain):
    assert chain.writer.record(intent=_intent(), receipt=_RECEIPT) == _LANDED
    assert chain.writer.record(intent=_intent(), receipt=_RECEIPT) == _LANDED
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
    assert chain.writer.record(intent=_intent(), receipt=_RECEIPT) == _TENANT
    assert chain.history()[-1]["phase"] == "reverting" and chain.transitions() == []
    chain.mode("up")
    assert chain.writer.record(intent=_intent(), receipt=_RECEIPT) == _LANDED
    assert len(chain.transitions()) == 1 and chain.status() == "blocked"


def test_an_unavailable_tenant_is_retried_and_writes_nothing(chain):
    chain.down(down=True)
    assert chain.writer.record(intent=_intent(), receipt=_RECEIPT) == _TENANT
    assert chain.transitions() == [] and chain.calls() == []
    chain.down(down=False)
    assert chain.writer.record(intent=_intent(), receipt=_RECEIPT) == _LANDED


def test_a_hung_reader_is_bounded_and_retried(chain, monkeypatch):
    client_timeout(monkeypatch=monkeypatch)
    chain.mode("hang")
    assert chain.writer.record(intent=_intent(), receipt=_RECEIPT) == _TENANT
    assert chain.transitions() == []


def test_a_non_json_reply_is_retried_never_a_recorded_conflict(chain):
    chain.mode("garbage")
    assert chain.writer.record(intent=_intent(), receipt=_RECEIPT) == _TENANT


@pytest.mark.parametrize(
    "tamper", ["lifecycle", "phase", "generation", "owner", "item", "repository", "attempt"]
)
def test_a_reply_that_does_not_prove_the_blocked_next_generation_is_terminal(chain, tamper):
    chain.mode("reply-" + tamper)
    written = chain.writer.record(intent=_intent(), receipt=_RECEIPT)
    assert written == ChainWrite.terminal(reason="conflict-reply-unproven")


@pytest.mark.parametrize("tamper", ["phase", "generation", "owner", "item", "repository"])
def test_a_reopen_reply_that_is_not_the_reverting_generation_is_terminal(chain, tamper):
    chain.mode("reopen-reply-" + tamper)
    written = chain.writer.record(intent=_intent(), receipt=_RECEIPT)
    assert written == ChainWrite.terminal(reason="reopen-reply-unproven")
    assert chain.actions() == ["reopen-regression"]


def test_a_reply_missing_its_result_keys_is_never_a_recorded_conflict(tmp_path):
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
    written = chain.record(intent=_intent(phase="reverting"), receipt=_RECEIPT)
    assert written == ChainWrite.terminal(reason="conflict-reply-unproven")


def test_a_reopen_refusal_not_known_to_be_final_is_retried_under_its_code(tmp_path, capsys):
    other = _chain(tmp_path, registration=_registration(phase="collecting-failures"))
    intent = _intent(phase="collecting-failures")
    written = other.writer.record(intent=intent, receipt=_RECEIPT)
    assert written == ChainWrite.retry(reason="reopen-refused: incident-reopen-not-eligible")
    assert other.actions() == ["reopen-regression"] and other.transitions() == []
    assert "incident-authority-refused: incident-reopen-not-eligible" in capsys.readouterr().err


def test_a_conflict_the_owner_already_resolved_is_terminal_and_never_rewritten(chain):
    assert chain.writer.record(intent=_intent(), receipt=_RECEIPT) == _LANDED
    blocked = chain.history()[-1]
    released = {
        **blocked,
        "phase": "reverting",
        "operation_id": "rollback-release-x#reverting",
        "generation": blocked["generation"] + 1,
    }
    chain.extend(released, claim={"status": "active", "claim": released["operation_id"]})
    written = chain.writer.record(intent=_intent(), receipt=_RECEIPT)
    assert written.status == "terminal"
    assert written.reason.startswith("superseded: the chain moved past this conflict")
    assert len(chain.transitions()) == 1 and chain.status() == "active"


def test_a_different_reopen_holding_the_chain_is_terminal(chain):
    other = {
        **chain.history()[0],
        "attempt_id": "recovery-another-finding",
        "phase": "reverting",
        "operation_id": "recovery-another-finding#reverting",
        "generation": 3,
    }
    chain.extend(other, claim={"claim": other["operation_id"]})
    written = chain.writer.record(intent=_intent(), receipt=_RECEIPT)
    assert written == ChainWrite.terminal(reason="superseded: a different reopen holds the chain")
    assert chain.actions() == ["reopen-regression", "record-rollback-conflict"]
    assert chain.transitions() == []


def test_a_reopen_interrupted_before_its_claim_is_retried_as_claim_changed(chain, capsys):
    """bd-ib-hyho7h: the chain moved to reverting but the claim stayed on the merge.

    One `claim-changed` is indistinguishable from a lost token race, so the writer retries
    it under its own reason; the publication calls it a half-reopen only once it persists.
    """
    chain.mode("half-reopen")
    assert chain.writer.record(intent=_intent(), receipt=_RECEIPT) == _TENANT
    chain.mode("up")
    written = chain.writer.record(intent=_intent(), receipt=_RECEIPT)
    assert written == ChainWrite.retry(reason="claim-changed")
    assert chain.history()[-1]["phase"] == "rollback-conflict"
    assert chain.status() == "active"
    err = capsys.readouterr().err
    assert "incident-rollback-conflict-lifecycle-refused: claim-changed" in err


@pytest.mark.parametrize("outcome", [o for o in CLAIM_OUTCOMES if o != "claim-changed"])
def test_a_transient_claim_outcome_is_retried_never_called_a_half_reopen(chain, outcome):
    chain.mode(outcome)
    written = chain.writer.record(intent=_intent(), receipt=_RECEIPT)
    assert written == ChainWrite.retry(reason=f"claim-unsettled: {outcome}")


@pytest.mark.parametrize(
    "phase", ["master-observation", "repair", "reverting"], ids=["merged", "armed", "reopened"]
)
def test_the_orchestrators_own_outage_refusal_is_retried_at_every_entry_point(
    tmp_path, phase, capsys
):
    """The real reader's Dolt outage: exit 78, incident-authority-unavailable (review F1)."""
    if phase == "repair":
        chain, _ = _armed_chain(tmp_path / "armed", registration=_registration(phase=phase))
    else:
        chain = _chain(tmp_path, registration=_registration(phase=phase))
    chain.down(down=True)
    assert chain.writer.record(intent=_intent(phase=phase), receipt=_RECEIPT) == _TENANT
    assert f"incident-authority-refused: {AUTHORITY_UNAVAILABLE}" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("mode", "code"),
    [("record-down", TRANSITION_UNAVAILABLE), ("record-unknown", TRANSITION_OUTCOME_UNKNOWN)],
)
def test_a_conflict_commit_that_failed_or_whose_fate_is_unknown_is_retried(
    chain, capsys, mode, code
):
    chain.mode(mode)
    assert chain.writer.record(intent=_intent(), receipt=_RECEIPT) == _TENANT
    assert f"incident-authority-refused: {code}" in capsys.readouterr().err


def test_a_reader_that_dies_without_a_reply_is_retried(chain):
    chain.mode("crash")
    assert chain.writer.record(intent=_intent(), receipt=_RECEIPT) == _TENANT


def test_a_failure_with_no_cause_has_nothing_to_attribute_and_calls_nothing(chain):
    written = chain.writer.record(intent=_intent(completion=False), receipt=_RECEIPT)
    assert written == ChainWrite.terminal(reason="no-failing-leaf")
    assert chain.calls() == []


def test_an_authority_receipt_that_is_not_text_is_terminal_before_any_call(chain):
    intent = _intent()
    broken = replace(intent.registration, authority_receipt=b"\xff\xfe")
    written = chain.writer.record(intent=replace(intent, registration=broken), receipt=_RECEIPT)
    assert written == ChainWrite.terminal(reason="receipt-not-canonical")
    assert chain.calls() == []


def test_an_unapproved_reader_is_never_run(tmp_path):
    other = _chain(tmp_path, registration=_registration(), approved=False)
    written = other.writer.record(intent=_intent(), receipt=_RECEIPT)
    assert written == ChainWrite.retry(reason="reader-unapproved")
    assert other.calls() == []


def test_a_missing_reader_is_an_unavailable_tenant(tmp_path):
    chain = ConflictChain.installed(
        command=(str(tmp_path / "absent"),), release="v1", repo=tmp_path
    )
    assert chain.record(intent=_intent(), receipt=_RECEIPT) == _TENANT


def test_an_empty_reader_command_never_runs_anything(tmp_path):
    chain = ConflictChain.installed(command=(), release="v1", repo=tmp_path)
    assert chain.record(intent=_intent(), receipt=_RECEIPT) == ChainWrite.retry(
        reason="reader-unapproved"
    )


def test_the_installed_reader_is_approved_only_for_its_own_release_and_command(tmp_path):
    chain = ConflictChain.installed(command=("/installed/reader",), release="v1", repo=tmp_path)
    assert chain.installed_reader_approved("v1", ("/installed/reader",)) is True
    assert chain.installed_reader_approved("v2", ("/installed/reader",)) is False
    assert chain.installed_reader_approved("v1", ("/other/reader",)) is False
    assert chain == ConflictChain.installed(
        command=("/installed/reader",), release="v1", repo=tmp_path
    )


def test_the_derived_reverting_identity_matches_the_chains_own_digest(chain):
    """A retry after a lost write names the generation the chain's digest produced."""
    assert chain.writer.record(intent=_intent(), receipt=_RECEIPT) == _LANDED
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


def _armed_chain(directory: Path, *, registration: ObserverRegistration, merged: bool = True):
    """A pre-merge arm's chain: the armed `repair` generation, then `record-merge`'s successor.

    The arm keeps the `repair` generation it armed at and lands no commits; the merge one
    generation on carries the landed commits, so only its record attributes a `trunk` finding.
    """
    directory.mkdir()
    chain = Chain(directory=directory, registration=registration)
    repair = {**chain.history()[0], "landed_commits": []}
    merge = {
        **repair,
        "phase": "master-observation",
        "operation_id": f"{registration.attempt_id}#master-observation",
        "generation": registration.generation + 1,
        "landed_commits": [registration.head_sha],
    }
    (directory / "history.json").write_text(json.dumps([repair, merge] if merged else [repair]))
    claimed = merge if merged else repair
    item = {"status": "active", "claim": claimed["operation_id"]}
    (directory / "item.json").write_text(json.dumps(item))
    (directory / "attributed.txt").write_text(
        json.dumps(merge, sort_keys=True, separators=(",", ":"))
    )
    return chain, merge


def test_a_pre_merge_arm_reopens_the_generation_record_merge_wrote(tmp_path):
    registration = _registration(phase="repair")
    chain, merge = _armed_chain(tmp_path / "armed", registration=registration)
    assert chain.writer.record(intent=_intent(phase="repair"), receipt=_RECEIPT) == _LANDED
    assert chain.actions() == ["read-history", "reopen-regression", "record-rollback-conflict"]
    history, reopen, conflict = chain.calls()
    merged_identity = ("master-observation", "attempt-1#master-observation", "3", "attempt-1")
    assert (
        history["--phase"],
        history["--operation"],
        history["--generation"],
        history["--attempt"],
    ) == merged_identity
    assert (reopen["--phase"], reopen["--operation"], reopen["--generation"]) == (
        merged_identity[:3]
    )
    assert reopen["--attributed-json"] == json.dumps(merge, sort_keys=True, separators=(",", ":"))
    assert json.loads(reopen["--finding-json"])["attributed_commit"] == registration.head_sha
    assert (conflict["--phase"], conflict["--generation"]) == ("reverting", "4")
    attempt = chain.read_current()["attempt"]
    assert (attempt["phase"], attempt["generation"], attempt["owner"]) == (
        "rollback-conflict",
        5,
        registration.owner,
    )
    assert chain.status() == "blocked" and len(chain.transitions()) == 1


def test_a_pre_merge_arm_retries_until_record_merge_then_reaches_the_chain(tmp_path, capsys):
    registration = _registration(phase="repair")
    chain, merge = _armed_chain(tmp_path / "armed", registration=registration, merged=False)
    written = chain.writer.record(intent=_intent(phase="repair"), receipt=_RECEIPT)
    assert written == ChainWrite.retry(reason="merge-unrecorded")
    assert chain.actions() == ["read-history"] and chain.transitions() == []
    assert "incident-authority-identity-mismatch" in capsys.readouterr().err
    chain.extend(merge, claim={"claim": merge["operation_id"]})
    assert chain.writer.record(intent=_intent(phase="repair"), receipt=_RECEIPT) == _LANDED
    assert len(chain.transitions()) == 1 and chain.status() == "blocked"


@pytest.mark.parametrize(
    "tamper",
    ["phase", "generation", "owner", "item", "repository", "attempt", "operation", "landed"],
)
def test_a_merge_record_that_is_not_this_attempts_landed_merge_is_terminal(
    tmp_path, tamper, capsys
):
    chain, _ = _armed_chain(tmp_path / "armed", registration=_registration(phase="repair"))
    chain.mode("history-" + tamper)
    written = chain.writer.record(intent=_intent(phase="repair"), receipt=_RECEIPT)
    assert written == ChainWrite.terminal(reason="merge-record-mismatch")
    assert chain.actions() == ["read-history"] and chain.transitions() == []
    assert "records no merge of this attempt" in capsys.readouterr().err


def test_a_merge_read_the_chain_refuses_otherwise_is_retried_under_its_code(tmp_path):
    chain, _ = _armed_chain(tmp_path / "armed", registration=_registration(phase="repair"))
    chain.mode("history-refused")
    written = chain.writer.record(intent=_intent(phase="repair"), receipt=_RECEIPT)
    assert written == ChainWrite.retry(
        reason="merge-read-refused: incident-authority-history-unreadable"
    )


def test_a_merge_read_the_tenant_never_answered_is_retried(tmp_path):
    chain, _ = _armed_chain(tmp_path / "armed", registration=_registration(phase="repair"))
    chain.down(down=True)
    assert chain.writer.record(intent=_intent(phase="repair"), receipt=_RECEIPT) == _TENANT


# --- The publication: the chain write between two short fenced steps -----------------


def _recover(world: World, monkeypatch: pytest.MonkeyPatch):
    forge = world.client(monkeypatch)
    with repository_lock(
        directory=world.installation.state, repository=REPOSITORY, existing_only=True
    ):
        result = recover_incident_inverse(
            repo_root=world.installation.repo, intent=world.intent, forge=forge
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
    """Present the registration as the master-observation attempt a standalone admission binds."""
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


def _use_reader(*, world: World, chain: Chain) -> None:
    world.installation = replace(world.installation, reader=tuple(chain.writer.command))


class Clock:
    """A settable clock for back-off."""

    def __init__(self):
        self.now = 1_000_000.0

    def __call__(self):
        return self.now


def _settle(world: World, *, automatic: bool, clock=None, retry: bool = False):
    reconcile = ObserverReconcile(installation=world.installation, clock=clock or Clock())
    return reconcile.settle(action_id=world.intent.action_id, retry=retry, automatic=automatic)


def _action(world: World) -> dict[str, Any]:
    return json.loads(world.record.read_text())["actions"][world.intent.action_id]


def _journal(world: World, chain: Chain, monkeypatch) -> Any:
    _overlap(world)
    outcome = _recover(world, monkeypatch)
    _use_reader(world=world, chain=chain)
    return outcome


def test_the_recovery_journals_the_conflict_and_never_writes_the_chain_under_the_fence(
    failing, monkeypatch
):
    world, chain = failing
    outcome = _journal(world, chain, monkeypatch)
    assert outcome.status == "rollback-conflict" and outcome.receipt
    assert chain.calls() == [] and chain.transitions() == []


def test_a_genuine_overlap_blocks_the_item_at_rollback_conflict_on_the_next_generation(
    failing, monkeypatch
):
    world, chain = failing
    outcome = _journal(world, chain, monkeypatch)
    settled = _settle(world, automatic=True)
    registration = world.intent.registration
    assert settled.status == "reconciled" and settled.receipt == outcome.receipt
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
    assert chain.status() == "blocked" and _action(world)["reconciled"] is True


def test_a_pre_merge_arm_overlap_blocks_the_item_through_its_recorded_merge(
    world: World, tmp_path, monkeypatch
):
    """The arm the expedited merge entrance records is the registration a first failure meets."""
    registration = world.intent.registration
    chain, _ = _armed_chain(tmp_path / "armed", registration=registration)
    outcome = _journal(world, chain, monkeypatch)
    settled = _settle(world, automatic=False)
    actions = chain.actions()
    attempt = chain.read_current()["attempt"]
    facts = (
        registration.phase == "repair",
        settled.status == "reconciled",
        attempt["phase"] == "rollback-conflict",
        attempt["generation"] == registration.generation + 3,
        attempt["owner"] == registration.owner,
        chain.status() == "blocked",
        actions == ["read-history", "reopen-regression", "record-rollback-conflict"],
        [json.loads(raw)["receipt"] for raw in chain.transitions()] == [outcome.receipt],
    )
    assert all(facts), facts


def test_repeating_the_conflict_after_a_restart_leaves_exactly_one_transition(failing, monkeypatch):
    world, chain = failing
    _journal(world, chain, monkeypatch)
    assert _settle(world, automatic=True).status == "reconciled"
    calls = len(chain.calls())
    assert _settle(world, automatic=True).status == "reconciled"
    assert _post(world=world, retry=False)["status"] == "reconciled"
    assert len(chain.calls()) == calls and len(chain.transitions()) == 1
    assert [attempt["phase"] for attempt in chain.history()].count("rollback-conflict") == 1


def test_a_conflict_recorded_while_the_tenant_is_down_backs_off_then_lands_when_it_returns(
    failing, monkeypatch
):
    world, chain = failing
    _journal(world, chain, monkeypatch)
    clock = Clock()
    chain.down(down=True)
    outage = _settle(world, automatic=True, clock=clock)
    assert outage.status == "completed" and "deferred: tenant-unavailable" in outage.reason
    state = _action(world)["sweep"]
    assert (state["attempts"], state["next_at"]) == (1, clock.now + 300)
    assert chain.transitions() == [] and chain.status() == "active"
    chain.down(down=False)
    early = _settle(world, automatic=True, clock=clock)
    assert "deferred: backing off" in early.reason and chain.calls() == []
    clock.now += 300
    landed = _settle(world, automatic=True, clock=clock)
    assert landed.status == "reconciled" and landed.receipt == outage.receipt
    assert len(chain.transitions()) == 1 and chain.status() == "blocked"


def test_an_operator_reconcile_ignores_the_back_off_but_not_a_terminal_state(failing, monkeypatch):
    world, chain = failing
    _journal(world, chain, monkeypatch)
    chain.down(down=True)
    assert "deferred" in _settle(world, automatic=True).reason
    chain.down(down=False)
    assert _post(world=world, retry=False)["status"] == "reconciled"


def test_a_terminal_conflict_is_journaled_with_its_reason_and_never_written_again(
    failing, monkeypatch, capsys
):
    world, chain = failing
    _journal(world, chain, monkeypatch)
    chain.mode("half-reopen")
    _ = _settle(world, automatic=True)
    chain.mode("up")
    clock = Clock()
    reasons = []
    for _attempt in range(3):
        clock.now += 3600
        reasons.append(_settle(world, automatic=True, clock=clock).reason)
    terminal_reason = reasons[-1]
    state = _action(world)["sweep"]
    assert reasons[:2] == ["rollback-conflict deferred: claim-changed"] * 2
    assert state["streak"] == 3 and state["attempts"] == 4
    assert "rollback-conflict terminal: half-reopen:" in terminal_reason
    assert state["terminal"].startswith("half-reopen:") and "bd-ib-hyho7h" in state["terminal"]
    assert "terminal: half-reopen:" in capsys.readouterr().err
    calls = len(chain.calls())
    assert _post(world=world, retry=False)["reason"].startswith("rollback-conflict terminal:")
    clock.now += 10 * 3600
    assert "terminal" in _settle(world, automatic=True, clock=clock).reason
    assert len(chain.calls()) == calls
    assert not is_due(action=_action(world), now=clock.now)


def test_a_retried_reason_turns_terminal_after_its_bound(failing, monkeypatch):
    world, chain = failing
    _journal(world, chain, monkeypatch)
    assert _settle(world, automatic=False).status == "reconciled"
    record = json.loads(world.record.read_text())
    record["actions"][world.intent.action_id].pop("reconciled")
    world.record.write_text(json.dumps(record))
    receipt = _action(world)["receipt"]
    clock = Clock()
    outcomes = [
        record_outcome(
            state=world.installation.state,
            repository=REPOSITORY,
            action_id=world.intent.action_id,
            receipt=receipt,
            outcome=ChainWrite.retry(reason="merge-unrecorded"),
            clock=clock,
        ).status
        for _ in range(12)
    ]
    assert outcomes == ["deferred"] * 11 + ["terminal"]
    assert _action(world)["sweep"]["terminal"] == "merge-unrecorded: no landing after 12 attempts"
    other = record_outcome(
        state=world.installation.state,
        repository=REPOSITORY,
        action_id=world.intent.action_id,
        receipt=receipt,
        outcome=ChainWrite.retry(reason="tenant-unavailable"),
        clock=clock,
    )
    assert other.status == "terminal" and _action(world)["sweep"]["attempts"] == 12


def test_the_tenant_bound_is_forty_eight_attempts(failing, monkeypatch):
    world, chain = failing
    _journal(world, chain, monkeypatch)
    assert _settle(world, automatic=False).status == "reconciled"
    record = json.loads(world.record.read_text())
    record["actions"][world.intent.action_id].pop("reconciled")
    world.record.write_text(json.dumps(record))
    receipt = _action(world)["receipt"]
    statuses = [
        record_outcome(
            state=world.installation.state,
            repository=REPOSITORY,
            action_id=world.intent.action_id,
            receipt=receipt,
            outcome=_TENANT,
        ).status
        for _ in range(48)
    ]
    assert statuses == ["deferred"] * 47 + ["terminal"]


def test_back_off_doubles_from_five_minutes_and_caps_at_an_hour():
    assert [backoff_seconds(attempts=n) for n in (1, 2, 3, 4, 5, 9)] == [
        300,
        600,
        1200,
        2400,
        3600,
        3600,
    ]
    assert is_due(action={}, now=0.0)
    assert not is_due(action={"sweep": {"next_at": 10.0}}, now=9.0)
    assert is_due(action={"sweep": {"next_at": 10.0}}, now=10.0)


def test_an_outcome_for_an_action_that_changed_during_the_write_records_nothing(
    failing, monkeypatch
):
    world, chain = failing
    _journal(world, chain, monkeypatch)
    _ = _settle(world, automatic=True)
    receipt = _action(world)["receipt"]
    before = world.record.read_text()
    changed = record_outcome(
        state=world.installation.state,
        repository=REPOSITORY,
        action_id=world.intent.action_id,
        receipt="rollback-conflict:another",
        outcome=_LANDED,
    )
    reconciled = record_outcome(
        state=world.installation.state,
        repository=REPOSITORY,
        action_id=world.intent.action_id,
        receipt=receipt,
        outcome=_TENANT,
    )
    missing = record_outcome(
        state=world.installation.state,
        repository=REPOSITORY,
        action_id="0" * 64,
        receipt=receipt,
        outcome=_LANDED,
    )
    assert (changed.status, reconciled.status, missing.status) == (
        "skipped",
        "reconciled",
        "skipped",
    )
    assert world.record.read_text() == before


def test_a_write_whose_action_was_reconciled_meanwhile_is_left_reconciled(failing, monkeypatch):
    world, chain = failing
    _journal(world, chain, monkeypatch)
    assert _settle(world, automatic=False, retry=False).status == "reconciled"
    record = json.loads(world.record.read_text())
    record["actions"][world.intent.action_id].pop("reconciled")
    world.record.write_text(json.dumps(record))
    receipt = _action(world)["receipt"]

    def rival(**_):
        current = json.loads(world.record.read_text())
        current["actions"][world.intent.action_id]["reconciled"] = True
        world.record.write_text(json.dumps(current))
        return _TENANT

    publication = ConflictPublication(
        state=world.installation.state,
        repository=REPOSITORY,
        chain=SimpleNamespace(record=rival),
    )
    published = publication.publish(intent=world.intent, receipt=receipt, automatic=False)
    assert published.status == "reconciled" and "sweep" not in _action(world)
    again = publication.publish(intent=world.intent, receipt=receipt, automatic=True)
    assert again.status == "reconciled"
    assert (
        publication.publish(intent=world.intent, receipt="rollback-conflict:other", automatic=True)
    ).status == "skipped"


def test_a_claim_race_lost_once_then_won_lands_and_is_never_called_a_half_reopen(
    failing, monkeypatch
):
    world, chain = failing
    _journal(world, chain, monkeypatch)
    chain.mode("claim-changed")
    clock = Clock()
    lost = _settle(world, automatic=True, clock=clock)
    chain.mode("up")
    clock.now += 3600
    won = _settle(world, automatic=True, clock=clock)
    assert "deferred: claim-changed" in lost.reason and won.status == "reconciled"
    assert "terminal" not in _action(world)["sweep"]


def test_a_landed_write_wins_over_a_terminal_a_rival_recorded_first(failing, monkeypatch):
    world, chain = failing
    _journal(world, chain, monkeypatch)
    chain.down(down=True)
    assert "deferred" in _settle(world, automatic=True).reason
    receipt = _action(world)["receipt"]
    rival = record_outcome(
        state=world.installation.state,
        repository=REPOSITORY,
        action_id=world.intent.action_id,
        receipt=receipt,
        outcome=ChainWrite.terminal(reason="superseded: a rival's diagnosis"),
    )
    landed = record_outcome(
        state=world.installation.state,
        repository=REPOSITORY,
        action_id=world.intent.action_id,
        receipt=receipt,
        outcome=_LANDED,
    )
    action = _action(world)
    assert (rival.status, landed.status, action["reconciled"]) == ("terminal", "reconciled", True)
    assert "terminal" not in action["sweep"]
    assert action["sweep"]["superseded_terminal"] == "superseded: a rival's diagnosis"


def test_a_write_made_during_the_chain_call_survives_the_outcome_write(failing, monkeypatch):
    """The outcome write re-reads the record under the fence; it never saves a stale copy."""
    world, chain = failing
    _journal(world, chain, monkeypatch)
    chain.down(down=True)
    assert "deferred" in _settle(world, automatic=True).reason
    receipt = _action(world)["receipt"]
    other_id = "f" * 64

    def concurrent(**_):
        with repository_lock(directory=world.installation.state, repository=REPOSITORY) as path:
            record = json.loads(path.read_text())
            record["actions"][other_id] = {"status": "pending", "written": "mid-call"}
            record["actions"][world.intent.action_id]["note"] = "mid-call"
            save_record(path=path, record=record)
        return _LANDED

    published = ConflictPublication(
        state=world.installation.state,
        repository=REPOSITORY,
        chain=SimpleNamespace(record=concurrent),
    ).publish(intent=world.intent, receipt=receipt, automatic=False)
    actions = json.loads(world.record.read_text())["actions"]
    assert published.status == "reconciled" and actions[world.intent.action_id]["reconciled"]
    assert actions[other_id] == {"status": "pending", "written": "mid-call"}
    assert actions[world.intent.action_id]["note"] == "mid-call"


def test_a_callback_gets_the_fence_while_the_principals_lookup_is_slow(failing, monkeypatch):
    """/reconcile asks the principal for the receipt OUTSIDE the fence (review F4, MR14)."""
    world, chain = failing
    _overlap(world)
    _recover(world, monkeypatch)
    _use_reader(world=world, chain=chain)
    looking = Event()

    class SlowForge(reconcile_module.ProcessInverseForge):
        def read_exact_receipt(self, *, intent):
            looking.set()
            time.sleep(6)
            return super().read_exact_receipt(intent=intent)

    monkeypatch.setattr(reconcile_module, "ProcessInverseForge", SlowForge)
    thread = Thread(target=lambda: _settle(world, automatic=True), daemon=True)
    thread.start()
    assert looking.wait(30)
    started = time.monotonic()
    with repository_lock(
        directory=world.installation.state, repository=REPOSITORY, wait_seconds=5.0
    ):
        waited = time.monotonic() - started
    assert waited < 5.0 and thread.is_alive()
    thread.join(timeout=60)
    assert not thread.is_alive() and chain.status() == "blocked"


def test_a_moved_head_with_no_overlap_recomputes_and_never_reaches_the_chain(failing, monkeypatch):
    world, chain = failing

    def move() -> None:
        world.push_later(path="keep.txt", text="kept and later changed\n")

    world.forge.hooks[("POST", "trees")] = move
    outcome = _recover(world, monkeypatch)
    _use_reader(world=world, chain=chain)
    assert outcome.status == "reverted"
    settled = _settle(world, automatic=True)
    assert settled.status == "completed" and settled.receipt == outcome.receipt
    assert chain.calls() == [] and chain.transitions() == []
    assert [attempt["phase"] for attempt in chain.history()] == ["master-observation"]
    assert chain.status() == "active"


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


def test_reconcile_writes_a_journaled_conflict_once_the_tenant_returns(failing, monkeypatch):
    world, chain = failing
    _journal(world, chain, monkeypatch)
    chain.down(down=True)
    outage = _post(world=world, retry=False)
    assert outage["status"] == "completed" and chain.transitions() == []
    chain.down(down=False)
    landed = _post(world=world, retry=False)
    assert landed["status"] == "reconciled" and landed["receipt"] == outage["receipt"]
    assert len(chain.transitions()) == 1 and chain.status() == "blocked"


def test_a_reverted_action_is_never_written_as_a_conflict_by_reconcile(failing, monkeypatch):
    world, chain = failing
    outcome = _recover(world, monkeypatch)
    assert outcome.status == "reverted"
    _use_reader(world=world, chain=chain)
    replay = _post(world=world, retry=False)
    assert replay["status"] == "completed" and replay["receipt"] == outcome.receipt
    assert chain.calls() == []


def test_an_explicit_retry_that_finds_the_overlap_writes_it_to_the_chain(failing, monkeypatch):
    world, chain = failing
    _overlap(world)
    world.client(monkeypatch)
    _use_reader(world=world, chain=chain)
    retried = _post(world=world, retry=True)
    assert retried["status"] == "reconciled" and retried["receipt"]
    assert len(chain.transitions()) == 1


def test_the_installed_service_recovers_without_a_chain_and_wakes_the_sweep_on_a_conflict(
    controller, monkeypatch, tmp_path
):
    application, _, _, _, _ = controller
    installation = application.installation
    captured = []
    receipts = iter([_REVERT_RECEIPT, None, _RECEIPT])
    monkeypatch.setattr(service.ControllerInstallation, "load", lambda **_: installation)
    modules = {
        "livespec_dev_tooling.incident_inverse": SimpleNamespace(
            observer_inverse_callback=lambda **kwargs: captured.append(kwargs)
            or (lambda _intent: next(receipts))
        ),
        "livespec_dev_tooling.incident_inverse_service": SimpleNamespace(
            ProcessInverseForge=lambda **_: object()
        ),
    }
    monkeypatch.setattr(service.importlib, "import_module", lambda name: modules[name])
    installed = service.ControllerService.installed(config=tmp_path)
    assert installed is not None and set(captured[0]) == {"repo_root", "forge"}
    woken = installed.conflict_journaled
    assert installed.recover(_intent()) == _REVERT_RECEIPT and not woken.is_set()
    assert installed.recover(_intent()) is None and not woken.is_set()
    assert installed.recover(_intent()) == _RECEIPT and woken.is_set()
