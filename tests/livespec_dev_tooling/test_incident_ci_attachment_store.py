"""Malformed attachment state refuses; it is never treated as empty or repaired."""

from __future__ import annotations

import copy

import pytest

from livespec_dev_tooling._incident_ci_attachment_store import (
    attachment_receipt,
    attachment_tree,
    observation_receipt,
)

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-si6uu7
_BINDING = {
    "repository": "owner/repo",
    "repository_id": 123,
    "repository_owner_id": 456,
    "incident_item_id": "fixture",
    "attempt_id": "repair",
    "operation_id": "operation",
    "generation": 1,
    "owner": "controller",
    "phase": "repair",
    "arm_id": "a" * 64,
    "receipt_digest": "b" * 64,
    "pr_number": 55,
    "base_sha": "e" * 40,
    "head_sha": "c" * 40,
    "merge_sha": "d" * 40,
    "ref": "refs/pull/55/merge",
    "base_ref": "master",
    "head_ref": "repair",
    "caller_workflow_ref": "owner/repo/.github/workflows/ci.yml@refs/pull/55/merge",
    "caller_workflow_sha": "d" * 40,
    "reusable_workflow_ref": "owner/provider/.github/workflows/protected.yml@" + "f" * 40,
    "reusable_workflow_sha": "f" * 40,
    "policy_sha256": "0" * 64,
    "controller_release": "v1",
    "controller_revision": "b" * 40,
    "run_id": 812,
    "run_attempt": 2,
    "job_id": 1011,
    "check_run_id": 913,
    "check_suite_id": 77,
}


def valid():
    receipt = attachment_receipt(binding=_BINDING)
    slot = receipt["attachment_id"]
    observation = {
        "sequence": 1,
        "collection_id": "c1",
        "observed_at": 5,
        "status": "successful",
        "facts": {
            "snapshot_status": "successful",
            "reason": "ok",
            "job_status": "completed",
            "job_conclusion": "success",
            "check_status": "completed",
            "check_conclusion": "success",
        },
    }
    observation["receipt"] = observation_receipt(
        attachment_id=slot, digest=receipt["binding_digest"], observation=observation
    )
    entry = {
        "binding": dict(_BINDING),
        "binding_digest": receipt["binding_digest"],
        "receipt": receipt,
        "attached_at": 1,
        "observations": [observation],
    }
    tree = {
        "schema": 1,
        "attachments": {slot: entry},
        "collections": {"c1": {"attachment_id": slot, "sequence": 1}},
    }
    return {"ci_job_attachments": tree}, slot


def test_absent_subtree_is_empty_and_valid_subtree_round_trips():
    assert attachment_tree(record={}) == {"schema": 1, "attachments": {}, "collections": {}}
    record, _ = valid()
    assert attachment_tree(record=record) == record["ci_job_attachments"]


def _entry(tree, slot):
    return tree["attachments"][slot]


def _observation(tree, slot):
    return _entry(tree, slot)["observations"][0]


MUTATIONS = {
    "tree-type": lambda t, _s: t.clear() or t.update(x=1),
    "schema-bool": lambda t, _s: t.update(schema=True),
    "schema-two": lambda t, _s: t.update(schema=2),
    "attachments-type": lambda t, _s: t.update(attachments=[]),
    "entry-type": lambda t, s: t["attachments"].update({s: []}),
    "entry-key": lambda t, s: _entry(t, s).update(extra=1),
    "binding-bool": lambda t, s: _entry(t, s)["binding"].update(run_id=True),
    "binding-negative": lambda t, s: _entry(t, s)["binding"].update(generation=-1),
    "binding-text": lambda t, s: _entry(t, s)["binding"].update(owner=1),
    "binding-hex": lambda t, s: _entry(t, s)["binding"].update(arm_id="x"),
    "binding-key": lambda t, s: _entry(t, s)["binding"].pop("owner"),
    "binding-changed": lambda t, s: _entry(t, s)["binding"].update(head_ref="other"),
    "digest": lambda t, s: _entry(t, s).update(binding_digest="0" * 64),
    "receipt": lambda t, s: _entry(t, s)["receipt"].update(ci_admission=True),
    "attached-bool": lambda t, s: _entry(t, s).update(attached_at=True),
    "observations-type": lambda t, s: _entry(t, s).update(observations={}),
    "slot": lambda t, s: t["attachments"].update({"0" * 64: t["attachments"].pop(s)}),
    "sequence": lambda t, s: _observation(t, s).update(sequence=2),
    "status": lambda t, s: _observation(t, s).update(status="passed"),
    "collection-id": lambda t, s: _observation(t, s).update(collection_id="-"),
    "observed-bool": lambda t, s: _observation(t, s).update(observed_at=True),
    "facts-key": lambda t, s: _observation(t, s)["facts"].pop("reason"),
    "facts-raw": lambda t, s: _observation(t, s)["facts"].update(job_status="Done!"),
    "facts-snapshot": lambda t, s: _observation(t, s)["facts"].update(snapshot_status="x"),
    "facts-reason": lambda t, s: _observation(t, s)["facts"].update(reason=1),
    "observation-receipt": lambda t, s: _observation(t, s).update(receipt="0" * 64),
    "collections-type": lambda t, _s: t.update(collections=[]),
    "collection-orphan": lambda t, _s: t["collections"].update(c2=t["collections"]["c1"]),
    "collection-missing": lambda t, _s: t["collections"].clear(),
    "collection-attachment": lambda t, _s: t["collections"]["c1"].update(attachment_id="0" * 64),
    "collection-sequence": lambda t, _s: t["collections"]["c1"].update(sequence=2),
    "collection-key": lambda t, _s: t["collections"]["c1"].update(extra=1),
}


@pytest.mark.parametrize("name", sorted(MUTATIONS))
def test_malformed_subtree_refuses(name):
    record, slot = valid()
    record = copy.deepcopy(record)
    MUTATIONS[name](record["ci_job_attachments"], slot)
    with pytest.raises((TypeError, ValueError)):
        attachment_tree(record=record)


def test_non_mapping_subtree_refuses():
    with pytest.raises(TypeError):
        attachment_tree(record={"ci_job_attachments": []})
