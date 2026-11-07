"""Every recovery principal refusal is named, effect-free and leaves master untouched."""

from __future__ import annotations

import json
from dataclasses import asdict, replace

import pytest

from livespec_dev_tooling._incident_recovery_publication import PublicationLedger
from tests.livespec_dev_tooling.test_incident_recovery_principal import (
    conflict_request,
    no_app,
    plan_for,
    publish_request,
    raise_oserror,
)
from tests.livespec_dev_tooling.test_incident_recovery_principal import (
    world as world_fixture,
)

world = world_fixture


def _foreign(world):
    intent = world.intent
    arm = replace(intent.observer_arm, owner="another-owner")
    registration = replace(intent.registration, owner="another-owner")
    return replace(intent, registration=registration, observer_arm=arm)


def _master_untouched(world):
    return world.forge.master() == world.merge and world.forge.count("PATCH", "master") == 0


@pytest.mark.parametrize("operation", ["landed", "authorize", "head", "publish", "conflict"])
def test_forge_operations_refuse_by_name_without_the_recovery_app(world, operation):
    payloads = {
        "landed": lambda: {"intent": asdict(world.intent)},
        "authorize": lambda: {"intent": asdict(world.intent), "scope": asdict(_scope(world))},
        "head": lambda: {"repository": world.installation.repository, "branch": "master"},
        "publish": lambda: {"request": asdict(publish_request(world, plan_for(world)))},
        "conflict": lambda: {"request": asdict(conflict_request(world, head=world.merge))},
    }
    reply = world.call(operation, payloads[operation](), connect=no_app)
    assert reply["status"] == "refused"
    assert reply["code"] == "recovery-app-credential-absent"
    assert _master_untouched(world)


def test_landed_refuses_an_action_the_observer_never_retained(world):
    reply = world.call("landed", {"intent": asdict(_foreign(world))})
    assert reply["status"] == "refused"
    assert "retained" in reply["reason"]


@pytest.mark.parametrize(
    "change",
    [
        {"merged": False},
        {"merge_commit_sha": "e" * 40},
        {"base": {"ref": "release", "sha": "a" * 40}},
        {"head": {"sha": "f" * 40}},
        {"commits": 0},
    ],
)
def test_landed_refuses_a_pull_the_forge_did_not_merge_at_the_registration(world, change):
    world.forge.pull["record"] = {**world.forge.pull["record"], **change}
    reply = world.call("landed", {"intent": asdict(world.intent)})
    assert reply["status"] == "refused"
    assert "landed pull scope" in reply["reason"]


@pytest.mark.parametrize("messages", [["incident: first"], [None, "x"], "not-a-list"])
def test_landed_refuses_a_chain_that_is_not_the_pulls_commits(world, messages):
    world.forge.pull["messages"] = messages
    assert world.call("landed", {"intent": asdict(world.intent)})["status"] == "refused"


def test_legacy_intent_without_an_arm_has_no_provable_scope(world):
    effects = world.principal().effects()
    assert effects.landed(intent=replace(world.intent, observer_arm=None)) is None


def test_authorize_binds_the_retained_grant_and_the_forge_scope(world):
    scope = asdict(_scope(world))
    assert (
        world.call("authorize", {"intent": asdict(world.intent), "scope": scope})["authorized"]
        is True
    )
    other = {**scope, "patch_sha256": "0" * 64}
    assert (
        world.call("authorize", {"intent": asdict(world.intent), "scope": other})["authorized"]
        is False
    )
    unbound = {**scope, "authority_sha256": "0" * 64}
    reply = world.call("authorize", {"intent": asdict(world.intent), "scope": unbound})
    assert reply["status"] == "refused"
    world.record.write_text("{")
    reply = world.call("authorize", {"intent": asdict(world.intent), "scope": scope})
    assert reply["status"] == "refused"
    assert "pending action" in reply["reason"]


def test_head_reads_only_the_observed_master(world):
    reply = world.call("head", {"repository": "owner/repo", "branch": "master"})
    assert reply["head"] == world.merge
    other = world.call("head", {"repository": "owner/other", "branch": "master"})
    assert other["status"] == "refused"
    world.forge.ref_missing = True
    reply = world.call("head", {"repository": "owner/repo", "branch": "master"})
    assert reply["reason"] == "master head unavailable"


def test_publish_refuses_a_message_that_does_not_name_its_action(world):
    request = replace(publish_request(world, plan_for(world)), message="Revert something\n")
    reply = world.call("publish", {"request": asdict(request)})
    assert reply["status"] == "refused"
    assert _master_untouched(world)


def test_publish_against_a_stale_head_answers_head_moved_with_no_attempt(world):
    plan = plan_for(world)
    world.push_later(path="keep.txt", text="moved\n")
    reply = world.call("publish", {"request": asdict(publish_request(world, plan))})
    assert reply["status"] == "head-moved"
    assert not world.ledger.exists()


def test_publish_refuses_a_scope_the_forge_no_longer_proves(world):
    request = publish_request(world, plan_for(world))
    world.forge.pull["record"] = {**world.forge.pull["record"], "merged": False}
    reply = world.call("publish", {"request": asdict(request)})
    assert reply["status"] == "refused"
    assert "landed scope" in reply["reason"]
    assert not world.ledger.exists()


def test_a_different_request_cannot_replace_an_unresolved_attempt(world):
    world.forge.hooks[("PATCH", "master")] = raise_oserror
    world.call("publish", {"request": asdict(publish_request(world, plan_for(world)))})
    other = publish_request(world, plan_for(world))
    other = replace(other, message=other.message + "Incident-Retry: second\n")
    reply = world.call("publish", {"request": asdict(other)})
    assert reply["status"] == "refused"
    assert "unresolved" in reply["reason"]


def test_a_forge_tree_that_differs_from_the_local_inverse_abandons_the_attempt(world):
    world.forge.wrong_tree = True
    reply = world.call("publish", {"request": asdict(publish_request(world, plan_for(world)))})
    assert reply["status"] == "refused"
    assert "exact inverse tree" in reply["reason"]
    attempt = json.loads(world.ledger.read_text())["attempts"][0]
    assert (attempt["status"], attempt["commit"]) == ("abandoned", None)
    assert _master_untouched(world)
    reply = world.call("lookup", {"intent": asdict(world.intent)}, fenced=False)
    assert reply["status"] == "absent"


@pytest.mark.parametrize("failure", ["base", "blob"])
def test_unreadable_base_or_unreproduced_blob_prepares_nothing(world, failure):
    world.forge.broken = failure
    reply = world.call("publish", {"request": asdict(publish_request(world, plan_for(world)))})
    assert reply["status"] == "refused"
    assert world.forge.count("POST", "git/trees") == 0
    assert _master_untouched(world)


def test_crash_before_the_commit_exists_is_provably_inert(world):
    world.forge.hooks[("POST", "trees")] = raise_oserror
    world.call("publish", {"request": asdict(publish_request(world, plan_for(world)))})
    assert json.loads(world.ledger.read_text())["attempts"][0]["status"] == "reserved"
    reply = world.call("lookup", {"intent": asdict(world.intent)}, fenced=False)
    assert reply["status"] == "absent"
    assert json.loads(world.ledger.read_text())["attempts"][0]["status"] == "abandoned"


@pytest.mark.parametrize("answer", ["missing", "error"])
def test_an_unobservable_landing_keeps_the_attempt_reserved(world, answer):
    world.forge.hooks[("PATCH", "master")] = raise_oserror
    world.call("publish", {"request": asdict(publish_request(world, plan_for(world)))})
    world.forge.compare = answer
    reply = world.call("lookup", {"intent": asdict(world.intent)}, fenced=False)
    assert reply["status"] == "reserved"


def test_publish_after_an_owned_conflict_is_refused(world, monkeypatch):
    world.push_later(
        path="shared.txt",
        text=(world.author / "shared.txt").read_text().replace("incident first", "later edit"),
    )
    world.recover(monkeypatch)
    world.push_later(path="shared.txt", text="".join(f"line {n}\n" for n in range(40)))
    reply = world.call("publish", {"request": asdict(publish_request(world, plan_for(world)))})
    assert reply["status"] == "refused"
    assert "another effect" in reply["reason"]


def test_conflict_requires_no_publication_and_the_forge_scope(world):
    world.forge.hooks[("PATCH", "master")] = raise_oserror
    world.call("publish", {"request": asdict(publish_request(world, plan_for(world)))})
    reply = world.call("conflict", {"request": asdict(conflict_request(world, head=world.merge))})
    assert "exists or is unresolved" in reply["reason"]


def test_conflict_scope_must_be_the_forge_scope_and_is_idempotent(world):
    world.push_later(
        path="shared.txt",
        text=(world.author / "shared.txt").read_text().replace("incident first", "later edit"),
    )
    head = world.forge.master()
    request = conflict_request(world, head=head)
    first = world.call("conflict", {"request": asdict(request)})
    assert first["status"] == "recorded"
    assert world.call("conflict", {"request": asdict(request)})["receipt"] == first["receipt"]
    world.forge.pull["record"] = {**world.forge.pull["record"], "merged": False}
    reply = world.call("conflict", {"request": asdict(request)})
    assert "landed scope" in reply["reason"]


@pytest.mark.parametrize(
    "record",
    [
        {"schema": 1, "action_id": "A", "attempts": [{"status": "prepared"}], "receipt": None},
        "receipt",
        "mode",
    ],
)
def test_damaged_publication_records_are_unavailable_never_absent(world, record):
    world.forge.lost_patch_reply = True
    world.call("publish", {"request": asdict(publish_request(world, plan_for(world)))})
    world.forge.lost_patch_reply = False
    world.call("lookup", {"intent": asdict(world.intent)}, fenced=False)
    stored = json.loads(world.ledger.read_text())
    if record == "receipt":
        stored["receipt"]["receipt"] = "recovery-inverse:forged"
    elif record == "mode":
        world.ledger.chmod(0o644)
    else:
        stored = {**record, "action_id": world.intent.action_id}
    if record != "mode":
        world.ledger.write_text(json.dumps(stored))
    reply = world.call("lookup", {"intent": asdict(world.intent)}, fenced=False)
    assert reply["status"] == "refused"


def test_the_ledger_refuses_an_unprotected_directory(world):
    directory = world.installation.state / "recovery-journal"
    directory.chmod(0o755)
    ledger = PublicationLedger(directory=directory)
    held = ledger.hold(action_id="a" * 64)
    with pytest.raises(OSError, match="unprotected"):
        held.__enter__()


def _scope(world):
    return world.principal().effects().landed(intent=world.intent)
