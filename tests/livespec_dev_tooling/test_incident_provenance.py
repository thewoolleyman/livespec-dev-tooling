"""The canonical process boundary is required even on ordinary normal master."""

from __future__ import annotations

import copy
import json
import subprocess
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

import pytest
from returns.pipeline import is_successful
from returns.unsafe import unsafe_perform_io

from livespec_dev_tooling import incident_provenance as provenance

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-gvylzw


def _query() -> provenance.IncidentCommitQuery:
    return provenance.IncidentCommitQuery(
        repository="owner/repo",
        item_id="incident-1",
        attempt_id="attempt-2",
        phase="repair",
        operation_id="operation-3",
        generation=4,
        owner="operator-5",
        base="a" * 40,
        head="b" * 40,
        pr_number=6,
        commit_sha="c" * 40,
        tree_sha="d" * 40,
    )


def _reply() -> dict[str, Any]:
    attempt = asdict(_query())
    del attempt["commit_sha"]
    del attempt["tree_sha"]
    attempt.update(
        landed_commits=["c" * 40, "e" * 40],
        landed_trees=["d" * 40, "f" * 40],
        original_paths=["src/repair.py"],
        deferred_work=["full-replay"],
        repayment_required=True,
    )
    return {
        "schema": 1,
        "status": "verified",
        "result": {
            "attempt": attempt,
            "committed_token_id": "token-old",
            "current_token_id": "token-current",
            "is_current": False,
        },
        "authorizes_current_effects": False,
        "normal_factory_proof": False,
    }


def _registered(**_: object) -> Path:
    return Path("/registered/plugin")


def _install(
    monkeypatch: pytest.MonkeyPatch, *, reply: dict[str, Any], returncode: int = 0
) -> list[list[str]]:
    calls: list[list[str]] = []
    monkeypatch.setattr(provenance, "registered_plugin_root", _registered)

    def run(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(
            args=argv, returncode=returncode, stdout=json.dumps(reply), stderr=""
        )

    monkeypatch.setattr(provenance.subprocess, "run", run)
    return calls


def test_historical_read_uses_registered_producer_and_retains_deferred_proof(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _install(monkeypatch, reply=_reply())
    result = provenance.read_historical_incident_commit(repo_root=Path("/checkout"), query=_query())
    assert is_successful(result)
    proof = unsafe_perform_io(result.unwrap())
    assert proof.query == _query()
    assert proof.committed_token_id == "token-old"
    assert proof.current_token_id == "token-current"
    assert proof.original_paths == ("src/repair.py",)
    assert proof.deferred_work == ("full-replay",)
    assert proof.repayment_required is True
    assert calls[0][:4] == [
        "/usr/local/bin/with-livespec-env.sh",
        "--",
        "python3",
        "/registered/plugin/scripts/bin/incident_authority.py",
    ]
    assert calls[0][4] == "read-history"
    for name, expected in [
        ("repository", "owner/repo"),
        ("item", "incident-1"),
        ("attempt", "attempt-2"),
        ("phase", "repair"),
        ("operation", "operation-3"),
        ("owner", "operator-5"),
        ("generation", "4"),
    ]:
        assert calls[0][calls[0].index("--" + name) + 1] == expected


@pytest.mark.parametrize(
    "field",
    [
        "repository",
        "item_id",
        "attempt_id",
        "phase",
        "operation_id",
        "generation",
        "owner",
        "base",
        "head",
        "pr_number",
    ],
)
def test_exact_receipt_fields_must_match(monkeypatch: pytest.MonkeyPatch, field: str) -> None:
    reply = _reply()
    reply["result"]["attempt"][field] = "foreign"
    _ = _install(monkeypatch, reply=reply)
    result = provenance.read_historical_incident_commit(repo_root=Path("/checkout"), query=_query())
    assert unsafe_perform_io(result.failure()).code == "incident-provenance-identity-mismatch"


@pytest.mark.parametrize("mutate", ["commit", "tree", "length", "bool_generation", "bool_pr"])
def test_landed_commit_and_tree_are_verified_as_one_pair(
    monkeypatch: pytest.MonkeyPatch, mutate: str
) -> None:
    reply = _reply()
    attempt = reply["result"]["attempt"]
    if mutate == "commit":
        attempt["landed_commits"][0] = "x" * 40
    elif mutate == "tree":
        attempt["landed_trees"].reverse()
    elif mutate == "length":
        attempt["landed_trees"] = []
    elif mutate == "bool_generation":
        attempt["generation"] = True
    else:
        attempt["pr_number"] = True
    _ = _install(monkeypatch, reply=reply)
    result = provenance.read_historical_incident_commit(repo_root=Path("/checkout"), query=_query())
    assert not is_successful(result)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema", True),
        ("schema", 2),
        ("status", "normal"),
        ("authorizes_current_effects", True),
        ("normal_factory_proof", True),
    ],
)
def test_historical_result_never_grants_current_or_normal_authority(
    monkeypatch: pytest.MonkeyPatch, field: str, value: object
) -> None:
    reply = _reply()
    reply[field] = value
    _ = _install(monkeypatch, reply=reply)
    result = provenance.read_historical_incident_commit(repo_root=Path("/checkout"), query=_query())
    assert unsafe_perform_io(result.failure()).code == "incident-reader-invalid-response"


def test_canonical_refusal_is_preserved(monkeypatch: pytest.MonkeyPatch) -> None:
    reply = copy.deepcopy(_reply())
    reply.update(
        status="refused",
        result={"code": "incident-authority-missing", "detail": "no sanctioned chain"},
    )
    _ = _install(monkeypatch, reply=reply, returncode=78)
    result = provenance.read_historical_incident_commit(repo_root=Path("/checkout"), query=_query())
    assert unsafe_perform_io(result.failure()).code == "incident-authority-missing"


def test_missing_registered_reader_has_no_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(**_: object) -> Path:
        raise OSError("reader is not installed")

    monkeypatch.setattr(provenance, "registered_plugin_root", missing)
    result = provenance.read_historical_incident_commit(repo_root=Path("/checkout"), query=_query())
    assert unsafe_perform_io(result.failure()).code == "incident-reader-unavailable"


@pytest.mark.parametrize("raw", ["not JSON", "[]", "{}", '{"schema": 1, "schema": 1}'])
def test_unreadable_process_reply_is_refused(monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
    monkeypatch.setattr(provenance, "registered_plugin_root", _registered)

    def raw_run(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=argv, returncode=0, stdout=raw, stderr="")

    monkeypatch.setattr(provenance.subprocess, "run", raw_run)
    result = provenance.read_historical_incident_commit(repo_root=Path("/checkout"), query=_query())
    assert unsafe_perform_io(result.failure()).code == "incident-reader-invalid-response"


def test_reader_timeout_is_unavailable_instead_of_normal_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(provenance, "registered_plugin_root", _registered)

    def expired(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(cmd="canonical reader", timeout=30)

    monkeypatch.setattr(provenance.subprocess, "run", expired)
    result = provenance.read_historical_incident_commit(repo_root=Path("/checkout"), query=_query())
    assert unsafe_perform_io(result.failure()).code == "incident-reader-unavailable"


@pytest.mark.parametrize("field", ["attempt", "committed_token_id", "current_token_id"])
def test_incomplete_historical_proof_is_refused(
    monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    reply = _reply()
    del reply["result"][field]
    _ = _install(monkeypatch, reply=reply)
    result = provenance.read_historical_incident_commit(repo_root=Path("/checkout"), query=_query())
    assert unsafe_perform_io(result.failure()).code == "incident-reader-invalid-response"


def test_a_crashed_producer_cannot_supply_a_verified_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = _install(monkeypatch, reply=_reply(), returncode=1)
    result = provenance.read_historical_incident_commit(repo_root=Path("/checkout"), query=_query())
    assert unsafe_perform_io(result.failure()).code == "incident-reader-unavailable"


def test_a_later_landed_commit_is_not_reduced_to_the_terminal_sha(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = _install(monkeypatch, reply=_reply())
    query = replace(_query(), commit_sha="e" * 40, tree_sha="f" * 40)
    result = provenance.read_historical_incident_commit(repo_root=Path("/checkout"), query=query)
    assert is_successful(result)
    assert unsafe_perform_io(result.unwrap()).query == query


def test_history_can_read_the_current_generation_without_authorizing_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reply = _reply()
    reply["result"]["is_current"] = True
    _ = _install(monkeypatch, reply=reply)
    result = provenance.read_historical_incident_commit(repo_root=Path("/checkout"), query=_query())
    assert is_successful(result)
    assert unsafe_perform_io(result.unwrap()).deferred_work == ("full-replay",)


def test_duplicate_keys_cannot_hide_inside_an_otherwise_verified_reply(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(provenance, "registered_plugin_root", _registered)
    raw = json.dumps(_reply()).replace('"schema": 1', '"schema": 1, "schema": 1')

    def raw_run(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=argv, returncode=0, stdout=raw, stderr="")

    monkeypatch.setattr(provenance.subprocess, "run", raw_run)
    result = provenance.read_historical_incident_commit(repo_root=Path("/checkout"), query=_query())
    assert unsafe_perform_io(result.failure()).code == "incident-reader-invalid-response"
