"""Pre-merge readiness never invents a future SHA/run or an outage authority."""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import replace

import pytest

from livespec_dev_tooling._incident_observer_store import read_observer_arm
from livespec_dev_tooling._incident_observer_types import (
    JobCallback,
    ObserverArm,
    ObserverArmQuery,
    ObserverRegistration,
)
from livespec_dev_tooling.incident_observer import (
    admit_observer,
    handle_job_callback,
    route_ordinary_action,
)
from livespec_dev_tooling.incident_observer_admission import (
    arm_before_merge,
    bind_after_merge,
    observer_arm_admitted,
)

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-47ij37


@pytest.fixture
def arm():
    return ObserverArm(
        repository="owner/repo",
        incident_item_id="incident-1",
        attempt_id="repair-1",
        operation_id="operation-1",
        generation=1,
        owner="controller",
        phase="repair",
        pr_number=55,
        base_sha="e" * 40,
        head_sha="c" * 40,
        required_jobs=("coverage",),
        controller_release="v1.2.3",
        controller_revision="b" * 40,
        authority_receipt=b"canonical-premerge-receipt",
    )


def _arm(*, directory, arm, expected=None, **overrides):
    args = {
        "directory": directory,
        "arm": arm,
        "expected_arm_id": expected,
        "authorize_current": lambda _: True,
        "released_controller": lambda *_: True,
    }
    args.update(overrides)
    return arm_before_merge(**args)


def _registration(*, arm, **changes):
    args = {
        "repository": arm.repository,
        "incident_item_id": arm.incident_item_id,
        "attempt_id": arm.attempt_id,
        "operation_id": arm.operation_id,
        "generation": arm.generation,
        "owner": arm.owner,
        "phase": arm.phase,
        "head_sha": "a" * 40,
        "run_id": 91,
        "required_jobs": arm.required_jobs,
        "controller_release": arm.controller_release,
        "controller_revision": arm.controller_revision,
        "candidate_revision": arm.head_sha,
        "authority_receipt": arm.authority_receipt,
    }
    args.update(changes)
    return ObserverRegistration(**args)


def _bind(*, directory, arm, registration=None, **overrides):
    args = {
        "directory": directory,
        "arm": arm,
        "registration": registration or _registration(arm=arm),
        "verify_merged_run": lambda *_: True,
    }
    args.update(overrides)
    return bind_after_merge(**args)


def _admitted(*, directory, arm, receipt, **changes):
    args = {
        "repository": arm.repository,
        "arm_id": receipt,
        "pr_number": arm.pr_number,
        "base_sha": arm.base_sha,
        "head_sha": arm.head_sha,
        "receipt_digest": hashlib.sha256(arm.authority_receipt).hexdigest(),
    }
    args.update(changes)
    return observer_arm_admitted(directory=directory, query=ObserverArmQuery(**args))


def test_arm_admits_exact_pr_before_a_master_run_exists(tmp_path, arm):
    ready = _arm(directory=tmp_path, arm=arm)
    assert ready.status == "armed"
    assert _admitted(directory=tmp_path, arm=arm, receipt=ready.receipt)
    assert _arm(directory=tmp_path, arm=arm).receipt == ready.receipt
    assert (
        route_ordinary_action(
            directory=tmp_path,
            repository=arm.repository,
            head_sha=arm.base_sha,
            run_id=1,
            perform=lambda: pytest.fail("pre-merge owner raced"),
        ).status
        == "incident-owned"
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"authorize_current": lambda _: False},
        {"released_controller": lambda *_: False},
    ],
)
def test_arm_needs_live_current_authority_and_real_release_verification(tmp_path, arm, changes):
    assert _arm(directory=tmp_path, arm=arm, **changes).status == "refused"


@pytest.mark.parametrize(
    "changes",
    [
        {"authority_receipt": b""},
        {"required_jobs": ()},
        {"phase": "closed"},
        {"controller_revision": "c" * 40},
    ],
)
def test_incomplete_historical_or_candidate_controller_cannot_arm(tmp_path, arm, changes):
    assert _arm(directory=tmp_path, arm=replace(arm, **changes)).status == "refused"


@pytest.mark.parametrize(
    "changes",
    [
        {"arm_id": "forged"},
        {"pr_number": 56},
        {"base_sha": "f" * 40},
        {"head_sha": "d" * 40},
        {"receipt_digest": "0" * 64},
    ],
)
def test_merge_entrance_rejects_forged_or_changed_arm(tmp_path, arm, changes):
    ready = _arm(directory=tmp_path, arm=arm)
    assert not _admitted(directory=tmp_path, arm=arm, receipt=ready.receipt, **changes)


def test_missing_or_corrupt_arm_never_admits_a_merge(tmp_path, arm):
    assert not _admitted(directory=tmp_path, arm=arm, receipt="missing")
    ready = _arm(directory=tmp_path, arm=arm)
    path = next(tmp_path.glob("*.json"))
    record = json.loads(path.read_bytes())
    record["observer_arm"] = []
    path.write_text(json.dumps(record))
    assert not _admitted(directory=tmp_path, arm=arm, receipt=ready.receipt)


def test_missing_cached_canonical_receipt_never_admits_merge(tmp_path, arm):
    ready = _arm(directory=tmp_path, arm=arm)
    path = next(tmp_path.glob("*.json"))
    record = json.loads(path.read_bytes())
    record["observer_arm"]["authority_receipt"] = None
    path.write_text(json.dumps(record))
    assert not _admitted(directory=tmp_path, arm=arm, receipt=ready.receipt)


def test_binding_fulfills_retained_grant_through_tenant_and_wrapper_outage(tmp_path, arm):
    ready = _arm(directory=tmp_path, arm=arm)
    # The post-merge API has no tenant/credential-wrapper input to call again.
    assert _bind(directory=tmp_path, arm=arm).status == "admitted"
    assert _bind(directory=tmp_path, arm=arm).status == "admitted"
    assert not _admitted(directory=tmp_path, arm=arm, receipt=ready.receipt)
    assert (
        _bind(directory=tmp_path, arm=arm, registration=_registration(arm=arm, run_id=92)).status
        == "refused"
    )


def test_low_level_new_admission_cannot_overwrite_a_retained_arm(tmp_path, arm):
    _arm(directory=tmp_path, arm=arm)
    result = admit_observer(
        directory=tmp_path,
        registration=_registration(arm=arm),
        expected_generation=None,
        authorize_current=lambda _: True,
        released_controller=lambda *_: True,
    )
    assert result.status == "refused"


@pytest.mark.parametrize(
    "changes",
    [
        {"repository": "owner/other"},
        {"incident_item_id": "other"},
        {"controller_revision": "f" * 40},
        {"generation": 2},
        {"operation_id": "other"},
        {"phase": "master-observation"},
        {"authority_receipt": b"invented-postmerge-receipt"},
        {"candidate_revision": "f" * 40},
        {"required_jobs": ("other",)},
    ],
)
def test_binding_cannot_invent_new_authority_or_change_armed_scope(tmp_path, arm, changes):
    _arm(directory=tmp_path, arm=arm)
    assert (
        _bind(directory=tmp_path, arm=arm, registration=_registration(arm=arm, **changes)).status
        == "refused"
    )


def test_unverified_merge_or_absent_premerge_arm_cannot_bind(tmp_path, arm):
    assert _bind(directory=tmp_path, arm=arm).status == "refused"
    _arm(directory=tmp_path, arm=arm)
    assert (
        _bind(directory=tmp_path, arm=arm, verify_merged_run=lambda *_: False).status == "refused"
    )


def test_arm_compare_and_swap_fences_delayed_binding_of_an_old_attempt(tmp_path, arm):
    first = _arm(directory=tmp_path, arm=arm)
    second = replace(arm, generation=2, operation_id="operation-2", head_sha="d" * 40)
    assert _arm(directory=tmp_path, arm=second).status == "refused"
    assert (
        _arm(directory=tmp_path, arm=replace(arm, head_sha="d" * 40), expected=first.receipt).status
        == "refused"
    )
    assert _arm(directory=tmp_path, arm=second, expected=first.receipt).status == "armed"
    assert _bind(directory=tmp_path, arm=arm).status == "refused"


def test_pending_unknown_effect_cannot_be_discarded_by_corrected_premerge_arm(tmp_path, arm):
    ready = _arm(directory=tmp_path, arm=arm)
    _bind(directory=tmp_path, arm=arm)
    raw = json.dumps(
        {
            "action": "completed",
            "repository": {"full_name": arm.repository},
            "workflow_job": {
                "id": 92,
                "run_id": 91,
                "head_sha": "a" * 40,
                "head_branch": "master",
                "name": "coverage",
                "status": "completed",
                "conclusion": "failure",
            },
        }
    ).encode()
    secret = b"controller-fixture"
    delivery = JobCallback(
        body=raw,
        signature="sha256=" + hmac.new(secret, raw, hashlib.sha256).hexdigest(),
        event="workflow_job",
        delivery_id="one",
    )
    assert (
        handle_job_callback(
            directory=tmp_path, delivery=delivery, webhook_secret=secret, recover=lambda _: None
        ).status
        == "pending"
    )
    assert (
        _arm(directory=tmp_path, arm=replace(arm, generation=2), expected=ready.receipt).status
        == "refused"
    )


@pytest.mark.parametrize(
    "corrupt",
    [
        [],
        {"generation": True},
        {"required_jobs": "coverage"},
        {"required_jobs": [1]},
        {"unknown": "extra"},
    ],
)
def test_corrupt_cached_arm_never_reaches_inverse_effect(tmp_path, arm, corrupt):
    _arm(directory=tmp_path, arm=arm)
    _bind(directory=tmp_path, arm=arm)
    path = next(tmp_path.glob("*.json"))
    record = json.loads(path.read_bytes())
    if isinstance(corrupt, dict):
        record["observer_arm"].update(corrupt)
        record["observer_arm_id"] = hashlib.sha256(
            json.dumps(record["observer_arm"], sort_keys=True).encode()
        ).hexdigest()
    else:
        record["observer_arm"] = corrupt
    path.write_text(json.dumps(record))
    with pytest.raises(TypeError, match="invalid"):
        read_observer_arm(record=record)


def test_cached_arm_digest_mismatch_is_not_authority(tmp_path, arm):
    _arm(directory=tmp_path, arm=arm)
    record = json.loads(next(tmp_path.glob("*.json")).read_bytes())
    record["observer_arm"]["head_sha"] = "f" * 40
    with pytest.raises(ValueError, match="invalid"):
        read_observer_arm(record=record)
