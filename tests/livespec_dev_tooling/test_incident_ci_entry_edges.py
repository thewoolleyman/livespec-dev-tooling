"""Actual member selection rechecks authority and retains honest outcome evidence."""

from __future__ import annotations

import json
import os
from dataclasses import replace

import pytest

from livespec_dev_tooling import incident_ci_entry as module
from livespec_dev_tooling._check_target_runner import COMPLETED, LAUNCH_FAILED, TargetOutcome
from livespec_dev_tooling.incident_ci_policy import CiEvent, CiOutcome, CiTarget
from tests.livespec_dev_tooling.test_incident_ci_payload import packet


def event():
    return CiEvent(
        kind="pull_request",
        repository="owner/repo",
        base_sha="a" * 40,
        head_sha="b" * 40,
        pr_number=7,
        labels=("expedited-incident-response",),
    )


def entry(*, tmp_path, current=lambda **_: True, observer=lambda **_: True):
    return module.CiEntry(
        repo=tmp_path,
        targets=(
            CiTarget(name="check-fast", classification="fast"),
            CiTarget(name="check-slow", classification="slow"),
        ),
        current=current,
        observer=observer,
    )


def plan(*, value):
    result = value.plan(
        event=event(),
        payload=json.dumps(packet()),
        environ=dict(os.environ),
    )
    assert result is not None
    return result


def test_real_fast_member_omits_slow_and_strips_incident_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("LIVESPEC_INCIDENT_OBSERVER_QUERY_TOKEN", "controlled-query-only")
    (tmp_path / "justfile").write_text(
        'check-fast:\n    test -z "${EXPEDITED_INCIDENT_RESPONSE:-}${LIVESPEC_INCIDENT_CONTEXT:-}${LIVESPEC_INCIDENT_OBSERVER_QUERY_TOKEN:-}"\ncheck-slow:\n    touch slow-ran\n'
    )
    value = entry(tmp_path=tmp_path)
    selected = plan(value=value)
    report = tmp_path / "results.jsonl"
    assert (
        value.execute(
            plan=selected,
            names=("check-fast", "check-slow"),
            report=report,
            payload=json.dumps(packet()),
            environ=dict(os.environ),
        )
        == 0
    )
    rows = [CiOutcome(**json.loads(line)) for line in report.read_text().splitlines()]
    assert len(rows) == 1 and rows[0].outcome == "passed" and not (tmp_path / "slow-ran").exists()
    result = value.aggregate(
        event=event(), payload=json.dumps(packet()), environ=dict(os.environ), outcomes=tuple(rows)
    )
    assert result["status"] == "passed" and result["deferred"][0]["name"] == "check-slow"


@pytest.mark.parametrize("names", [(), ("check-fast", "check-fast"), ("--help",)])
def test_unknown_duplicate_or_empty_requests_run_nothing(tmp_path, names):
    value = entry(tmp_path=tmp_path)
    assert (
        value.execute(
            plan=plan(value=value),
            names=names,
            report=tmp_path / "no-results",
            payload=json.dumps(packet()),
            environ=dict(os.environ),
        )
        == 2
    )
    assert not (tmp_path / "no-results").exists()


def test_execution_rechecks_before_any_member_and_preserves_failure(tmp_path, monkeypatch):
    value = entry(tmp_path=tmp_path)
    selected = plan(value=value)
    stale = replace(value, current=lambda **_: False)
    assert (
        stale.execute(
            plan=selected,
            names=("check-fast",),
            report=tmp_path / "r",
            payload=json.dumps(packet()),
            environ=dict(os.environ),
        )
        == 2
    )
    for code in (13, -15):
        monkeypatch.setattr(
            module,
            "run_targets",
            lambda *, runs, code=code, **_k: tuple(
                TargetOutcome(name=run.name, status=COMPLETED, returncode=code) for run in runs
            ),
        )
        assert value.execute(
            plan=selected,
            names=("check-fast",),
            report=tmp_path / "r",
            payload=json.dumps(packet()),
            environ=dict(os.environ),
        ) == (13 if code == 13 else 143)

    def unavailable(*, runs, **_k):
        return tuple(
            TargetOutcome(
                name=run.name, status=LAUNCH_FAILED, returncode=127, output="missing just"
            )
            for run in runs
        )

    monkeypatch.setattr(module, "run_targets", unavailable)
    assert (
        value.execute(
            plan=selected,
            names=("check-fast",),
            report=tmp_path / "r",
            payload=json.dumps(packet()),
            environ=dict(os.environ),
        )
        == 127
    )


def test_a_recheck_failing_mid_run_records_finished_members_and_refuses(tmp_path, monkeypatch):
    # One worker, so the second member's launch-time recheck sees the first
    # member's revocation; nothing after a failed recheck launches.
    monkeypatch.setattr(module, "current_allowed_cpu_count", lambda: 1)
    (tmp_path / "justfile").write_text(
        "check-fast:\n    touch revoked\ncheck-slow:\n    touch slow-ran\n"
    )
    value = replace(
        entry(tmp_path=tmp_path),
        targets=(
            CiTarget(name="check-fast", classification="fast"),
            CiTarget(name="check-slow", classification="fast"),
        ),
        current=lambda **_: not (tmp_path / "revoked").exists(),
    )
    report = tmp_path / "results.jsonl"
    assert (
        value.execute(
            plan=plan(value=value),
            names=("check-fast", "check-slow"),
            report=report,
            payload=json.dumps(packet()),
            environ=dict(os.environ),
        )
        == 2
    )
    rows = [CiOutcome(**json.loads(line)) for line in report.read_text().splitlines()]
    assert [(row.name, row.outcome) for row in rows] == [("check-fast", "passed")]
    assert not (tmp_path / "slow-ran").exists()


def test_a_consumer_whose_producer_failed_is_recorded_failed_without_running(tmp_path):
    # Normal mode selects every member, including the coverage pair, so the
    # normal aggregate's producer/consumer edge applies here too.
    (tmp_path / "justfile").write_text(
        "check-per-file-coverage:\n    exit 3\ncheck-coverage:\n    touch consumer-ran\n"
    )
    value = module.CiEntry(
        repo=tmp_path,
        targets=(
            CiTarget(name="check-per-file-coverage", classification="fast"),
            CiTarget(name="check-coverage", classification="fast"),
        ),
    )
    push = CiEvent(kind="push", repository="owner/repo", base_sha="a" * 40, head_sha="b" * 40)
    selected = value.plan(event=push, payload="", environ=dict(os.environ))
    assert selected is not None
    report = tmp_path / "results.jsonl"
    assert (
        value.execute(
            plan=selected,
            names=("check-per-file-coverage", "check-coverage"),
            report=report,
            payload="",
            environ=dict(os.environ),
        )
        == 3
    )
    rows = [CiOutcome(**json.loads(line)) for line in report.read_text().splitlines()]
    assert [(row.name, row.outcome) for row in rows] == [
        ("check-per-file-coverage", "failed"),
        ("check-coverage", "failed"),
    ]
    assert not (tmp_path / "consumer-ran").exists()


@pytest.mark.parametrize("mutation", ["selected", "environment"])
def test_constructed_plan_cannot_execute_slow_members_or_injected_environment(tmp_path, mutation):
    (tmp_path / "justfile").write_text(
        "check-fast:\n    touch executed\ncheck-slow:\n    touch executed\n"
    )
    value = entry(tmp_path=tmp_path)
    original = plan(value=value)
    forged = replace(
        original,
        **(
            {"selected": (value.targets[1],)}
            if mutation == "selected"
            else {"environment": (*original.environment, ("INJECTED", "yes"))}
        ),
    )
    assert forged.scope == original.scope
    assert (
        value.execute(
            plan=forged,
            names=("check-fast", "check-slow"),
            report=tmp_path / "results.jsonl",
            payload=json.dumps(packet()),
            environ=dict(os.environ),
        )
        == 2
    )
    assert not (tmp_path / "executed").exists()
    assert not (tmp_path / "results.jsonl").exists()


@pytest.mark.parametrize("which", ["current", "observer"])
def test_missing_current_or_admitted_endpoint_never_falls_back(tmp_path, which):
    value = entry(tmp_path=tmp_path, **{which: lambda **_: False})
    assert value.plan(event=event(), payload=json.dumps(packet()), environ=dict(os.environ)) is None
    assert (
        value.aggregate(
            event=event(), payload=json.dumps(packet()), environ=dict(os.environ), outcomes=()
        )["status"]
        == "refused"
    )
    assert value.plan(event=event(), payload="not-json", environ=dict(os.environ)) is None


def test_missing_hosted_configuration_and_missing_selected_outcome_refuse(tmp_path):
    value = module.CiEntry(
        repo=tmp_path, targets=(CiTarget(name="check-fast", classification="fast"),)
    )
    assert value.plan(event=event(), payload=json.dumps(packet()), environ=dict(os.environ)) is None
    value = entry(tmp_path=tmp_path)
    assert (
        value.aggregate(
            event=event(), payload=json.dumps(packet()), environ=dict(os.environ), outcomes=()
        )["status"]
        == "failed"
    )
    assert (
        module.CiEntry(repo=tmp_path, targets=()).plan(
            event=replace(event(), kind="push"), payload="bad", environ=dict(os.environ)
        )
        is None
    )


@pytest.mark.parametrize("mutation", ["unknown", "duplicate", "stale", "badoutcome"])
def test_aggregate_refuses_foreign_duplicate_stale_or_unknown_results(tmp_path, mutation):
    value = entry(tmp_path=tmp_path)
    selected = plan(value=value)
    row = CiOutcome(
        name="check-fast", head_sha=event().head_sha, scope=selected.scope, outcome="passed"
    )
    rows = (
        (row, row)
        if mutation == "duplicate"
        else (
            replace(
                row,
                **(
                    {"name": "check-foreign"}
                    if mutation == "unknown"
                    else {"scope": "a" * 64}
                    if mutation == "stale"
                    else {"outcome": "unknown"}
                ),
            ),
        )
    )
    assert (
        value.aggregate(
            event=event(), payload=json.dumps(packet()), environ=dict(os.environ), outcomes=rows
        )["status"]
        == "refused"
    )
