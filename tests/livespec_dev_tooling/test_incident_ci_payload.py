"""Incident packets are consistency checks, with exact types and immutable arm ids."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from typing import Any

import pytest

from livespec_dev_tooling import incident_ci_payload as module


def packet() -> dict[str, Any]:
    arm = dict(
        repository="owner/repo",
        incident_item_id="incident-1",
        attempt_id="attempt-1",
        operation_id="repair-1",
        generation=1,
        owner="operator:alice",
        phase="repair",
        pr_number=7,
        base_sha="a" * 40,
        head_sha="b" * 40,
        required_jobs=["check-lint"],
        controller_release="v1.0.0",
        controller_revision="c" * 40,
        authority_receipt=b"actual-controlled-receipt".hex(),
    )
    return dict(
        schema=1,
        arm=arm,
        observer_arm_id=hashlib.sha256(json.dumps(arm, sort_keys=True).encode()).hexdigest(),
    )


def outcome() -> dict[str, str]:
    return dict(name="check-fast", head_sha="b" * 40, scope="c" * 64, outcome="passed")


def test_exact_packet_projects_six_query_fields_and_absent_identity_refuses():
    value = module.decode_authority(payload=json.dumps(packet()))
    assert value is not None
    query = module.query_for(authority=value)
    assert set(query) == {
        "repository",
        "arm_id",
        "pr_number",
        "base_sha",
        "head_sha",
        "receipt_digest",
    }
    assert query["arm_id"] == packet()["observer_arm_id"]
    with pytest.raises(ValueError, match="no identity"):
        module.query_for(authority=replace(value, context=replace(value.context, identity=None)))


@pytest.mark.parametrize(
    "value",
    [
        [],
        {},
        {"schema": True},
        packet() | {"schema": 2},
        packet() | {"arm": []},
        packet() | {"observer_arm_id": "forged"},
    ],
)
def test_unbound_packet_is_never_authority(value):
    assert module.decode_authority(payload=json.dumps(value)) is None


@pytest.mark.parametrize(
    "change", [{"generation": True}, {"authority_receipt": "invalid"}, {"extra": "unknown"}]
)
def test_arm_codec_refusals_propagate(change):
    data = packet()
    data["arm"].update(change)
    data["observer_arm_id"] = hashlib.sha256(
        json.dumps(data["arm"], sort_keys=True).encode()
    ).hexdigest()
    assert module.decode_authority(payload=json.dumps(data)) is None


def test_missing_or_duplicate_json_keys_and_decoder_refusal(monkeypatch):
    for text in ("{bad", '{"schema":1,"schema":1}', "x" * 16385):
        assert module.decode_authority(payload=text) is None
    monkeypatch.setattr(module, "read_observer_arm", lambda **_: None)
    assert module.decode_authority(payload=json.dumps(packet())) is None


@pytest.mark.parametrize(
    "value",
    [
        None,
        [],
        {},
        outcome() | {"extra": "x"},
        outcome() | {"name": 1},
        outcome() | {"name": "--help"},
        outcome() | {"head_sha": "x"},
        outcome() | {"scope": "x"},
        outcome() | {"outcome": "unknown"},
    ],
)
def test_unknown_outcomes_and_invalid_identities_refuse(value):
    with pytest.raises(ValueError, match="invalid incident CI outcome"):
        module.decode_outcome(value=value)


@pytest.mark.parametrize("status", ["passed", "failed", "cancelled", "skipped", "timed_out"])
def test_declared_outcomes_remain_explicit(status):
    assert module.decode_outcome(value=outcome() | {"outcome": status}).outcome == status
