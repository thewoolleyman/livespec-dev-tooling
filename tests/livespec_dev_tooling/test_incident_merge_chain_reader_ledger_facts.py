"""The runner's chain reader adds the two ledger facts the merge decision needs to its reading."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock

from returns.result import Failure, Success

from livespec_dev_tooling import _incident_merge_bindings as bindings
from livespec_dev_tooling.incident_authority_client import AuthorityRefusal

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-nrb3oa

_REPOSITORY = "owner/repo"
_MARKER = "livespec-incident-authority-v1\n"


def _identity() -> bindings.ArmIdentity:
    return bindings.ArmIdentity(
        incident_id="inc-1",
        attempt_id="a-1",
        phase="repair",
        operation_id="op-1",
        generation=2,
        owner="owner",
    )


def _genesis(*, item: str = "inc-1", repository: str = _REPOSITORY) -> dict[str, str]:
    body = {
        "schema": 1,
        "repository": repository,
        "item_id": item,
        "root_token_id": "root-1",
        "claim_token_id": "claim-1",
    }
    return {"text": _MARKER + json.dumps(body, sort_keys=True, separators=(",", ":"))}


def _runner(*, status: str = "active", comments: list[dict[str, str]] | None = None):
    def run(*, argv):
        if "show" in argv:
            return 0, json.dumps([{"id": "inc-1", "status": status}])
        return 0, json.dumps(comments if comments is not None else [_genesis()])

    return Mock(side_effect=run)


def _read(monkeypatch, *, reply, run):
    monkeypatch.setattr(bindings, "call_authority", Mock(return_value=reply))
    reader = bindings.authority_chain_reader(
        command=["authority"],
        repository=_REPOSITORY,
        repo=Path("/ledger"),
        identity=_identity(),
        run=run,
    )
    return reader(incident_id="inc-1")


def test_a_verified_chain_with_a_published_genesis_reading_names_the_writer_and_status(monkeypatch):
    chain = {"attempt": {"phase": "repair"}, "is_current": True}
    reading = _read(monkeypatch, reply=Success(chain), run=_runner()).unwrap()
    facts = [
        reading["genesis_writer"] == "publish-genesis",
        reading["item_status"] == "active",
        reading["is_current"] is True,
        reading["attempt"] == {"phase": "repair"},
    ]
    assert all(facts)


def test_an_item_without_its_own_genesis_comment_gets_no_writer(monkeypatch):
    other = [_genesis(item="inc-2"), _genesis(repository="elsewhere/repo"), {"text": "note"}]
    reading = _read(monkeypatch, reply=Success({"is_current": True}), run=_runner(comments=other))
    assert reading.unwrap().get("genesis_writer") is None


def test_a_refused_chain_read_passes_through_untouched(monkeypatch):
    refusal = Failure(AuthorityRefusal(code="incident-authority-missing", detail="x"))
    run = _runner()
    answer = _read(monkeypatch, reply=refusal, run=run)
    assert all([answer is refusal, run.call_count == 0])


def test_an_unreadable_ledger_refuses_by_name(monkeypatch):
    answer = _read(
        monkeypatch, reply=Success({"is_current": True}), run=Mock(return_value=(1, "down"))
    )
    facts = [
        isinstance(answer, Failure),
        answer.failure().code == "incident-merge-runner-ledger-unreadable",
    ]
    assert all(facts)


def _answers(*, show: str, comments: str):
    def run(*, argv):
        return 0, show if "show" in argv else comments

    return Mock(side_effect=run)


def test_a_ledger_answer_that_is_not_json_refuses_by_name(monkeypatch):
    run = _answers(show="not json", comments="[]")
    answer = _read(monkeypatch, reply=Success({"is_current": True}), run=run)
    assert answer.failure().code == "incident-merge-runner-ledger-unreadable"


def test_an_item_the_ledger_does_not_list_refuses_by_name(monkeypatch):
    run = _answers(show="[]", comments="[]")
    answer = _read(monkeypatch, reply=Success({"is_current": True}), run=run)
    assert answer.failure().code == "incident-merge-runner-ledger-unreadable"


def test_comments_that_are_not_a_genesis_record_give_no_writer(monkeypatch):
    comments = json.dumps(
        [
            "not an object",
            {"text": 5},
            {"text": _MARKER + "not json"},
            {"text": _MARKER + "[1]"},
        ]
    )
    run = _answers(show=json.dumps([{"id": "inc-1", "status": "active"}]), comments=comments)
    reading = _read(monkeypatch, reply=Success({"is_current": True}), run=run).unwrap()
    assert reading.get("genesis_writer") is None


def test_a_chain_reply_that_is_not_an_object_passes_through(monkeypatch):
    reply = Success("opaque")
    run = _runner()
    answer = _read(monkeypatch, reply=reply, run=run)
    assert all([answer is reply, run.call_count == 0])


def test_a_read_for_another_incident_refuses_before_any_call(monkeypatch):
    monkeypatch.setattr(bindings, "call_authority", Mock())
    reader = bindings.authority_chain_reader(
        command=["authority"],
        repository=_REPOSITORY,
        repo=Path("/ledger"),
        identity=_identity(),
        run=_runner(),
    )
    answer = reader(incident_id="inc-2")
    facts = [
        answer.failure().code == "incident-merge-runner-incident-mismatch",
        bindings.call_authority.call_count == 0,
    ]
    assert all(facts)
