"""The remaining direct gate entrances resolve incident mode before gate work.

`lint-autofix-staged`, `check-commit-pairs-source-and-test`, `check-coverage`
and `check-per-file-coverage` are independently invocable recipes. Each routes
through the shared `incident_gate_entry` boundary before any Ruff mutation,
source/test pairing selection, cached coverage lookup or coverage execution.
"""

from __future__ import annotations

import importlib
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

from livespec_dev_tooling import incident_gate_entry

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-wjmre6
_REPO = Path(__file__).resolve().parents[2]
_SCRIPTS = ("lint-autofix-staged", "check-coverage", "check-per-file-coverage")
_PAIRING = "check-commit-pairs-source-and-test"
_FLAG = "EXPEDITED_INCIDENT_RESPONSE"
_REVERT = "EXPEDITED_INCIDENT_RESPONSE_REVERT"
_REFUSALS = (
    ({_FLAG: "maybe"}, "invalid-incident-flag"),
    ({_REVERT: "2"}, "invalid-incident-flag"),
    ({_FLAG: "1"}, "untrusted-incident-receipt"),
)


def _scrubbed() -> dict[str, str]:
    return {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("GIT_", "EXPEDITED_", "LIVESPEC_INCIDENT_", "COVERAGE_"))
        and key not in {"GITHUB_ACTIONS", "GITHUB_EVENT_NAME"}
    }


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
    staged = (
        "#!/bin/sh\n"
        'case "$*" in "config --get livespec.sandboxExempt") exit 1;; esac\n'
        'touch "$GATE_MARKER"\necho staged.py\nexit 0\n'
    )
    for name, body in (("uv", forward), ("git", staged), ("xargs", staged)):
        _ = (binary / name).write_text(body)
        (binary / name).chmod(0o755)
    return binary


def _run_script(*, root: Path, script: str, flags: dict[str, str]) -> tuple[int, str, bool, str]:
    work = root / script
    work.mkdir()
    binary = _stub_bin(root=work)
    log = work / "uv.log"
    marker = work / "gate-work-launched"
    _ = (work / ".coverage").write_text("cached")
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
            "test_nprocs": "1",
        },
        stdin=subprocess.DEVNULL,
        check=False,
        capture_output=True,
        text=True,
    )
    logged = log.read_text() if log.exists() else ""
    touched = marker.exists() or not (work / ".coverage").exists()
    return completed.returncode, completed.stderr, touched, logged


@pytest.mark.parametrize("script", _SCRIPTS)
@pytest.mark.parametrize(("flags", "code"), _REFUSALS)
def test_remaining_recipe_refuses_an_incident_flag_before_any_gate_work(
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
def test_remaining_recipe_with_both_flags_unset_runs_its_normal_body(
    *, tmp_path: Path, script: str
) -> None:
    _, _, launched, logged = _run_script(
        root=tmp_path, script=script, flags={_FLAG: "", _REVERT: ""}
    )
    facts = ["incident_gate_entry" not in logged, launched]
    assert all(facts), (launched, logged)


def _clear(*, monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        _FLAG,
        _REVERT,
        "LIVESPEC_INCIDENT_CONTEXT",
        "LIVESPEC_INCIDENT_AUTHORITY_QUERY",
        "LIVESPEC_INCIDENT_LOCAL_OPERATION",
    ):
        monkeypatch.delenv(key, raising=False)


@pytest.mark.parametrize(("flags", "code"), _REFUSALS)
def test_pairing_check_refuses_before_source_test_pairing_selection(
    *,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    flags: dict[str, str],
    code: str,
) -> None:
    pairing = importlib.import_module("livespec_dev_tooling.checks.commit_pairs_source_and_test")
    _clear(monkeypatch=monkeypatch)
    for name, value in flags.items():
        monkeypatch.setenv(name, value)
    selection = Mock(side_effect=AssertionError("load_config_or_report"))
    monkeypatch.setattr(pairing, "load_config_or_report", selection)
    status = pairing.main()
    stderr = capsys.readouterr().err
    facts = [
        status == incident_gate_entry.REFUSED,
        f"incident-gate-refused: {_PAIRING}: {code}" in stderr,
        selection.call_count == 0,
    ]
    assert all(facts), (status, stderr, selection.call_count)


def test_pairing_check_with_both_flags_unset_runs_its_normal_body(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    pairing = importlib.import_module("livespec_dev_tooling.checks.commit_pairs_source_and_test")
    _clear(monkeypatch=monkeypatch)
    monkeypatch.setenv(_FLAG, "0")
    selection = Mock(side_effect=RuntimeError("normal body reached"))
    monkeypatch.setattr(pairing, "load_config_or_report", selection)
    with pytest.raises(RuntimeError, match="normal body reached"):
        _ = pairing.main()
    assert selection.call_count == 1


def test_every_remaining_surface_is_a_registered_entrance() -> None:
    surfaces = {*_SCRIPTS, _PAIRING}
    assert surfaces <= incident_gate_entry.ENTRANCES
