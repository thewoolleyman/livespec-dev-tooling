"""`/arm` refuses an expedited PR whose head tree lacks complete, disposed focused evidence."""

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-4aksht
from __future__ import annotations

import hashlib
import io
import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from livespec_dev_tooling import incident_observer_control as control
from livespec_dev_tooling import incident_observer_service as service
from livespec_dev_tooling.incident_controller_installation import ControllerInstallation
from livespec_dev_tooling.incident_focused_admission import (
    EVIDENCE_ROW,
    EvidenceSubject,
    disposition_receipt,
    evidence_receipt_id,
)

_HEAD = "c" * 40
_TREE = "f" * 40
_CHECKSUM = "sha256:" + "1" * 64
_MEMBER = "coverage incomplete: src/widget.py"
_SUBJECT = EvidenceSubject(
    repository="owner/repo",
    item="incident-1",
    attempt="repair-1",
    operation="operation-1",
    generation=1,
    head=_HEAD,
    tree=_TREE,
)
_ATTEMPT: dict[str, Any] = {
    "repository": "owner/repo",
    "item_id": "incident-1",
    "attempt_id": "repair-1",
    "phase": "repair",
    "operation_id": "operation-1",
    "generation": 1,
    "owner": "owner",
    "base": "e" * 40,
    "head": _HEAD,
    "pr_number": 55,
    "landed_commits": [],
}


def _record(**changes: Any) -> dict[str, Any]:
    record: dict[str, Any] = {
        "mode": "expedited-repair",
        "scope": "focused-tests-and-touched-files",
        "tree_hash": _TREE,
        "identity": {
            "incident_item_id": "incident-1",
            "attempt_id": "repair-1",
            "repository": "owner/repo",
            "head_sha": _HEAD,
            "operation_id": "operation-1",
        },
        "paths": {"src/widget.py": "executable"},
        "selection": {"tests": [], "deferred_tests": {}},
        "manual": {"procedure": "p", "expected": "e", "observed": "e", "outcome": "passed"},
        "tests": {"returncode": 0, "timed_out": False},
        "coverage_command": {"returncode": 0, "timed_out": False},
        "coverage": {"src/widget.py": {"summary": {"percent_covered": 50}}},
        "risks": [_MEMBER],
        "outcome": "incomplete",
    }
    record.update(changes)
    return record


def _evidence(*, record: dict[str, Any]) -> dict[str, Any]:
    return {
        "receipt_id": evidence_receipt_id(subject=_SUBJECT, slot=0),
        "hook": "pre-push",
        "tree": _TREE,
        "mode": "expedited-repair",
        "evidence_kind": "expedited-local-partial",
        "exit_status": 1,
        "results": [{"name": EVIDENCE_ROW, "status": "failed", "output": json.dumps(record)}],
    }


class _Authority:
    def __init__(self) -> None:
        self.receipts: dict[str, dict[str, Any]] = {}
        self.actions: list[str] = []
        self.local_gates_exit = 0

    def add(self, receipt: dict[str, Any]) -> None:
        self.receipts[receipt["receipt_id"]] = receipt

    def __call__(self, argv: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        action = argv[1]
        self.actions.append(action)
        result: dict[str, Any] = {"is_current": True, "attempt": _ATTEMPT}
        if action == "read-local-gates":
            if self.local_gates_exit:
                return subprocess.CompletedProcess(argv, self.local_gates_exit, "", "boom")
            receipt_id = argv[argv.index("--receipt-id") + 1]
            receipt = self.receipts.get(receipt_id)
            result = {
                "status": "absent" if receipt is None else "recorded",
                "receipt_id": receipt_id,
                "committed_token_id": "committed",
                "current_token_id": "current",
                "checksum": None if receipt is None else _CHECKSUM,
                "receipt": receipt,
            }
        reply = {
            "schema": 1,
            "status": "verified",
            "authorizes_current_effects": action == "read-current",
            "normal_factory_proof": False,
            "result": result,
        }
        return subprocess.CompletedProcess(argv, 0, json.dumps(reply), "")


@pytest.fixture
def observer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[service.ControllerService, dict[str, Any], _Authority]:
    settings = ControllerInstallation(
        repository="owner/repo",
        repo=tmp_path / "repo",
        state=tmp_path / "state",
        reader=("/installed/reader",),
        reader_release="v0.304.0",
        principal=("/installed/principal",),
        release="v1.169.0",
        revision="b" * 40,
        jobs=("coverage",),
        webhook_secret=b"webhook" * 8,
        control_secret=b"control" * 8,
        query_secret=b"query" * 8,
        port=8765,
        config=tmp_path / "controller.json",
    )
    authority = _Authority()
    monkeypatch.setattr(subprocess, "run", authority)

    def installed(**_: object) -> Callable[[str], object]:
        commits = {f"repos/owner/repo/git/commits/{_HEAD}": {"sha": _HEAD, "tree": {"sha": _TREE}}}
        return commits.get

    monkeypatch.setattr(control.ForgeReads, "installed", installed)
    payload = {
        "repository": "owner/repo",
        "incident_item_id": "incident-1",
        "attempt_id": "repair-1",
        "phase": "repair",
        "operation_id": "operation-1",
        "generation": 1,
        "owner": "owner",
        "base_sha": "e" * 40,
        "head_sha": _HEAD,
        "pr_number": 55,
        "authority_receipt": json.dumps(_ATTEMPT, sort_keys=True, separators=(",", ":"))
        .encode()
        .hex(),
    }
    application = service.ControllerService(installation=settings, recover=lambda _: None)
    return application, payload, authority


def _post(
    *, application: service.ControllerService, path: str, payload: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    body = json.dumps(payload).encode()
    secret = (
        application.installation.query_secret
        if path == "/admitted"
        else application.installation.control_secret
    )
    environ = {
        "PATH_INFO": path,
        "REQUEST_METHOD": "POST",
        "CONTENT_LENGTH": str(len(body)),
        "wsgi.input": io.BytesIO(body),
        "HTTP_AUTHORIZATION": "Bearer " + secret.decode(),
    }
    statuses: list[str] = []
    data = b"".join(application(environ, lambda status, _: statuses.append(status)))
    return statuses[0], json.loads(data)


def _admitted(
    *, application: service.ControllerService, arm_id: str, payload: dict[str, Any]
) -> str:
    query = {
        "repository": "owner/repo",
        "arm_id": arm_id,
        "pr_number": 55,
        "base_sha": "e" * 40,
        "head_sha": _HEAD,
        "receipt_digest": hashlib.sha256(bytes.fromhex(payload["authority_receipt"])).hexdigest(),
    }
    return _post(application=application, path="/admitted", payload=query)[0]


def _arm_id(*, payload: dict[str, Any]) -> str:
    snapshot = {
        **payload,
        "controller_release": "v1.169.0",
        "controller_revision": "b" * 40,
        "required_jobs": ["coverage"],
    }
    return hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()


def test_arm_refuses_absent_then_undisposed_then_accepts_once_disposed(
    observer: tuple[service.ControllerService, dict[str, Any], _Authority],
) -> None:
    application, payload, authority = observer
    status, result = _post(application=application, path="/arm", payload=payload)
    assert status == "403 Forbidden"
    assert result["reason"].startswith("incident-focused-evidence-absent:")
    assert _TREE in result["reason"]
    assert "read-current" not in authority.actions
    assert _admitted(application=application, arm_id=_arm_id(payload=payload), payload=payload) == (
        "403 Forbidden"
    )

    authority.add(_evidence(record=_record()))
    status, result = _post(application=application, path="/arm", payload=payload)
    assert status == "403 Forbidden"
    assert result["reason"].startswith("incident-focused-evidence-undisposed:")
    assert _MEMBER in result["reason"]

    authority.add(
        disposition_receipt(
            evidence_receipt_id=evidence_receipt_id(subject=_SUBJECT, slot=0),
            evidence_checksum=_CHECKSUM,
            member=_MEMBER,
            disposition="P1 is a defensive fast path with no test; risk accepted",
            tree=_TREE,
        )
    )
    status, result = _post(application=application, path="/arm", payload=payload)
    assert (status, result["status"]) == ("202 Accepted", "armed")
    assert result["receipt"] == _arm_id(payload=payload)
    assert authority.actions[-1] == "read-current"
    assert _admitted(application=application, arm_id=result["receipt"], payload=payload) == (
        "202 Accepted"
    )


def test_arm_refuses_a_failed_member_whatever_its_disposition(
    observer: tuple[service.ControllerService, dict[str, Any], _Authority],
) -> None:
    application, payload, authority = observer
    authority.add(
        _evidence(record=_record(tests={"returncode": 1, "timed_out": False}, outcome="failed"))
    )
    for member in (_MEMBER, "focused test"):
        authority.add(
            disposition_receipt(
                evidence_receipt_id=evidence_receipt_id(subject=_SUBJECT, slot=0),
                evidence_checksum=_CHECKSUM,
                member=member,
                disposition="accepted",
                tree=_TREE,
            )
        )
    status, result = _post(application=application, path="/arm", payload=payload)
    assert status == "403 Forbidden"
    assert result["reason"].startswith("incident-focused-evidence-failed: focused test")


def test_arm_refuses_when_the_evidence_cannot_be_read(
    observer: tuple[service.ControllerService, dict[str, Any], _Authority],
) -> None:
    application, payload, authority = observer
    authority.local_gates_exit = 1
    status, result = _post(application=application, path="/arm", payload=payload)
    assert status == "403 Forbidden"
    assert result["reason"].startswith("incident-focused-evidence-unavailable:")
    assert "read-current" not in authority.actions
