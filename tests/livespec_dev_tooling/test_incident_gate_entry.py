"""Every direct gate entrance resolves incident mode before any gate work."""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock

import pytest

from livespec_dev_tooling import (
    gate_remote_delegate,
    gate_runner_delegate,
    incident_gate_entry,
    pre_commit_delegate,
)
from livespec_dev_tooling.gate_runner_delegate import GateVenue
from livespec_dev_tooling.incident_execution import Invocation

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-6bmta2
_REPO = Path(__file__).resolve().parents[2]
_SCRIPTS = ("check", "check-scoped", "check-changed", "check-pre-push", "check-pre-commit")
_FLAG = "EXPEDITED_INCIDENT_RESPONSE"
_REVERT = "EXPEDITED_INCIDENT_RESPONSE_REVERT"
_REFUSALS = (
    ({_FLAG: "maybe"}, "invalid-incident-flag"),
    ({_REVERT: "2"}, "invalid-incident-flag"),
    ({_FLAG: "1"}, "untrusted-incident-receipt"),
)
_QUERY = json.dumps(
    dict(
        repository="owner/repo",
        item="incident-1",
        attempt="attempt-1",
        phase="repair",
        operation="operation-1",
        generation=1,
        owner="operator:alice",
    ),
    sort_keys=True,
    separators=(",", ":"),
)


def _scrubbed() -> dict[str, str]:
    return {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("GIT_", "EXPEDITED_", "LIVESPEC_INCIDENT_"))
    }


def _clear(*, monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        _FLAG,
        _REVERT,
        "LIVESPEC_INCIDENT_CONTEXT",
        "LIVESPEC_INCIDENT_AUTHORITY_QUERY",
        "LIVESPEC_INCIDENT_LOCAL_OPERATION",
    ):
        monkeypatch.delenv(key, raising=False)


def _stub_bin(*, root: Path) -> Path:
    binary = root / "bin"
    binary.mkdir()
    forward = (
        "#!/bin/sh\n"
        'printf "%s\\n" "$*" >> "$UV_LOG"\n'
        'case "$*" in *livespec_dev_tooling.incident_gate_entry*) '
        'shift 3; exec "$ENTRY_PYTHON" "$@";; esac\n'
        'touch "$GATE_MARKER"\nexit 0\n'
    )
    work = '#!/bin/sh\ntouch "$GATE_MARKER"\nexit 0\n'
    for name, body in (("uv", forward), ("just", work), ("git", work), ("mise", work)):
        _ = (binary / name).write_text(body)
        (binary / name).chmod(0o755)
    return binary


def _run_script(*, root: Path, script: str, flags: dict[str, str]) -> tuple[int, str, bool, str]:
    work = root / script
    work.mkdir()
    binary = _stub_bin(root=work)
    log = work / "uv.log"
    marker = work / "gate-work-launched"
    completed = subprocess.run(
        ["bash", str(_REPO / "scripts/just" / (script + ".sh"))],
        cwd=work,
        env=_scrubbed()
        | flags
        | {
            "PATH": str(binary) + os.pathsep + os.environ["PATH"],
            "UV_LOG": str(log),
            "GATE_MARKER": str(marker),
            "ENTRY_PYTHON": sys.executable,
        },
        stdin=subprocess.DEVNULL,
        check=False,
        capture_output=True,
        text=True,
    )
    logged = log.read_text() if log.exists() else ""
    return completed.returncode, completed.stderr, marker.exists(), logged


@pytest.mark.parametrize("script", _SCRIPTS)
@pytest.mark.parametrize(("flags", "code"), _REFUSALS)
def test_direct_recipe_refuses_an_incident_flag_before_any_gate_work(
    *, tmp_path: Path, script: str, flags: dict[str, str], code: str
) -> None:
    returncode, stderr, launched, _ = _run_script(root=tmp_path, script=script, flags=flags)
    facts = [
        returncode == incident_gate_entry.REFUSED,
        f"incident-gate-refused: {script}: {code}" in stderr,
        not launched,
    ]
    assert all(facts), (returncode, stderr, launched)


@pytest.mark.parametrize("script", _SCRIPTS)
def test_direct_recipe_with_both_flags_unset_never_enters_the_boundary(
    *, tmp_path: Path, script: str
) -> None:
    _, _, _, logged = _run_script(root=tmp_path, script=script, flags={_FLAG: "", _REVERT: ""})
    assert "incident_gate_entry" not in logged


def _python_entrances(
    *, monkeypatch: pytest.MonkeyPatch
) -> list[tuple[str, list[str], ModuleType, Mock]]:
    replay = importlib.import_module("livespec_dev_tooling.checks.red_green_replay")
    cases: list[tuple[str, list[str], ModuleType, str]] = [
        ("pre-commit-delegate", ["run"], pre_commit_delegate, "run_pre_commit"),
        ("gate-remote-delegate", ["enabled"], gate_remote_delegate, "delegated_gate_selected"),
        ("gate-remote-delegate", ["run"], gate_remote_delegate, "group_repair_status"),
        ("gate-runner", ["--", "just", "check"], gate_runner_delegate, "select_for_repository"),
        ("gate-runner", ["run", "--run-dir", "x", "--"], gate_runner_delegate, "run_cluster_gate"),
        ("check-red-green-replay", [], replay, "load_config_or_report"),
    ]
    wired: list[tuple[str, list[str], ModuleType, Mock]] = []
    for surface, argv, module, collaborator in cases:
        work = Mock(side_effect=AssertionError(collaborator))
        monkeypatch.setattr(module, collaborator, work)
        wired.append((surface, argv, module, work))
    return wired


@pytest.mark.parametrize(("flags", "code"), _REFUSALS)
def test_python_entrances_refuse_before_selection_probe_or_submission(
    *,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    flags: dict[str, str],
    code: str,
) -> None:
    _clear(monkeypatch=monkeypatch)
    for name, value in flags.items():
        monkeypatch.setenv(name, value)
    facts: list[bool] = []
    for surface, argv, module, work in _python_entrances(monkeypatch=monkeypatch):
        monkeypatch.setattr(sys, "argv", [surface, *argv])
        status = module.main()
        stderr = capsys.readouterr().err
        facts.extend(
            [
                status == incident_gate_entry.REFUSED,
                f"incident-gate-refused: {surface}: {code}" in stderr,
                work.call_count == 0,
            ]
        )
    assert all(facts), facts


def _trusted(*, monkeypatch: pytest.MonkeyPatch) -> tuple[Mock, Mock]:
    _clear(monkeypatch=monkeypatch)
    monkeypatch.setenv(_FLAG, "1")
    monkeypatch.setenv("LIVESPEC_INCIDENT_AUTHORITY_QUERY", _QUERY)
    monkeypatch.setenv("LIVESPEC_INCIDENT_LOCAL_OPERATION", "local-operation-1")
    authority = Mock(return_value={"is_current": True})
    resolver = Mock(return_value=None)
    monkeypatch.setattr(incident_gate_entry, "invoke_authority", authority)
    monkeypatch.setattr(incident_gate_entry, "resolve_current", resolver)
    return authority, resolver


def test_a_trusted_incident_launches_the_detached_runner_on_the_local_venue_only(
    *, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    authority, resolver = _trusted(monkeypatch=monkeypatch)
    select = Mock(return_value=GateVenue(venue="local", reason="incident"))
    monkeypatch.setattr(gate_runner_delegate, "select_for_repository", select)
    monkeypatch.setattr(sys, "argv", ["gate-runner", "--", "git", "commit"])
    status = gate_runner_delegate.main()
    facts = [
        status == 0,
        select.call_args is not None and select.call_args.kwargs["force_local"] is True,
        authority.call_args is not None and authority.call_args.kwargs["action"] == "read-current",
        resolver.call_count == 1,
        capsys.readouterr().out == "local\nincident\n",
    ]
    assert all(facts), facts


def test_a_trusted_incident_never_runs_a_direct_aggregate_or_cluster_submission(
    *, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _ = _trusted(monkeypatch=monkeypatch)
    cluster = Mock(side_effect=AssertionError("cluster"))
    monkeypatch.setattr(gate_runner_delegate, "run_cluster_gate", cluster)
    monkeypatch.setattr(sys, "argv", ["gate-runner", "run", "--run-dir", "x", "--"])
    facts = [
        incident_gate_entry.main(argv=["check"]) == incident_gate_entry.REFUSED,
        gate_runner_delegate.main() == incident_gate_entry.REFUSED,
        cluster.call_count == 0,
        capsys.readouterr().err.count("no-direct-incident-mode") == 2,
    ]
    assert all(facts), facts


def test_the_boundary_cli_distinguishes_normal_unknown_and_reverting_refusals(
    *, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _clear(monkeypatch=monkeypatch)
    monkeypatch.setattr(sys, "argv", ["incident_gate_entry", "check-scoped"])
    normal = incident_gate_entry.main()
    unknown = incident_gate_entry.main(argv=["deploy"])
    empty = incident_gate_entry.main(argv=[])
    continued = incident_gate_entry.entrance_refusal(surface="check")
    monkeypatch.setenv(_REVERT, "1")
    monkeypatch.setenv("LIVESPEC_INCIDENT_AUTHORITY_QUERY", "{not json")
    reverting = incident_gate_entry.resolve_entrance(surface="check-changed", launcher=True)
    stderr = capsys.readouterr().err
    facts = [
        normal == incident_gate_entry.NORMAL,
        unknown == incident_gate_entry.REFUSED,
        empty == incident_gate_entry.REFUSED,
        continued is None,
        reverting.mode == "refused",
        "check-changed: untrusted-incident-receipt" in reverting.reason,
        stderr.count("unknown-entrance") == 2,
    ]
    assert all(facts), facts


@pytest.mark.parametrize(
    "invocation",
    [
        Invocation.NORMAL_MASTER,
        Invocation.NORMAL_FACTORY_FOLLOW_UP,
    ],
)
def test_trusted_normal_gate_entrances_ignore_malformed_inherited_flags(
    *, invocation: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Trusted normal callers reach their complete normal body before flag parsing."""
    _clear(monkeypatch=monkeypatch)
    monkeypatch.setenv(_FLAG, "malformed")
    monkeypatch.setenv(_REVERT, "also-malformed")

    decision = incident_gate_entry.resolve_entrance(surface="check", invocation=invocation)

    assert decision.mode == "normal"
    assert decision.status == incident_gate_entry.NORMAL
