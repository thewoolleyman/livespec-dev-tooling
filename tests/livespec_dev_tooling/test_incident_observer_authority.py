"""Only the approved reader's current process reply can authorize a new arm."""

from __future__ import annotations

import json
import subprocess
from dataclasses import replace

import pytest

from livespec_dev_tooling._incident_observer_types import ObserverArm, ObserverRegistration
from livespec_dev_tooling.incident_observer_authority import CurrentAuthorityReader

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-47ij37


@pytest.fixture
def setup(tmp_path, monkeypatch):
    attempt = {
        "repository": "owner/repo",
        "item_id": "incident-1",
        "attempt_id": "repair-1",
        "phase": "repair",
        "operation_id": "operation-1",
        "generation": 1,
        "owner": "owner",
        "base": "e" * 40,
        "head": "c" * 40,
        "pr_number": 55,
        "landed_commits": [],
        "landed_trees": [],
        "original_paths": ["module.py"],
        "deferred_work": [],
        "repayment_required": True,
    }
    arm = ObserverArm(
        repository="owner/repo",
        incident_item_id="incident-1",
        attempt_id="repair-1",
        phase="repair",
        operation_id="operation-1",
        generation=1,
        owner="owner",
        pr_number=55,
        base_sha="e" * 40,
        head_sha="c" * 40,
        required_jobs=("coverage",),
        controller_release="v1.2.3",
        controller_revision="b" * 40,
        authority_receipt=json.dumps(attempt, sort_keys=True, separators=(",", ":")).encode(),
    )
    reply = {
        "schema": 1,
        "status": "verified",
        "authorizes_current_effects": True,
        "normal_factory_proof": False,
        "result": {"is_current": True, "attempt": attempt},
    }
    outputs = [subprocess.CompletedProcess([], 0, json.dumps(reply), "")]
    calls = []

    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        result = outputs[0]
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(subprocess, "run", run)
    reader = CurrentAuthorityReader(
        command=("installed-reader",),
        repo=tmp_path,
        release="v0.283.0",
        installed_reader_approved=lambda tag, command: (tag, command)
        == ("v0.283.0", ("installed-reader",)),
    )
    return arm, reader, reply, outputs, calls


def test_complete_identity_is_passed_to_read_current_without_caller_json(setup):
    arm, reader, _, _, calls = setup
    assert reader(arm)
    argv, kwargs = calls[0]
    assert argv[:2] == ["installed-reader", "read-current"]
    assert argv[argv.index("--generation") + 1] == "1"
    assert argv[argv.index("--owner") + 1] == "owner"
    assert argv[argv.index("--operation") + 1] == "operation-1"
    assert "shell" not in kwargs


def test_unapproved_or_missing_installed_reader_never_runs(setup):
    arm, reader, _, _, calls = setup
    assert not replace(reader, command=())(arm)
    assert not replace(reader, installed_reader_approved=lambda *_: False)(arm)
    assert not calls


@pytest.mark.parametrize(
    "result",
    [
        subprocess.CompletedProcess([], 78, "{}", "unavailable"),
        subprocess.CompletedProcess([], 0, "not json", ""),
        OSError("reader missing"),
        subprocess.TimeoutExpired("reader", 10),
    ],
)
def test_reader_outage_or_invalid_reply_cannot_authorize_new_admission(setup, result):
    arm, reader, _, outputs, _ = setup
    outputs[0] = result
    assert not reader(arm)


_PROTOCOL = {"schema": 1, "status": "verified", "normal_factory_proof": False}


@pytest.mark.parametrize(
    "reply",
    [
        [],
        {"schema": True},
        {"schema": 2},
        {"schema": 1, "status": "refused"},
        {**_PROTOCOL, "authorizes_current_effects": False},
        {**_PROTOCOL, "authorizes_current_effects": True, "result": []},
        {
            **_PROTOCOL,
            "authorizes_current_effects": True,
            "result": {"is_current": False, "attempt": {}},
        },
        {
            **_PROTOCOL,
            "authorizes_current_effects": True,
            "result": {"is_current": True, "attempt": []},
        },
    ],
)
def test_history_and_unknown_protocol_shapes_are_not_current_authority(setup, reply):
    arm, reader, _, outputs, _ = setup
    outputs[0] = subprocess.CompletedProcess([], 0, json.dumps(reply), "")
    assert not reader(arm)


@pytest.mark.parametrize(
    "change",
    [
        {"owner": "other"},
        {"generation": True},
        {"operation_id": "old"},
    ],
)
def test_wrong_or_ambiguous_current_identity_is_refused(setup, change):
    arm, reader, reply, outputs, _ = setup
    reply["result"]["attempt"].update(change)
    outputs[0] = subprocess.CompletedProcess([], 0, json.dumps(reply), "")
    assert not reader(arm)


def test_exact_canonical_snapshot_and_pr_scope_are_required(setup):
    arm, reader, _, _, _ = setup
    assert not reader(replace(arm, authority_receipt=b"ambient forged snapshot"))
    assert not reader(replace(arm, pr_number=56))
    assert not reader(replace(arm, base_sha="f" * 40))
    assert not reader(replace(arm, head_sha="f" * 40))


def test_standalone_postmerge_admission_needs_canonical_landed_membership(setup):
    arm, reader, reply, outputs, _ = setup
    registration = ObserverRegistration(
        repository=arm.repository,
        incident_item_id=arm.incident_item_id,
        attempt_id=arm.attempt_id,
        operation_id=arm.operation_id,
        generation=arm.generation,
        owner=arm.owner,
        phase=arm.phase,
        head_sha="a" * 40,
        run_id=91,
        required_jobs=arm.required_jobs,
        controller_release=arm.controller_release,
        controller_revision=arm.controller_revision,
        candidate_revision=arm.head_sha,
        authority_receipt=arm.authority_receipt,
    )
    assert not reader(registration)
    reply["result"]["attempt"]["landed_commits"] = [registration.head_sha]
    payload = json.dumps(reply["result"]["attempt"], sort_keys=True, separators=(",", ":")).encode()
    outputs[0] = subprocess.CompletedProcess([], 0, json.dumps(reply), "")
    assert reader(replace(registration, authority_receipt=payload))
    assert not reader(replace(registration, authority_receipt=payload, candidate_revision="f" * 40))


def test_a_reply_without_the_no_normal_proof_flag_is_not_current_authority(setup):
    arm, reader, reply, outputs, _ = setup
    del reply["normal_factory_proof"]
    outputs[0] = subprocess.CompletedProcess([], 0, json.dumps(reply), "")
    assert not reader(arm)
    reply["normal_factory_proof"] = True
    outputs[0] = subprocess.CompletedProcess([], 0, json.dumps(reply), "")
    assert not reader(arm)


def test_a_reply_repeating_a_key_is_not_current_authority(setup):
    arm, reader, reply, outputs, _ = setup
    repeated = json.dumps(reply).replace('"schema": 1', '"schema": 1, "schema": 1')
    outputs[0] = subprocess.CompletedProcess([], 0, repeated, "")
    assert not reader(arm)


def test_a_matching_attempt_that_is_no_longer_current_is_refused(setup):
    arm, reader, reply, outputs, _ = setup
    assert reply["result"]["attempt"]["head"] == arm.head_sha
    reply["result"]["is_current"] = False
    outputs[0] = subprocess.CompletedProcess([], 0, json.dumps(reply), "")
    assert not reader(arm)
