"""Failures and principal protocol branches beyond the checksum-bound Red file."""

from __future__ import annotations

import base64
import json
import subprocess
import sys
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from returns.io import IOFailure, IOSuccess
from returns.unsafe import unsafe_perform_io

import livespec_dev_tooling.incident_inverse as inverse
import livespec_dev_tooling.incident_inverse_service as service
from livespec_dev_tooling._incident_inverse_types import (
    InverseConflictRequest,
    InversePublishRequest,
)
from livespec_dev_tooling.incident_git import IncidentGitError

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_incident_inverse import Forge, _intent
from test_incident_inverse import history as history_fixture


@pytest.fixture
def history(tmp_path):
    return history_fixture.__wrapped__(tmp_path)


def test_missing_source_is_refusal_not_a_conflict(tmp_path, history):
    _, scope, _ = history
    result = inverse.plan_incident_inverse(
        repo_root=tmp_path / "absent", scope=scope, expected_head=scope.merge_sha
    )
    assert isinstance(result, IOFailure)
    assert unsafe_perform_io(result.failure()).code == "invalid-incident-scope"


@pytest.mark.parametrize(
    "failure",
    [
        OSError("unavailable disk"),
        subprocess.CalledProcessError(128, ["git", "write-tree"], stderr=b"cannot write index"),
        subprocess.CalledProcessError(1, ["git", "write-tree"]),
        subprocess.TimeoutExpired("git", 15),
        UnicodeError("invalid output"),
    ],
)
def test_build_errors_are_unavailable_not_owned_overlap(history, monkeypatch, failure):
    repo, scope, _ = history

    def fail(**_kwargs):
        raise failure

    monkeypatch.setattr(inverse, "build_inverse", fail)
    result = inverse.plan_incident_inverse(
        repo_root=repo, scope=scope, expected_head=scope.merge_sha
    )
    assert isinstance(result, IOFailure)
    assert unsafe_perform_io(result.failure()).code == "inverse-unavailable"


@pytest.mark.parametrize(
    ("failure", "code", "detail"),
    [
        (
            IncidentGitError(
                reason="incident git apply exited 1: conflict",
                cmd=("git", "apply", "--3way"),
                returncode=1,
                stderr=b"patch does not apply",
            ),
            "rollback-conflict",
            "patch does not apply",
        ),
        (
            IncidentGitError(
                reason="incident git write-tree exited 128: no index",
                cmd=("git", "write-tree"),
                returncode=128,
                stderr=b"no index",
            ),
            "inverse-unavailable",
            "no index",
        ),
        (
            IncidentGitError(
                reason="incident git apply exceeded its 120 s ceiling",
                cmd=("git", "apply"),
                returncode=None,
                stderr=b"",
            ),
            "inverse-unavailable",
            "incident git apply exceeded its 120 s ceiling",
        ),
    ],
)
def test_one_incident_git_failure_is_classified_by_its_exit_and_command(
    history, monkeypatch, failure, code, detail
):
    repo, scope, _ = history

    def fail(**_kwargs):
        raise failure

    monkeypatch.setattr(inverse, "build_inverse", fail)
    result = inverse.plan_incident_inverse(
        repo_root=repo, scope=scope, expected_head=scope.merge_sha
    )
    refusal = unsafe_perform_io(result.failure())
    assert (refusal.code, refusal.detail) == (code, detail)


@pytest.mark.parametrize(
    "failure",
    [
        OSError("service unavailable"),
        subprocess.TimeoutExpired("principal", 15),
        ValueError("invalid receipt"),
    ],
)
def test_principal_failure_never_attempts_publication(history, monkeypatch, failure):
    repo, scope, _ = history
    forge = Forge(repo=repo, scope=scope)

    def fail(**_kwargs):
        raise failure

    monkeypatch.setattr(forge, "read_exact_receipt", fail)
    result = inverse.recover_incident_inverse(repo_root=repo, intent=_intent(scope), forge=forge)
    assert isinstance(result, IOFailure)
    assert unsafe_perform_io(result.failure()).code == "inverse-unavailable"
    assert not forge.requests


def test_invalid_complete_chain_is_refused_even_with_terminal_sha(history):
    repo, scope, _ = history
    incomplete = replace(
        scope, landed_commits=(scope.merge_sha,), landed_trees=(scope.landed_trees[-1],)
    )
    result = inverse.plan_incident_inverse(
        repo_root=repo, scope=incomplete, expected_head=scope.merge_sha
    )
    assert isinstance(result, IOFailure)
    assert unsafe_perform_io(result.failure()).code == "invalid-incident-scope"


def test_non_conflict_planning_refusal_propagates_without_effect(history):
    repo, scope, _ = history
    forge = Forge(repo=repo, scope=replace(scope, patch_sha256="0" * 64))
    result = inverse.recover_incident_inverse(repo_root=repo, intent=_intent(scope), forge=forge)
    assert isinstance(result, IOFailure)
    assert unsafe_perform_io(result.failure()).code == "invalid-incident-scope"
    assert not forge.requests
    assert not forge.conflicts


def test_unknown_response_with_exact_receipt_recovers_once(history):
    repo, scope, _ = history
    forge = Forge(repo=repo, scope=scope)
    original = forge.publish_inverse

    def publish(*, request):
        _ = original(request=request)
        return replace(original_result, status="unknown")

    from livespec_dev_tooling._incident_inverse_types import InversePublishResult

    original_result = InversePublishResult(status="unknown")
    forge.publish_inverse = publish
    result = inverse.recover_incident_inverse(repo_root=repo, intent=_intent(scope), forge=forge)
    assert isinstance(result, IOSuccess)
    assert unsafe_perform_io(result.unwrap()).receipt == forge.receipt
    assert len(forge.requests) == 1


def test_host_rpc_uses_immutable_intent_complete_scope_and_binary_inverse(history, monkeypatch):
    repo, scope, _ = history
    intent = _intent(scope)
    plan = unsafe_perform_io(
        inverse.plan_incident_inverse(
            repo_root=repo, scope=scope, expected_head=scope.merge_sha
        ).unwrap()
    )
    calls = []

    def run(command, **kwargs):
        body = json.loads(kwargs["input"])
        calls.append((command, kwargs, body))
        reply = {"schema": 1, "operation": body["operation"], "binding": body["binding"]}
        if body["operation"] == "landed":
            reply["scope"] = asdict(scope)
        elif body["operation"] == "authorize":
            reply["authorized"] = True
        elif body["operation"] == "head":
            reply["head"] = scope.merge_sha
        elif body["operation"] == "publish":
            reply.update(status="committed", merge_sha="e" * 40, tree_sha=plan.tree_sha)
        else:
            reply["receipt"] = "exact-effect"
            reply["status"] = "recorded"
        return SimpleNamespace(returncode=0, stdout=json.dumps(reply).encode())

    monkeypatch.setattr(service.subprocess, "run", run)
    principal = service.ProcessInverseForge(command=("/trusted/controller", "inverse-rpc"))
    assert principal.landed_incident(intent=intent) == scope
    assert principal.authorize_inverse(intent=intent, scope=scope)
    assert (
        principal.read_master_head(repository=scope.repository, branch="master") == scope.merge_sha
    )
    assert principal.read_exact_receipt(intent=intent) == "exact-effect"
    published = principal.publish_inverse(
        request=InversePublishRequest(intent=intent, plan=plan, message="inverse")
    )
    assert published.status == "committed" and published.tree_sha == plan.tree_sha
    assert (
        principal.record_conflict(
            request=InverseConflictRequest(
                intent=intent,
                scope=scope,
                expected_head=scope.merge_sha,
                reason="overlap",
                receipt="owned",
            )
        )
        == "exact-effect"
    )
    assert len(calls) == 6
    _assert_host_calls(calls=calls, intent=intent, plan=plan)


def _assert_host_calls(*, calls, intent, plan):
    for command, kwargs, body in calls:
        assert command == ["/trusted/controller", "inverse-rpc"]
        assert kwargs["timeout"] == 15
        assert kwargs["check"] is False
        assert "shell" not in kwargs
        assert body["schema"] == 1
    assert calls[0][2]["intent"]["action_id"] == intent.action_id
    assert (
        base64.b64decode(calls[0][2]["intent"]["registration"]["authority_receipt"])
        == intent.registration.authority_receipt
    )
    assert base64.b64decode(calls[4][2]["request"]["plan"]["inverse_patch"]) == plan.inverse_patch


@pytest.mark.parametrize(
    "answer",
    [
        None,
        [],
        {},
        {"schema": 2, "operation": "lookup"},
        {"schema": 1, "operation": "other"},
        {"schema": 1, "operation": "lookup", "receipt": ""},
        {"schema": 1, "operation": "lookup", "receipt": 7},
    ],
)
def test_missing_or_malformed_rpc_receipt_is_not_retry_authority(history, monkeypatch, answer):
    _, scope, _ = history
    monkeypatch.setattr(
        service.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout=json.dumps(answer).encode()),
    )
    with pytest.raises(OSError, match="publication refused"):
        service.ProcessInverseForge(command=("trusted",)).read_exact_receipt(intent=_intent(scope))


@pytest.mark.parametrize(("stdout", "returncode"), [(b"not json", 0), (b"{}", 7)])
def test_rpc_process_failure_is_unknown(history, monkeypatch, stdout, returncode):
    _, scope, _ = history
    monkeypatch.setattr(
        service.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=returncode, stdout=stdout),
    )
    with pytest.raises(OSError, match="publication refused"):
        service.ProcessInverseForge(command=("trusted",)).read_exact_receipt(intent=_intent(scope))


@pytest.mark.parametrize("failure", [OSError("down"), subprocess.TimeoutExpired("principal", 15)])
def test_rpc_transport_failure_is_unknown(history, monkeypatch, failure):
    _, scope, _ = history

    def run(*_args, **_kwargs):
        raise failure

    monkeypatch.setattr(service.subprocess, "run", run)
    with pytest.raises(OSError, match="publication refused"):
        service.ProcessInverseForge(command=("trusted",)).read_exact_receipt(intent=_intent(scope))


@pytest.mark.parametrize(("command", "seconds"), [((), 15), (("trusted",), 0), (("trusted",), 60)])
def test_no_command_or_unbounded_transport_never_calls_principal(
    history, monkeypatch, command, seconds
):
    _, scope, _ = history
    monkeypatch.setattr(
        service.subprocess, "run", lambda *_args, **_kwargs: pytest.fail("invalid transport")
    )
    with pytest.raises(OSError, match="publication refused"):
        service.ProcessInverseForge(command=command, timeout_seconds=seconds).read_exact_receipt(
            intent=_intent(scope)
        )


@pytest.mark.parametrize(
    "scope_change",
    [
        {"pr_number": "71"},
        {"landed_commits": "terminal"},
        {"changed_paths": [7]},
        {"repository": 3},
        {"extra": "forged"},
    ],
)
def test_rpc_landed_scope_requires_complete_typed_fields(history, monkeypatch, scope_change):
    _, scope, _ = history
    data = json.loads(json.dumps(asdict(scope)))
    data.update(scope_change)
    monkeypatch.setattr(
        service.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "schema": 1,
                    "operation": "landed",
                    "binding": json.loads(_kwargs["input"])["binding"],
                    "scope": data,
                }
            ).encode(),
        ),
    )
    assert (
        service.ProcessInverseForge(command=("trusted",)).landed_incident(intent=_intent(scope))
        is None
    )


def test_rpc_missing_scope_and_unknown_publish_are_conservative(history, monkeypatch):
    repo, scope, _ = history
    plan = unsafe_perform_io(
        inverse.plan_incident_inverse(
            repo_root=repo, scope=scope, expected_head=scope.merge_sha
        ).unwrap()
    )
    monkeypatch.setattr(
        service.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout=b"null"),
    )
    principal = service.ProcessInverseForge(command=("trusted",))
    assert principal.landed_incident(intent=_intent(scope)) is None
    assert (
        principal.publish_inverse(
            request=InversePublishRequest(intent=_intent(scope), plan=plan, message="inverse")
        ).status
        == "unknown"
    )
    assert principal.read_master_head(repository=scope.repository, branch="master") == ""


@pytest.mark.parametrize("status", [["committed"], None, 7, "unknown", "head-moved"])
def test_publish_reply_never_raises_for_malformed_status(history, monkeypatch, status):
    repo, scope, _ = history
    plan = unsafe_perform_io(
        inverse.plan_incident_inverse(
            repo_root=repo, scope=scope, expected_head=scope.merge_sha
        ).unwrap()
    )
    monkeypatch.setattr(
        service.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "schema": 1,
                    "operation": "publish",
                    "binding": json.loads(_kwargs["input"])["binding"],
                    "status": status,
                }
            ).encode(),
        ),
    )
    result = service.ProcessInverseForge(command=("trusted",)).publish_inverse(
        request=InversePublishRequest(intent=_intent(scope), plan=plan, message="inverse")
    )
    assert result.status == ("head-moved" if status == "head-moved" else "unknown")


@dataclass(frozen=True, kw_only=True)
class ArmedIntent:
    action_id: str
    registration: object
    completion: object
    observer_arm: object


@pytest.mark.parametrize(
    "change",
    [
        {},
        {"pr_number": 72},
        {"base_sha": "a" * 40},
        {"head_sha": "b" * 40},
        {"owner": "other"},
        {"generation": 999},
        {"operation_id": "stale"},
        {"authority_receipt": b"other"},
        {"phase": "closed"},
    ],
)
def test_retained_premerge_arm_binds_full_pr_and_generation(history, change):
    repo, scope, _ = history
    original = _intent(scope)
    arm = asdict(original.registration)
    arm.update(
        pr_number=scope.pr_number,
        base_sha=scope.original_base_sha,
        head_sha=scope.original_head_sha,
    )
    arm.update(change)
    intent = ArmedIntent(
        action_id=original.action_id,
        registration=original.registration,
        completion=original.completion,
        observer_arm=arm,
    )
    forge = Forge(repo=repo, scope=scope)
    result = inverse.recover_incident_inverse(repo_root=repo, intent=intent, forge=forge)
    assert isinstance(result, IOSuccess if not change else IOFailure)
    assert len(forge.requests) == (0 if change else 1)


def test_malformed_retained_arm_refuses_scope(history):
    repo, scope, _ = history
    original = _intent(scope)
    intent = ArmedIntent(
        action_id=original.action_id,
        registration=original.registration,
        completion=original.completion,
        observer_arm="malformed",
    )
    forge = Forge(repo=repo, scope=scope)
    result = inverse.recover_incident_inverse(repo_root=repo, intent=intent, forge=forge)
    assert isinstance(result, IOFailure)
    assert not forge.requests


@pytest.mark.parametrize("status", ["unknown", "reserved", "recorded", "absent"])
def test_only_explicit_bound_absence_permits_initial_recovery(history, monkeypatch, status):
    repo, scope, _ = history
    calls = []

    def run(command, **kwargs):
        body = json.loads(kwargs["input"])
        calls.append(body["operation"])
        assert command == ["trusted"]
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "schema": 1,
                    "operation": body["operation"],
                    "binding": body["binding"],
                    "status": status,
                    "scope": asdict(scope),
                    "authorized": True,
                    "head": scope.merge_sha,
                }
            ).encode(),
        )

    monkeypatch.setattr(service.subprocess, "run", run)
    principal = service.ProcessInverseForge(command=("trusted",))
    if status == "absent":
        assert principal.read_exact_receipt(intent=_intent(scope)) is None
        assert calls == ["lookup"]
        return
    result = inverse.recover_incident_inverse(
        repo_root=repo, intent=_intent(scope), forge=principal
    )
    assert isinstance(result, IOFailure)
    assert calls == ["lookup"]


@pytest.mark.parametrize("case", ["unavailable", "reserved", "wrong-binding", "bool-schema"])
def test_unobservable_or_wrong_action_lookup_blocks_restart_publication(history, monkeypatch, case):
    repo, scope, _ = history
    calls = []

    def run(*_args, **kwargs):
        body = json.loads(kwargs["input"])
        calls.append(body["operation"])
        response = {
            "schema": True if case == "bool-schema" else 1,
            "operation": body["operation"],
            "binding": {} if case == "wrong-binding" else body["binding"],
            "status": "reserved",
            "receipt": "other-action-effect",
        }
        return SimpleNamespace(
            returncode=7 if case == "unavailable" else 0, stdout=json.dumps(response).encode()
        )

    monkeypatch.setattr(service.subprocess, "run", run)
    principal = service.ProcessInverseForge(command=("trusted",))
    for _restart in range(2):
        result = inverse.recover_incident_inverse(
            repo_root=repo, intent=_intent(scope), forge=principal
        )
        assert isinstance(result, IOFailure)
    assert calls == ["lookup", "lookup"]


def test_unknown_publish_reservation_survives_direct_recovery_restart(history, monkeypatch):
    repo, scope, _ = history
    real_run = subprocess.run
    state = {"reserved": False, "publishes": 0}

    def run(command, **kwargs):
        if command != ["trusted"]:
            return real_run(command, **kwargs)
        body = json.loads(kwargs["input"])
        response = {"schema": 1, "operation": body["operation"], "binding": body["binding"]}
        if body["operation"] == "lookup":
            response["status"] = "reserved" if state["reserved"] else "absent"
        elif body["operation"] == "landed":
            response["scope"] = asdict(scope)
        elif body["operation"] == "authorize":
            response["authorized"] = True
        elif body["operation"] == "head":
            response["head"] = scope.merge_sha
        else:
            assert body["operation"] == "publish"
            state["publishes"] += 1
            state["reserved"] = True
            response["status"] = "unknown"
        return SimpleNamespace(returncode=0, stdout=json.dumps(response).encode())

    monkeypatch.setattr(service.subprocess, "run", run)
    principal = service.ProcessInverseForge(command=("trusted",))
    for _restart in range(2):
        result = inverse.recover_incident_inverse(
            repo_root=repo, intent=_intent(scope), forge=principal
        )
        assert isinstance(result, IOFailure)
    assert state["publishes"] == 1
