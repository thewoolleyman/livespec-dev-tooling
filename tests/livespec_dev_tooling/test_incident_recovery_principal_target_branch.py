"""The recovery principal acts on the target branch its installation configuration names.

A principal configured for a scratch branch (livespec-dev-tooling-thhgeg) publishes
and merges its inverse there, recomputes against that branch's moved head, answers
`head` only for that branch, and refuses an action registered for any other branch
instead of falling back to master. With no target named, master is the default.
"""

from __future__ import annotations

import json
from dataclasses import asdict, replace

import pytest

from tests.livespec_dev_tooling.test_incident_recovery_principal import (
    REPOSITORY,
    build_world,
    conflict_request,
    git,
    plan_for,
    publish_request,
)

SCRATCH = "drill/recovery-scratch"


@pytest.fixture
def scratch(tmp_path):
    return build_world(tmp_path=tmp_path, branch=SCRATCH)


def test_principal_configured_for_a_scratch_branch_merges_the_inverse_there(scratch, monkeypatch):
    master_before = git(scratch.bare, "rev-parse", "refs/heads/master")
    outcome = scratch.recovered(monkeypatch)
    assert outcome.status == "reverted", outcome
    head = scratch.forge.master()
    assert git(scratch.bare, "rev-parse", head + "^") == scratch.merge
    assert git(scratch.bare, "rev-parse", head + "^{tree}") == git(
        scratch.bare, "rev-parse", scratch.before + "^{tree}"
    )
    assert outcome.receipt == f"recovery-inverse:{scratch.intent.action_id}:commit:{head}"
    assert git(scratch.bare, "rev-parse", "refs/heads/master") == master_before
    assert scratch.forge.count("PATCH", f"git/refs/heads/{SCRATCH}") == 1
    assert scratch.forge.count("PATCH", "git/refs/heads/master") == 0
    assert len(scratch.reverts()) == 1


def test_moved_scratch_head_with_genuine_overlap_is_an_owned_rollback_conflict(
    scratch, monkeypatch
):
    scratch.push_later(
        path="shared.txt",
        text=(scratch.author / "shared.txt").read_text().replace("incident first", "later edit"),
    )
    head = scratch.forge.master()
    outcome = scratch.recovered(monkeypatch)
    owner = scratch.intent.registration.owner
    assert outcome.status == "rollback-conflict", outcome
    assert (
        outcome.receipt == f"rollback-conflict:{scratch.intent.action_id}:owner:{owner}:head:{head}"
    )
    assert scratch.forge.master() == head
    assert scratch.forge.count("PATCH", f"git/refs/heads/{SCRATCH}") == 0


def test_moved_scratch_head_without_overlap_is_recomputed_and_preserves_later_work(
    scratch, monkeypatch
):
    scratch.forge.hooks[("POST", "trees")] = lambda: scratch.push_later(
        path="keep.txt", text="kept and later changed\n"
    )
    outcome = scratch.recovered(monkeypatch)
    assert outcome.status == "reverted", outcome
    head = scratch.forge.master()
    assert git(scratch.bare, "show", f"{head}:keep.txt") == "kept and later changed"
    assert len(scratch.reverts()) == 1
    assert scratch.forge.count("PATCH", f"git/refs/heads/{SCRATCH}") == 2


def test_scratch_publication_is_journaled_once_across_a_principal_restart(scratch):
    scratch.forge.lost_patch_reply = True
    request = {"request": asdict(publish_request(scratch, plan_for(scratch)))}
    assert scratch.call("publish", request)["status"] == "unknown"
    merged = scratch.forge.master()
    scratch.forge.lost_patch_reply = False
    restarted = scratch.call("publish", request)
    assert (restarted["status"], restarted["merge_sha"]) == ("committed", merged)
    lookup = scratch.call("lookup", {"intent": asdict(scratch.intent)})
    assert lookup["status"] == "recorded"
    assert scratch.forge.count("POST", "git/commits") == 1
    assert scratch.reverts() == [f"{merged} Revert complete incident PR #71"]
    assert json.loads(scratch.ledger.read_text())["attempts"][-1]["commit"] == merged


def test_scratch_principal_answers_head_only_for_its_configured_branch(scratch):
    own = scratch.call("head", {"repository": REPOSITORY, "branch": SCRATCH})
    assert own["head"] == scratch.forge.master()
    other = scratch.call("head", {"repository": REPOSITORY, "branch": "master"})
    assert other["status"] == "refused"
    assert scratch.forge.count("GET", "git/ref/heads/master") == 0


def test_scratch_principal_refuses_an_action_registered_for_master(scratch):
    master_intent = replace(
        scratch.intent,
        registration=replace(scratch.intent.registration, branch="master"),
        completion=replace(scratch.intent.completion, branch="master"),
    )
    reply = scratch.call("landed", {"intent": asdict(master_intent)})
    assert reply["status"] == "refused"
    assert scratch.forge.count("GET", "pulls/71") == 0


def test_default_principal_refuses_an_action_registered_for_a_scratch_branch(scratch):
    request = {"request": asdict(publish_request(scratch, plan_for(scratch)))}
    conflict = {"request": asdict(conflict_request(scratch, head=scratch.merge))}
    scratch.installation = replace(scratch.installation, target_branch="master")
    assert (
        scratch.call("head", {"repository": REPOSITORY, "branch": SCRATCH})["status"] == "refused"
    )
    for operation in ("landed", "lookup"):
        reply = scratch.call(operation, {"intent": asdict(scratch.intent)})
        assert reply["status"] == "refused", (operation, reply)
    assert scratch.call("publish", request)["status"] == "refused"
    assert scratch.call("conflict", conflict)["status"] == "refused"
    assert scratch.forge.count("POST", "git/commits") == 0
