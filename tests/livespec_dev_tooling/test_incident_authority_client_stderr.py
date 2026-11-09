"""A refused authority call reports the failing call's stderr, not just its exit.

livespec-dev-tooling-iezdmk. A 1Password 500 in the credential wrapper used to surface
as a bare JSONDecodeError and the operator never saw the wrapper's own words. Every
refusal now carries the call's stderr to the operator: a refusing client names it in
the detail it hands back, and the two observer readers, which answer a bare boolean or
a reason code, write the same detail on their own stderr.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from returns.pipeline import is_successful
from returns.unsafe import unsafe_perform_io

from livespec_dev_tooling import incident_authority_client as client
from livespec_dev_tooling import incident_hook_process as hook
from livespec_dev_tooling import incident_observer_provenance as observer_provenance
from livespec_dev_tooling import incident_provenance as provenance
from livespec_dev_tooling._incident_observer_types import ObserverArm
from livespec_dev_tooling._incident_original_run_ports import installed_ports
from livespec_dev_tooling.incident_observer_authority import CurrentAuthorityReader

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-iezdmk
_WRAPPER_WORDS = "[ERROR] 2026-11-09 (500) Internal Server Error: Server experienced a fatal error."
_HEAD = "b" * 40
_QUERY: dict[str, Any] = {
    "repository": "owner/repo",
    "item_id": "incident-1",
    "attempt_id": "attempt-1",
    "phase": "repair",
    "operation_id": "operation-2",
    "generation": 2,
    "owner": "operator",
    "base": "a" * 40,
    "head": _HEAD,
    "pr_number": 7,
    "commit_sha": _HEAD,
    "tree_sha": "c" * 40,
}


def _reply(**changes: object) -> dict[str, Any]:
    reply: dict[str, Any] = {
        "schema": 1,
        "status": "verified",
        "authorizes_current_effects": True,
        "normal_factory_proof": False,
        "result": {"marker": "ok"},
    }
    return reply | changes


def _run(
    *, monkeypatch: pytest.MonkeyPatch, stdout: str, returncode: int, stderr: str = _WRAPPER_WORDS
) -> None:
    def run(argv: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(argv, returncode, stdout, stderr)

    monkeypatch.setattr(subprocess, "run", run)


def _call() -> Any:
    return client.call_authority(
        command=["reader"], action="read-current", flags={}, cwd=Path("/governed")
    )


_FAILING_REPLIES = [
    ("exit", json.dumps(_reply()), 1),
    ("empty", "", 1),
    ("not-json", "not json", 0),
    ("duplicate-keys", json.dumps(_reply()).replace('"schema": 1', '"schema": 1, "schema": 1'), 0),
    ("schema", json.dumps(_reply(schema=True)), 0),
    (
        "proof-flag",
        json.dumps({k: v for k, v in _reply().items() if k != "normal_factory_proof"}),
        0,
    ),
    ("not-verified", json.dumps(_reply(status="refused")), 0),
    ("wrong-kind", json.dumps(_reply(authorizes_current_effects=False)), 0),
    ("result", json.dumps(_reply(result=[])), 0),
    ("malformed-refusal", json.dumps(_reply()), 78),
]


@pytest.mark.parametrize(
    ("stdout", "returncode"), [pytest.param(o, r, id=i) for i, o, r in _FAILING_REPLIES]
)
def test_every_refusal_by_name_carries_the_failing_calls_stderr(
    monkeypatch: pytest.MonkeyPatch, stdout: str, returncode: int
) -> None:
    _run(monkeypatch=monkeypatch, stdout=stdout, returncode=returncode)
    refused = _call().failure()
    assert refused.code.startswith("incident-authority-")
    assert _WRAPPER_WORDS in refused.detail


def test_a_very_long_stderr_is_bounded_in_the_detail(monkeypatch: pytest.MonkeyPatch) -> None:
    _run(monkeypatch=monkeypatch, stdout="", returncode=1, stderr="x" * 100000)
    assert len(_call().failure().detail) < 4000


def test_a_canonical_refusal_keeps_the_authoritys_own_detail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = _reply(
        status="refused",
        authorizes_current_effects=False,
        result={"code": "incident-authority-missing", "detail": "no chain"},
    )
    _run(monkeypatch=monkeypatch, stdout=json.dumps(body), returncode=78)
    refused = _call().failure()
    assert (refused.code, refused.detail) == ("incident-authority-missing", "no chain")


def test_stderr_noise_on_a_verified_reply_is_not_a_refusal(monkeypatch: pytest.MonkeyPatch) -> None:
    _run(monkeypatch=monkeypatch, stdout=json.dumps(_reply()), returncode=0)
    assert is_successful(_call())


# ---- What each caller does with the refusal. ----


def _failing(*, monkeypatch: pytest.MonkeyPatch) -> None:
    _run(monkeypatch=monkeypatch, stdout="", returncode=1)


def _hook_reports(*, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, **_: object) -> str:
    monkeypatch.setattr(hook, "_governed_root", lambda **_kwargs: tmp_path)
    monkeypatch.setattr(hook, "registered_plugin_root", lambda **_kwargs: tmp_path)
    query = {
        "repository": "owner/repo",
        "item": "incident",
        "attempt": "attempt",
        "phase": "repair",
        "operation": "operation",
        "generation": 1,
        "owner": "operator",
    }
    _failing(monkeypatch=monkeypatch)
    with pytest.raises(hook.HookRefusalError) as refused:
        _ = hook.invoke_authority(repo=tmp_path, query=query, action="read-current")
    return str(refused.value)


def _operator_reports(*, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, **_: object) -> str:
    _ = (tmp_path / "reader.env").write_text("BEADS_DOLT_PASSWORD=tenant\n")
    installation = SimpleNamespace(
        config=tmp_path / "controller.json", repo=tmp_path, reader=("installed-reader",)
    )
    authority = installed_ports(installation=installation).canonical.authority
    _failing(monkeypatch=monkeypatch)
    with pytest.raises(ValueError, match="incident-authority-exit") as refused:
        _ = authority("read-current", {"item": "incident-1"}, {})
    return str(refused.value)


def _provenance_reports(*, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, **_: object) -> str:
    monkeypatch.setattr(provenance, "registered_plugin_root", lambda **_kwargs: tmp_path)
    _failing(monkeypatch=monkeypatch)
    done = provenance.read_historical_incident_commit(
        repo_root=tmp_path, query=provenance.IncidentCommitQuery(**_QUERY)
    )
    refusal = unsafe_perform_io(done.failure())
    return f"{refusal.code}: {refusal.detail}"


def _observer_reader_reports(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> str:
    arm = ObserverArm(
        repository="owner/repo",
        incident_item_id="incident-1",
        attempt_id="repair-1",
        phase="repair",
        operation_id="operation-2",
        generation=2,
        owner="owner",
        pr_number=55,
        base_sha="e" * 40,
        head_sha="c" * 40,
        required_jobs=("ci-green",),
        controller_release="v1.2.3",
        controller_revision="b" * 40,
        authority_receipt=b"{}",
    )
    reader = CurrentAuthorityReader(
        command=("installed-reader",),
        repo=tmp_path,
        release="v1.2.3",
        installed_reader_approved=lambda _release, _command: True,
    )
    _failing(monkeypatch=monkeypatch)
    assert reader(arm) is False
    return capsys.readouterr().err


def _observer_provenance_reports(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> str:
    settings = SimpleNamespace(repo=tmp_path, reader=("installed-reader",))
    _failing(monkeypatch=monkeypatch)
    answer = observer_provenance.ObserverProvenance(installation=settings).execute(
        path="/provenance", payload=dict(_QUERY)
    )
    assert answer == {
        "schema": 1,
        "status": "refused",
        "reason": "incident-authority-exit",
    }
    return capsys.readouterr().err


_REPORTERS: dict[str, Callable[..., str]] = {
    "hook": _hook_reports,
    "operator": _operator_reports,
    "provenance": _provenance_reports,
    "observer-reader": _observer_reader_reports,
    "observer-provenance": _observer_provenance_reports,
}


@pytest.mark.parametrize("caller", _REPORTERS)
def test_every_caller_reports_the_failing_calls_stderr_to_the_operator(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    caller: str,
) -> None:
    reported = _REPORTERS[caller](monkeypatch=monkeypatch, tmp_path=tmp_path, capsys=capsys)
    assert "incident-authority-exit" in reported
    assert _WRAPPER_WORDS in reported
