"""Real CI process entrances retain complete normal graphs and honest aggregates."""

from __future__ import annotations

import json
from dataclasses import asdict

import pytest

from livespec_dev_tooling import incident_ci_process as module
from livespec_dev_tooling.incident_ci_policy import CiEvent, CiTarget
from tests.livespec_dev_tooling.test_incident_ci_payload import outcome


def master(*, monkeypatch, tmp_path):
    monkeypatch.setenv("GITHUB_EVENT_NAME", "push")
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GITHUB_SHA", "b" * 40)
    monkeypatch.setenv("EXPEDITED_INCIDENT_RESPONSE", "malformed")
    monkeypatch.setenv("EXPEDITED_INCIDENT_RESPONSE_REVERT", "malformed")
    monkeypatch.setenv("LIVESPEC_INCIDENT_CONTEXT", "malformed")
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        module,
        "load_inventory",
        lambda: (
            CiTarget(name="check-fast", classification="fast"),
            CiTarget(name="check-slow", classification="slow"),
        ),
    )
    (tmp_path / "justfile").write_text(
        'check-fast:\n    test -z "${EXPEDITED_INCIDENT_RESPONSE:-}${EXPEDITED_INCIDENT_RESPONSE_REVERT:-}${LIVESPEC_INCIDENT_CONTEXT:-}"\ncheck-slow:\n    echo normal-slow\n'
    )


def test_normal_master_process_keeps_slow_member_and_writes_all_actual_outcomes(
    monkeypatch, tmp_path, capsys
):
    master(monkeypatch=monkeypatch, tmp_path=tmp_path)
    output = tmp_path / "output"
    summary = tmp_path / "summary"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    assert module.main(argv=["plan"]) == 0
    planned = json.loads(capsys.readouterr().out)
    assert planned["mode"] == "normal" and planned["deferred"] == []
    assert planned["selected"] == ["check-fast", "check-slow"]
    assert "mode=normal" in output.read_text() and "planned" in summary.read_text()
    assert module.main(argv=["run", "--target", "check-fast", "--target", "check-slow"]) == 0
    capsys.readouterr()
    assert module.main(argv=["aggregate"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "passed"


def test_missing_and_failed_selected_members_never_satisfy_master(monkeypatch, tmp_path, capsys):
    master(monkeypatch=monkeypatch, tmp_path=tmp_path)
    assert module.main(argv=["aggregate"]) == 1
    assert json.loads(capsys.readouterr().out)["missing"] == ["check-fast", "check-slow"]
    (tmp_path / "justfile").write_text("check-fast:\n    exit 13\n")
    assert module.main(argv=["run", "--target", "check-fast"]) != 0
    capsys.readouterr()
    assert module.main(argv=["aggregate"]) == 1
    assert json.loads(capsys.readouterr().out)["failed"] == ["check-fast"]


def test_invalid_event_inventory_and_incident_claim_refuse_without_fallback(
    monkeypatch, tmp_path, capsys
):
    master(monkeypatch=monkeypatch, tmp_path=tmp_path)
    monkeypatch.setattr(module, "observe_event", lambda **_: None)
    assert module.main(argv=["plan"]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "refused"
    event = CiEvent(
        kind="pull_request",
        repository="owner/repo",
        base_sha="a" * 40,
        head_sha="b" * 40,
        pr_number=7,
        labels=("expedited-incident-response",),
    )
    monkeypatch.setattr(module, "observe_event", lambda **_: (event, "invalid"))
    assert module.main(argv=["plan"]) == 2
    capsys.readouterr()

    def broken():
        raise ValueError("not a released inventory")

    monkeypatch.setattr(module, "load_inventory", broken)
    assert module.main(argv=["plan"]) == 2
    assert "not a released inventory" not in capsys.readouterr().out


def test_ordinary_pr_plan_ignores_incident_payload_and_needs_no_outputs(
    monkeypatch, tmp_path, capsys
):
    master(monkeypatch=monkeypatch, tmp_path=tmp_path)
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    event = CiEvent(
        kind="pull_request",
        repository="owner/repo",
        base_sha="a" * 40,
        head_sha="b" * 40,
        pr_number=7,
    )
    monkeypatch.setattr(module, "observe_event", lambda **_: (event, "malformed"))
    assert module.main(argv=["plan"]) == 0
    assert json.loads(capsys.readouterr().out)["mode"] == "normal"


def test_outcome_files_are_bounded_strict_and_symlink_free(monkeypatch, tmp_path):
    report = tmp_path / "one.jsonl"
    report.write_text(json.dumps(outcome()) + "\n")
    assert asdict(module.CiProcess.outcomes(directory=tmp_path)[0]) == outcome()
    report.write_text('{"name":"check-fast","name":"check-fast"}\n')
    with pytest.raises(ValueError, match="duplicate"):
        module.CiProcess.outcomes(directory=tmp_path)
    report.write_text(json.dumps(outcome()) + "\n")
    link = tmp_path / "two.jsonl"
    link.symlink_to(report)
    with pytest.raises(ValueError, match="report inventory"):
        module.CiProcess.outcomes(directory=tmp_path)
    link.unlink()
    monkeypatch.setattr(module, "_MAX_REPORT", 1)
    with pytest.raises(ValueError, match="oversized"):
        module.CiProcess.outcomes(directory=tmp_path)


def test_outcome_count_limits_apply_within_and_between_files(monkeypatch, tmp_path):
    monkeypatch.setattr(module, "_MAX_ROWS", 1)
    report = tmp_path / "one.jsonl"
    report.write_text((json.dumps(outcome()) + "\n") * 2)
    with pytest.raises(ValueError, match="too many"):
        module.CiProcess.outcomes(directory=tmp_path)
    report.write_text(json.dumps(outcome()) + "\n")
    (tmp_path / "two.jsonl").write_text("")
    with pytest.raises(ValueError, match="report inventory"):
        module.CiProcess.outcomes(directory=tmp_path)
