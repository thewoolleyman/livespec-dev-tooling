"""Recovered failure and stale ownership never turn into new execution."""

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-cerkbn
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

from livespec_dev_tooling import incident_hook_entry as module
from livespec_dev_tooling import incident_hook_process as process
from livespec_dev_tooling.incident_hook_process import HookRefusalError
from tests.livespec_dev_tooling.test_incident_hook_entry_edges import _wired


@pytest.mark.parametrize("failure", [0, 3])
def test_recovered_success_or_failure_never_runs_gates_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: int
) -> None:
    reading, receipts = _wired(root=tmp_path, monkeypatch=monkeypatch, failure=failure)
    invoke = module.invoke_authority
    assert module.main(argv=["pre-commit"]) == failure
    original = receipts[0]

    def recovered(**kwargs: Any) -> dict[str, Any]:
        if kwargs["action"] != "read-local-gates":
            return invoke(**kwargs)
        return dict(
            status="recorded",
            receipt_id=kwargs["receipt_id"],
            receipt=original,
            checksum="sha256:" + "a" * 64,
            committed_token_id=reading["committed_token_id"],
            current_token_id=reading["current_token_id"],
        )

    gates = Mock(wraps=module.route_resolved_gates)
    monkeypatch.setattr(module, "invoke_authority", recovered)
    monkeypatch.setattr(module, "route_resolved_gates", gates)
    assert module.main(argv=["pre-commit"]) == failure
    gates.assert_not_called()
    assert receipts == [original]


@pytest.mark.parametrize("moved", ["authority", "tree"])
def test_recovery_rechecks_current_authority_and_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, moved: str
) -> None:
    reading, receipts = _wired(root=tmp_path, monkeypatch=monkeypatch)
    invoke = module.invoke_authority
    assert module.main(argv=["pre-commit"]) == 0
    original = receipts[0]
    recovered: list[bool] = []

    def current(**kwargs: Any) -> dict[str, Any]:
        if kwargs["action"] == "read-local-gates":
            recovered.append(True)
            return dict(
                status="recorded",
                receipt_id=kwargs["receipt_id"],
                receipt=original,
                checksum="sha256:" + "a" * 64,
                committed_token_id=reading["committed_token_id"],
                current_token_id=reading["current_token_id"],
            )
        if recovered:
            if moved == "authority":
                return reading | {"current_token_id": "new-owner"}
            (tmp_path / "app.py").write_text("changed after lookup\n")
        return invoke(**kwargs)

    monkeypatch.setattr(module, "invoke_authority", current)
    assert module.main(argv=["pre-commit"]) == 78
    assert len(receipts) == 1


def test_unobservable_lookup_is_not_absence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _reading, receipts = _wired(root=tmp_path, monkeypatch=monkeypatch)
    invoke = module.invoke_authority

    def unavailable(**kwargs: Any) -> dict[str, Any]:
        if kwargs["action"] == "read-local-gates":
            message = "canonical lookup unavailable"
            raise HookRefusalError(message)
        return invoke(**kwargs)

    monkeypatch.setattr(module, "invoke_authority", unavailable)
    assert module.main(argv=["pre-commit"]) == 78
    assert not receipts


def test_registered_lookup_process_receives_exact_receipt_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(process, "git_text", lambda **_kw: str(tmp_path / ".git"))
    monkeypatch.setattr(process, "registered_plugin_root", lambda **_kw: tmp_path / "installed")

    def command(argv: list[str], **_kw: Any) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(
            argv,
            0,
            json.dumps(
                dict(
                    schema=1,
                    status="verified",
                    normal_factory_proof=False,
                    authorizes_current_effects=False,
                    result=dict(status="absent"),
                )
            ),
            "",
        )

    monkeypatch.setattr(process.subprocess, "run", command)
    assert process.invoke_authority(
        repo=tmp_path, query={}, action="read-local-gates", receipt_id="exact-receipt"
    ) == dict(status="absent")
    assert calls[0][-2:] == ["--receipt-id", "exact-receipt"]
