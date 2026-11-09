"""`POST /recover` reverts a landed incident attempt reopened for a related regression."""

from __future__ import annotations

import hashlib
import hmac
import io
import json
import subprocess
from dataclasses import asdict
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from livespec_dev_tooling._incident_observer_store import (
    load_record,
    repository_lock,
    save_record,
)
from livespec_dev_tooling._incident_observer_types import JobCallback, ObserverRegistration
from livespec_dev_tooling._incident_recovery_journal_identity import JournalCodec
from livespec_dev_tooling.incident_observer import admit_observer, handle_job_callback
from livespec_dev_tooling.incident_observer_service import ControllerService

_REPOSITORY = "owner/repo"
_WEBHOOK = b"webhook" * 8


@pytest.fixture
def landed():
    return ObserverRegistration(
        repository=_REPOSITORY,
        incident_item_id="incident-1",
        attempt_id="repair-2",
        operation_id="repair-operation-2",
        generation=1,
        owner="controller",
        phase="repair",
        head_sha="a" * 40,
        run_id=91,
        required_jobs=("coverage", "lint"),
        controller_release="v1.170.0",
        controller_revision="b" * 40,
        candidate_revision="c" * 40,
        authority_receipt=b"canonical-landed-receipt-2",
    )


@pytest.fixture
def reverting(landed):
    """The orchestrator's reopened generation: the attributed attempt, now `reverting`."""
    return {
        "repository": _REPOSITORY,
        "item_id": landed.incident_item_id,
        "attempt_id": "recovery-0123456789abcdef01234567",
        "phase": "reverting",
        "operation_id": "recovery-0123456789abcdef01234567#reverting",
        "generation": 2,
        "owner": "controller",
        "base": "e" * 40,
        "head": landed.candidate_revision,
        "pr_number": 55,
        "landed_commits": [landed.head_sha],
        "repayment_required": True,
    }


@pytest.fixture
def settings(tmp_path, landed):
    namespace = SimpleNamespace(
        repository=_REPOSITORY,
        repo=tmp_path / "reference",
        state=tmp_path / "protected",
        reader=("/installed/reader",),
        reader_release="v0.298.0",
        control_secret=b"control" * 8,
        query_secret=b"query" * 8,
        webhook_secret=_WEBHOOK,
    )
    admitted = admit_observer(
        directory=namespace.state,
        registration=landed,
        expected_generation=None,
        authorize_current=lambda _: True,
        released_controller=lambda *_: True,
    )
    assert admitted.status == "admitted"
    return namespace


@pytest.fixture
def chain(monkeypatch, reverting):
    """The installed canonical reader's current attempt; tests move it to model staleness."""
    current = {"attempt": reverting, "calls": 0, "during": lambda: None}

    def reader(argv, **_kwargs):
        current["calls"] += 1
        current["during"]()
        reply = {
            "schema": 1,
            "status": "verified",
            "authorizes_current_effects": True,
            "normal_factory_proof": False,
            "result": {"is_current": True, "attempt": current["attempt"]},
        }
        return subprocess.CompletedProcess(argv, 0, json.dumps(reply), "")

    monkeypatch.setattr(subprocess, "run", reader)
    return current


def _receipt(*, attempt):
    return {
        "repository": attempt["repository"],
        "incident_item_id": attempt["item_id"],
        "attempt_id": attempt["attempt_id"],
        "phase": attempt["phase"],
        "operation_id": attempt["operation_id"],
        "generation": attempt["generation"],
        "owner": attempt["owner"],
        "authority_receipt": json.dumps(attempt, sort_keys=True, separators=(",", ":"))
        .encode()
        .hex(),
    }


def _post(*, application, payload, token=None):
    body = json.dumps(payload).encode()
    secret = application.installation.control_secret if token is None else token
    statuses = []
    environ = {
        "PATH_INFO": "/recover",
        "REQUEST_METHOD": "POST",
        "CONTENT_LENGTH": str(len(body)),
        "HTTP_AUTHORIZATION": "Bearer " + secret.decode(),
        "wsgi.input": io.BytesIO(body),
    }
    reply = b"".join(application(environ, lambda status, _headers: statuses.append(status)))
    return statuses[0], json.loads(reply)


def _record(*, settings):
    with repository_lock(directory=settings.state, repository=settings.repository) as path:
        return load_record(path=path)


def _mark_armed(*, settings):
    with repository_lock(directory=settings.state, repository=settings.repository) as path:
        record = load_record(path=path)
        record["observer_arm_id"] = "a-later-unbound-arm"
        save_record(path=path, record=record)


def _action_id(*, registration):
    key = f"{registration.repository}:{registration.operation_id}:{registration.generation}:recover"
    return hashlib.sha256(key.encode()).hexdigest()


def _leaf(*, registration):
    body = json.dumps(
        {
            "action": "completed",
            "repository": {"full_name": registration.repository},
            "workflow_job": {
                "id": 92,
                "run_id": registration.run_id,
                "head_sha": registration.head_sha,
                "head_branch": registration.branch,
                "name": "coverage",
                "conclusion": "failure",
                "status": "completed",
            },
        }
    ).encode()
    return JobCallback(
        body=body,
        signature="sha256=" + hmac.new(_WEBHOOK, body, hashlib.sha256).hexdigest(),
        event="workflow_job",
        delivery_id="job-92",
    )


# DoD 1: an authenticated, verified reopened-chain receipt produces one recovery
# action through the same `recover` callback a failing master leaf uses.


def test_recover_reverts_the_reopened_landed_attempt_through_the_leaf_recovery_path(
    settings, landed, reverting, chain
):
    recover = Mock(return_value="revert-receipt-1")
    application = ControllerService(installation=settings, recover=recover)

    status, result = _post(application=application, payload=_receipt(attempt=reverting))

    action_id = _action_id(registration=landed)
    intent = recover.call_args.args[0]
    record = _record(settings=settings)
    retained = JournalCodec.retained(record=record, intent=intent)
    facts = [
        status == "202 Accepted",
        result["status"] == "completed",
        result["action_id"] == action_id,
        result["receipt"] == "revert-receipt-1",
        recover.call_count == 1,
        chain["calls"] == 1,
        intent.action_id == action_id,
        intent.registration == landed,
        intent.completion is None,
        intent.regression.generation == reverting["generation"],
        intent.regression.operation_id == reverting["operation_id"],
        record["actions"][action_id]["status"] == "completed",
        # The principal re-authenticates exactly this retained action, as it does a leaf's.
        retained is not None and retained.status == "completed",
        JournalCodec.intent(raw=JournalCodec.wire(value=asdict(intent))) == intent,
    ]
    assert all(facts), facts


# DoD 2: no control token, a stale generation, or a phase other than `reverting`
# is refused by name and records no action.


def test_recover_without_the_control_token_is_refused_and_records_nothing(
    settings, reverting, chain
):
    recover = Mock(return_value="revert-receipt-1")
    application = ControllerService(installation=settings, recover=recover)

    status, result = _post(
        application=application, payload=_receipt(attempt=reverting), token=b"guess" * 8
    )

    facts = [
        status == "403 Forbidden",
        result["reason"] == "protected control authentication and repository required",
        recover.call_count == 0,
        chain["calls"] == 0,
        not _record(settings=settings).get("actions"),
    ]
    assert all(facts), facts


def test_recover_for_an_attempt_not_in_phase_reverting_is_refused_and_records_nothing(
    settings, reverting, chain
):
    recover = Mock(return_value="revert-receipt-1")
    application = ControllerService(installation=settings, recover=recover)
    repair = {**reverting, "phase": "repair"}

    status, result = _post(application=application, payload=_receipt(attempt=repair))

    facts = [
        status == "403 Forbidden",
        result
        == {"status": "refused", "reason": "reopened incident attempt is not in phase reverting"},
        recover.call_count == 0,
        chain["calls"] == 0,
        not _record(settings=settings).get("actions"),
    ]
    assert all(facts), facts


def test_recover_with_a_generation_the_chain_has_moved_past_is_refused_and_records_nothing(
    settings, reverting, chain
):
    recover = Mock(return_value="revert-receipt-1")
    application = ControllerService(installation=settings, recover=recover)
    chain["attempt"] = {**reverting, "phase": "repair", "generation": 3}

    status, result = _post(application=application, payload=_receipt(attempt=reverting))

    facts = [
        status == "403 Forbidden",
        result
        == {
            "status": "refused",
            "reason": "canonical reopened-chain receipt is stale or unavailable",
        },
        recover.call_count == 0,
        chain["calls"] == 1,
        not _record(settings=settings).get("actions"),
    ]
    assert all(facts), facts


def test_recover_with_a_generation_not_after_the_landed_attempt_is_refused_as_stale(
    settings, landed, reverting, chain
):
    recover = Mock(return_value="revert-receipt-1")
    application = ControllerService(installation=settings, recover=recover)
    stale = {**reverting, "generation": landed.generation}

    status, result = _post(application=application, payload=_receipt(attempt=stale))

    facts = [
        status == "403 Forbidden",
        result == {"status": "refused", "reason": "reopened-chain receipt generation is stale"},
        recover.call_count == 0,
        chain["calls"] == 0,
        not _record(settings=settings).get("actions"),
    ]
    assert all(facts), facts


# DoD 3: a repeated `/recover` for the same receipt, including after an observer
# restart, answers with the existing action and causes no second revert.


def test_repeated_recover_after_an_observer_restart_answers_the_existing_action(
    settings, landed, reverting, chain
):
    recover = Mock(return_value="revert-receipt-1")
    payload = _receipt(attempt=reverting)
    first = _post(
        application=ControllerService(installation=settings, recover=recover), payload=payload
    )
    again = _post(
        application=ControllerService(installation=settings, recover=recover), payload=payload
    )
    # A fresh process during a tenant outage still answers from protected state.
    chain["attempt"] = None
    restarted = ControllerService(installation=settings, recover=recover)
    after_restart = _post(application=restarted, payload=payload)

    expected = {
        "status": "completed",
        "reason": "existing immutable action; no duplicate effect",
        "action_id": _action_id(registration=landed),
        "receipt": "revert-receipt-1",
    }
    facts = [
        first[1]["status"] == "completed",
        again == ("202 Accepted", expected),
        after_restart == ("202 Accepted", expected),
        recover.call_count == 1,
        chain["calls"] == 1,
        len(_record(settings=settings)["actions"]) == 1,
    ]
    assert all(facts), facts


def test_recover_after_the_master_leaf_already_reverted_the_attempt_causes_no_second_revert(
    settings, landed, reverting, chain
):
    recover = Mock(return_value="revert-receipt-1")
    leaf = handle_job_callback(
        directory=settings.state,
        delivery=_leaf(registration=landed),
        webhook_secret=_WEBHOOK,
        recover=recover,
    )
    application = ControllerService(installation=settings, recover=recover)

    status, result = _post(application=application, payload=_receipt(attempt=reverting))

    facts = [
        leaf.status == "completed",
        status == "202 Accepted",
        result["reason"] == "existing immutable action; no duplicate effect",
        result["action_id"] == leaf.action_id,
        recover.call_count == 1,
        chain["calls"] == 1,
        len(_record(settings=settings)["actions"]) == 1,
    ]
    assert all(facts), facts


def test_recover_whose_principal_outcome_is_unknown_retains_a_pending_action(
    settings, landed, reverting, chain
):
    recover = Mock(return_value=None)
    application = ControllerService(installation=settings, recover=recover)

    status, result = _post(application=application, payload=_receipt(attempt=reverting))

    action = _record(settings=settings)["actions"][_action_id(registration=landed)]
    facts = [
        status == "202 Accepted",
        result["status"] == "pending",
        result["receipt"] is None,
        action["status"] == "pending",
        action["receipt"] is None,
        recover.call_count == 1,
        chain["calls"] == 1,
    ]
    assert all(facts), facts


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"generation": "2"}, "invalid reopened-chain receipt"),
        ({"generation": 0}, "invalid reopened-chain receipt"),
        ({"owner": ""}, "invalid reopened-chain receipt"),
        ({"authority_receipt": 7}, "invalid reopened-chain receipt"),
        ({"authority_receipt": "not-hex"}, "invalid reopened-chain receipt"),
        ({"authority_receipt": ""}, "invalid reopened-chain receipt"),
        ({"pr_number": 55}, "invalid reopened-chain receipt"),
        ({"incident_item_id": "incident-9"}, "reopened-chain receipt names another incident"),
    ],
)
def test_malformed_or_foreign_receipts_are_refused_by_name_before_any_read(
    settings, reverting, chain, change, reason
):
    recover = Mock(return_value="revert-receipt-1")
    application = ControllerService(installation=settings, recover=recover)

    status, result = _post(application=application, payload=_receipt(attempt=reverting) | change)

    facts = [
        status == "403 Forbidden",
        result == {"status": "refused", "reason": reason},
        recover.call_count == 0,
        chain["calls"] == 0,
        not _record(settings=settings).get("actions"),
    ]
    assert all(facts), facts


def test_recover_without_a_registered_landed_attempt_is_refused(
    tmp_path, settings, reverting, chain
):
    recover = Mock(return_value="revert-receipt-1")
    empty = SimpleNamespace(**{**vars(settings), "state": tmp_path / "empty"})
    application = ControllerService(installation=empty, recover=recover)

    status, result = _post(application=application, payload=_receipt(attempt=reverting))

    facts = [
        status == "403 Forbidden",
        result == {"status": "refused", "reason": "no landed incident attempt is registered"},
        recover.call_count == 0,
        chain["calls"] == 0,
    ]
    assert all(facts), facts


def test_recover_while_a_later_attempt_is_armed_and_unbound_is_refused(settings, reverting, chain):
    recover = Mock(return_value="revert-receipt-1")
    application = ControllerService(installation=settings, recover=recover)
    _mark_armed(settings=settings)

    status, result = _post(application=application, payload=_receipt(attempt=reverting))

    facts = [
        status == "403 Forbidden",
        result == {"status": "refused", "reason": "armed observer awaits post-merge binding"},
        recover.call_count == 0,
        chain["calls"] == 0,
        not _record(settings=settings).get("actions"),
    ]
    assert all(facts), facts


def test_recover_refuses_when_the_registration_moves_during_the_canonical_read(
    settings, reverting, chain
):
    recover = Mock(return_value="revert-receipt-1")
    application = ControllerService(installation=settings, recover=recover)
    chain["during"] = lambda: _mark_armed(settings=settings)

    status, result = _post(application=application, payload=_receipt(attempt=reverting))

    facts = [
        status == "403 Forbidden",
        result == {"status": "refused", "reason": "incident registration changed before recovery"},
        recover.call_count == 0,
        chain["calls"] == 1,
        not _record(settings=settings).get("actions"),
    ]
    assert all(facts), facts


# The principal's journal authenticates a regression-caused intent only when it
# names exactly one cause and a generation after the landed attempt.


def _wire_intent(*, landed, completion, regression):
    return {
        "action_id": _action_id(registration=landed),
        "registration": JournalCodec.wire(value=asdict(landed)),
        "completion": completion,
        "observer_arm": None,
        "regression": regression,
    }


_COMPLETION = {
    "delivery_id": "job-92",
    "repository": _REPOSITORY,
    "head_sha": "a" * 40,
    "branch": "master",
    "run_id": 91,
    "job_id": 92,
    "job_name": "coverage",
    "conclusion": "failure",
}
_REGRESSION = {
    "attempt_id": "recovery-0123456789abcdef01234567",
    "operation_id": "recovery-0123456789abcdef01234567#reverting",
    "generation": 2,
    "owner": "controller",
    "receipt_digest": "d" * 64,
}


@pytest.mark.parametrize(
    ("completion", "regression", "message"),
    [
        (_COMPLETION, _REGRESSION, "recovery intent does not match retained grant"),
        (None, None, "recovery intent does not match retained grant"),
        (None, _REGRESSION | {"generation": 1}, "recovery intent does not match retained grant"),
        (None, _REGRESSION | {"receipt_digest": "short"}, "invalid recovery regression"),
        (None, _REGRESSION | {"pr_number": 55}, "invalid recovery regression"),
    ],
)
def test_the_journal_refuses_an_intent_without_exactly_one_valid_cause(
    landed, completion, regression, message
):
    raw = _wire_intent(landed=landed, completion=completion, regression=regression)

    with pytest.raises(ValueError, match=message):
        JournalCodec.intent(raw=raw)


def test_the_journal_still_decodes_a_leaf_intent_from_an_older_wire_form(landed):
    raw = _wire_intent(landed=landed, completion=_COMPLETION, regression=None)
    del raw["regression"]

    intent = JournalCodec.intent(raw=raw)

    assert (intent.completion.run_id, intent.regression) == (91, None)


def test_an_identical_recover_landing_during_the_canonical_read_wins_and_is_answered(
    settings, landed, reverting, chain
):
    recover = Mock(return_value="revert-receipt-1")
    application = ControllerService(installation=settings, recover=recover)
    payload = _receipt(attempt=reverting)
    nested = []

    def concurrent():
        chain["during"] = lambda: None
        nested.append(_post(application=application, payload=payload))

    chain["during"] = concurrent

    status, result = _post(application=application, payload=payload)

    facts = [
        nested[0][1]["status"] == "completed",
        status == "202 Accepted",
        result["reason"] == "existing immutable action; no duplicate effect",
        result["action_id"] == _action_id(registration=landed),
        recover.call_count == 1,
        chain["calls"] == 2,
    ]
    assert all(facts), facts
