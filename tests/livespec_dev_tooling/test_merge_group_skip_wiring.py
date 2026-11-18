"""The committed ci.yml wires the merge-group tree-equality skip exactly as its bounds require.

Work-item livespec-dev-tooling-ymog6r. `test_merge_group_skip.py` proves the verdict and
`test_ci_green_required_legs_guard_skip.py` proves the reader; this module proves the
workflow joins them: the guard always runs, only the gating jobs can be skipped, and
ci-green's reader, replayed over a synthetic skipped run of the REAL workflow, passes
only under the same run's skip=true.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from livespec_dev_tooling.ci_green_required_legs import RunJob, leg_gaps, required_legs

__all__: list[str] = []

_CI_YML = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml"
_SKIP_TERM = "needs.merge-group-guard.outputs.skip != 'true'"
_SKIPPABLE = frozenset(
    {
        "check-python",
        "check-per-file-coverage-shard",
        "check-per-file-coverage",
        "check-coverage",
        "check-python-batch",
        "check-fleet-conformance",
        "check-metadata",
        "check-metadata-batch",
    }
)


def _text() -> str:
    return _CI_YML.read_text(encoding="utf-8")


def _jobs() -> dict[str, Any]:
    loaded: dict[str, Any] = yaml.safe_load(_text())
    jobs: dict[str, Any] = loaded["jobs"]
    return jobs


def _guard_steps() -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = _jobs()["merge-group-guard"]["steps"]
    return steps


def test_the_guard_runs_on_every_event_and_defaults_skip_to_false() -> None:
    guard = _jobs()["merge-group-guard"]
    assert "if" not in guard
    assert guard["outputs"]["skip"] == "${{ steps.skip.outputs.skip || 'false' }}"


def test_the_guard_token_stays_read_only() -> None:
    permissions = _jobs()["merge-group-guard"]["permissions"]
    assert permissions == {
        "actions": "read",
        "checks": "read",
        "contents": "read",
        "pull-requests": "read",
    }


def _skip_step() -> dict[str, Any]:
    return next(step for step in _guard_steps() if step.get("id") == "skip")


def test_the_guard_has_no_event_conditioned_step_and_the_skip_step_cannot_fail_it() -> None:
    assert [step for step in _guard_steps() if "if" in step] == []
    assert _skip_step()["continue-on-error"] is True
    assert 'if [ "$GITHUB_EVENT_NAME" = "merge_group" ]' in _skip_step()["run"]


def test_the_skip_decision_reads_the_group_base_commit_never_the_enqueued_tree() -> None:
    run = _skip_step()["run"]
    assert "tarball/${MG_BASE_SHA}" in run
    assert "PYTHONPATH" in run
    assert "actions/checkout" not in str(_guard_steps())


def test_only_the_gating_jobs_carry_the_skip_term() -> None:
    carrying = {name for name, job in _jobs().items() if _SKIP_TERM in str(job.get("if", ""))}
    assert carrying == _SKIPPABLE


def test_every_skippable_job_still_runs_after_a_failed_guard() -> None:
    jobs = _jobs()
    assert all("!cancelled()" in jobs[name]["if"] for name in _SKIPPABLE)


def test_ci_green_reads_the_guard_signal_through_incident_ci_and_hands_it_to_the_reader() -> None:
    jobs = _jobs()
    gate = jobs["ci-green"]
    reader = next(step for step in gate["steps"] if "required leg" in step["name"])
    assert (
        jobs["incident-ci"]["outputs"]["guard_skip"],
        "merge-group-guard" in gate["needs"],
        gate["if"],
        reader["env"]["GUARD_SKIP"],
        '--guard-skip "$GUARD_SKIP"' in reader["run"],
    ) == (
        "${{ needs.merge-group-guard.outputs.skip }}",
        False,
        "always()",
        "${{ needs.incident-ci.outputs.guard_skip }}",
        True,
    )


def _skipped_run() -> tuple[RunJob, ...]:
    run: list[RunJob] = []
    for job, legs in required_legs(ci_yaml_text=_text(), gate_job="ci-green"):
        conclusion = "success" if job == "incident-ci" else "skipped"
        run.extend(RunJob(name=leg, status="completed", conclusion=conclusion) for leg in legs)
    return tuple(run)


def test_the_real_workflow_reports_a_skipped_run_green_only_under_the_skip_signal() -> None:
    def gaps(*, guard_skip: bool) -> int:
        return len(
            leg_gaps(
                ci_yaml_text=_text(),
                gate_job="ci-green",
                run_jobs=_skipped_run(),
                guard_skip=guard_skip,
            )
        )

    assert (gaps(guard_skip=True), gaps(guard_skip=False) > 0) == (0, True)


def test_an_unskippable_leg_that_never_ran_still_fails_a_skipped_run() -> None:
    without_incident = tuple(run for run in _skipped_run() if run.name != "incident-ci")
    found = leg_gaps(
        ci_yaml_text=_text(), gate_job="ci-green", run_jobs=without_incident, guard_skip=True
    )
    assert [gap.leg for gap in found] == ["incident-ci"]


def test_the_skip_step_logs_the_module_output_prefixed_before_the_decision() -> None:
    run = _skip_step()["run"]
    log = "printf '%s\\n' \"$out\" | sed 's/^/merge_group_skip: /' || true"
    assert log in run
    assert run.index(log) < run.index("grep -qx 'skip=true'")
