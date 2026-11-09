"""The controller's forge reads go only through the recovery App, read-only, on one repository."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import Mock

import pytest

from livespec_dev_tooling.incident_forge_reads import ForgeReads
from livespec_dev_tooling.incident_recovery_app import AppRefusal, RecoveryForge

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-x3wwwc
_PEM = "-----BEGIN RSA PRIVATE KEY----- QUJD -----END RSA PRIVATE KEY-----"


def _installation(*, root: Path) -> Any:
    return cast(
        "Any",
        SimpleNamespace(
            config=root / "controller.json", repository="owner/repo", ci_identity_policy=None
        ),
    )


def _forge(*answers: tuple[int, object]) -> Mock:
    forge = Mock(repository="owner/repo")
    forge.request.side_effect = list(answers)
    return forge


def test_a_read_returns_the_resource_and_names_it_under_the_repository() -> None:
    forge = _forge((200, {"id": 1}))
    assert ForgeReads(connect=lambda: forge)("repos/owner/repo/pulls/1") == {"id": 1}
    assert forge.request.call_args.kwargs == {"method": "GET", "path": "pulls/1"}


def test_a_failed_read_or_a_foreign_path_answers_none() -> None:
    forge = _forge((404, {"message": "Not Found"}))
    reads = ForgeReads(connect=lambda: forge)
    assert reads("repos/owner/repo/pulls/1") is None
    assert reads("repos/owner/other/pulls/1") is None
    assert forge.request.call_count == 1


def test_a_refused_credential_answers_none() -> None:
    refusal = AppRefusal(code="recovery-app-credential-absent", detail="absent")
    assert ForgeReads(connect=lambda: refusal)("repos/owner/repo/pulls/1") is None


def test_an_absent_credential_refuses_with_no_other_identity(tmp_path: Path) -> None:
    reads = ForgeReads.installed(installation=_installation(root=tmp_path))
    assert isinstance(reads.connect(), AppRefusal)
    assert reads("repos/owner/repo/pulls/1") is None


def test_one_operation_mints_one_read_token_over_many_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    credential = tmp_path / "recovery-app.json"
    credential.write_text(json.dumps({"app_id": "7", "private_key": _PEM}))
    credential.chmod(0o600)
    forge = _forge((200, {"a": 1}), (200, {"b": 2}))
    connect = Mock(return_value=forge)
    monkeypatch.setattr(RecoveryForge, "connect", connect)
    reads = ForgeReads.installed(installation=_installation(root=tmp_path))
    assert reads("repos/owner/repo/a") == {"a": 1}
    assert reads("repos/owner/repo/b") == {"b": 2}
    assert connect.call_count == 1
    assert connect.call_args.kwargs["repository"] == "owner/repo"
    assert connect.call_args.kwargs["access"] == "read"
    assert connect.call_args.kwargs["credential"].app_id == "7"
