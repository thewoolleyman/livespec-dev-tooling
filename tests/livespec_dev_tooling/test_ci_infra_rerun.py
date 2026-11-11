"""Tests for `ci_infra_rerun`, the planner behind `reusable-ci-infra-rerun.yml`.

The scenario test drives `main()` end to end, the way the reusable workflow
does, over a RECORDED runner log: `tests/fixtures/ci_infra_rerun/setup-job-429.log`
is livespec-orchestrator-beads-fabro job 125948122947 (run 41645065357), one of
the ten jobs a codeload 429 burst killed at `Set up job` on 2026-11-03 13:33Z.
It replays four attempts of one run: the first three re-run the job with a
growing wait, the fourth leaves it at the attempt cap, and a job that failed at
a later step is left as the verdict on every attempt.

No `An action could not be found` log survives from that burst, so that
signature's case uses a line in the runner's message format rather than a
recorded log.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import cast

import pytest

from livespec_dev_tooling.ci_infra_rerun import (
    CLASSIFIERS,
    LeftJob,
    RecordedJob,
    RerunPlan,
    jobs_needing_logs,
    main,
    parse_jobs,
    plan_payload,
    plan_reruns,
    summary_lines,
)

__all__: list[str] = []

_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_RECORDED_429_LOG = (_FIXTURES / "ci_infra_rerun" / "setup-job-429.log").read_text(encoding="utf-8")
_SETUP = "Set up job"
_INITIALIZE_CONTAINERS = "Initialize containers"
_NOT_FOUND_LINE = (
    "2026-11-03T13:40:01.0000000Z ##[error]An action could not be found at the URI "
    "'https://api.github.com/repos/actions/checkout/tarball/11d5960a'"
)
_PLAIN_SETUP_FAILURE = "2026-11-03T13:40:01.0000000Z ##[error]Runner disk is full\n"


def _job(
    *,
    attempt: int,
    job_id: int,
    name: str,
    failed_step: str | None,
    conclusion: str = "failure",
    later_step_started: bool = False,
) -> dict[str, object]:
    steps: list[dict[str, object]] = [{"name": _SETUP, "conclusion": "success"}]
    if failed_step == _SETUP:
        steps = [{"name": _SETUP, "conclusion": "failure"}]
    elif failed_step is not None:
        steps.append({"name": failed_step, "conclusion": "failure"})
    if later_step_started:
        steps.append({"name": "just check", "conclusion": "success"})
    return {
        "attempt": attempt,
        "id": job_id,
        "name": name,
        "conclusion": conclusion,
        "steps": steps,
    }


def _run_plan(
    *, tmp_path: Path, jobs: list[dict[str, object]], run_attempt: int, logs: dict[int, str]
) -> tuple[int, dict[str, object], str]:
    """Run `main plan` over files the way the workflow writes them; return code, plan, summary."""
    jobs_path = tmp_path / f"jobs-{run_attempt}.json"
    _ = jobs_path.write_text(json.dumps(jobs), encoding="utf-8")
    logs_dir = tmp_path / f"logs-{run_attempt}"
    logs_dir.mkdir()
    for job_id, text in logs.items():
        _ = (logs_dir / f"{job_id}.log").write_text(text, encoding="utf-8")
    plan_out = tmp_path / f"plan-{run_attempt}.json"
    summary_out = tmp_path / f"summary-{run_attempt}.md"
    code = main(
        argv=[
            "plan",
            "--jobs",
            str(jobs_path),
            "--run-attempt",
            str(run_attempt),
            "--logs-dir",
            str(logs_dir),
            "--plan-out",
            str(plan_out),
            "--summary-out",
            str(summary_out),
            "--repository",
            "thewoolleyman/livespec-dev-tooling",
            "--run-id",
            "41645065357",
        ]
    )
    payload = cast("dict[str, object]", json.loads(plan_out.read_text(encoding="utf-8")))
    return code, payload, summary_out.read_text(encoding="utf-8")


@pytest.mark.integration
def test_a_setup_job_429_is_rerun_with_growing_waits_up_to_three_attempts(
    tmp_path: Path,
) -> None:
    """Scenario: a CI job killed at Set up job by an action-download 429 is re-run with backoff."""
    later = _job(attempt=1, job_id=900, name="check-lint", failed_step="just check-lint")
    jobs: list[dict[str, object]] = [later]
    codes: list[int] = []
    waits: list[object] = []
    recorded_logs: dict[int, str] = {}
    attempts: list[list[object]] = []
    lefts: list[list[object]] = []
    summaries: list[str] = []
    for attempt, job_id in ((1, 101), (2, 102), (3, 103), (4, 104)):
        jobs.append(
            _job(attempt=attempt, job_id=job_id, name="check-types (root)", failed_step=_SETUP)
        )
        jobs.extend([{**later, "attempt": attempt}] if attempt > 1 else [])
        recorded_logs[job_id] = _RECORDED_429_LOG
        code, payload, summary = _run_plan(
            tmp_path=tmp_path, jobs=jobs, run_attempt=attempt, logs=dict(recorded_logs)
        )
        codes.append(code)
        reruns = cast("list[dict[str, object]]", payload["reruns"])
        attempts.append([rerun["attempt"] for rerun in reruns])
        lefts.append([left["name"] for left in cast("list[dict[str, object]]", payload["left"])])
        waits.append(payload["wait_seconds"])
        summaries.append(summary)

    assert codes == [0, 0, 0, 0]

    assert attempts == [[1], [2], [3], []]
    assert waits == [120, 300, 600, 0]
    assert "attempt 1 of 3" in summaries[0]
    assert "check-types (root)" in summaries[0]
    assert "signature action-download-429" in summaries[0]
    assert "429 (Too Many Requests)" in summaries[0]
    assert all("left for its owner: job 'check-lint'" in summary for summary in summaries)
    assert "the attempt cap is reached" in summaries[3]
    assert lefts == [
        ["check-lint"],
        ["check-lint"],
        ["check-lint"],
        ["check-types (root)", "check-lint"],
    ]


def test_an_action_not_found_at_set_up_job_is_rerun() -> None:
    jobs = parse_jobs(payload=[_job(attempt=1, job_id=7, name="check-e2e", failed_step=_SETUP)])
    assert jobs is not None

    plan = plan_reruns(jobs=jobs, run_attempt=1, logs={7: f"{_NOT_FOUND_LINE}\n"})

    assert [r.signature for r in plan.reruns] == ["action-not-found"]
    assert plan.reruns[0].matched_line == _NOT_FOUND_LINE


@pytest.mark.integration
def test_initialize_containers_registry_network_failures_rerun_once_before_any_later_step(
    tmp_path: Path,
) -> None:
    """Scenario: registry failures before a job starts re-run once and are summarized."""
    logs = {
        101: "##[error]pkg-containers.githubusercontent.com: connection reset by peer\n",
        102: "##[error]pulling ghcr.io/example/image: i/o timeout\n",
        103: "##[error]pulling ghcr.io/example/image: TLS handshake timeout\n",
        104: "##[error]Head https://ghcr.io/v2/example: 503 Service Unavailable\n",
        105: "##[error]pkg-containers.githubusercontent.com: connection reset by peer\n",
        106: "##[error]Pod workflow-123 is unhealthy with phase status Failed\n",
        107: "##[error]pkg-containers.githubusercontent.com: connection reset by peer\n",
    }
    first_attempt = [
        _job(attempt=1, job_id=job_id, name=f"check-{job_id}", failed_step=_INITIALIZE_CONTAINERS)
        for job_id in (101, 102, 103, 104)
    ]
    first_attempt.extend(
        [
            _job(
                attempt=1,
                job_id=105,
                name="started-later",
                failed_step=_INITIALIZE_CONTAINERS,
                later_step_started=True,
            ),
            _job(
                attempt=1,
                job_id=106,
                name="unhealthy-pod",
                failed_step=_INITIALIZE_CONTAINERS,
            ),
        ]
    )
    first_code, first_payload, first_summary = _run_plan(
        tmp_path=tmp_path,
        jobs=first_attempt,
        run_attempt=1,
        logs=logs,
    )

    first_reruns = cast("list[dict[str, object]]", first_payload["reruns"])
    assert first_code == 0
    assert [
        (rerun["job_id"], rerun["signature"], rerun["max_attempts"]) for rerun in first_reruns
    ] == [
        (101, "registry-connection-reset", 1),
        (102, "registry-io-timeout", 1),
        (103, "registry-tls-handshake-timeout", 1),
        (104, "registry-5xx", 1),
    ]
    assert first_payload["wait_seconds"] <= 300
    assert "run 41645065357" in first_summary
    assert "job 'check-101' (id 101)" in first_summary
    assert logs[101].strip() in first_summary
    assert "left for its owner: job 'started-later'" in first_summary
    assert "left for its owner: job 'unhealthy-pod'" in first_summary

    next_jobs = [
        *first_attempt,
        _job(
            attempt=2,
            job_id=107,
            name="check-101",
            failed_step=_INITIALIZE_CONTAINERS,
        ),
    ]
    retry_code, retry_payload, retry_summary = _run_plan(
        tmp_path=tmp_path,
        jobs=next_jobs,
        run_attempt=2,
        logs=logs,
    )

    assert retry_code == 0
    assert retry_payload["reruns"] == []
    assert "left for its owner: job 'check-101'" in retry_summary
    assert "already re-run 1 times" in retry_summary


def test_a_setup_job_failure_without_the_signature_or_its_log_is_left() -> None:
    jobs = parse_jobs(
        payload=[
            _job(attempt=1, job_id=1, name="no-signature", failed_step=_SETUP),
            _job(attempt=1, job_id=2, name="no-log", failed_step=_SETUP),
        ]
    )
    assert jobs is not None

    plan = plan_reruns(jobs=jobs, run_attempt=1, logs={1: _PLAIN_SETUP_FAILURE})

    assert plan.reruns == ()
    assert [left.reason for left in plan.left] == [
        "failed at 'Set up job' without a set-up-job action download signature",
        "failed at 'Set up job', but its log was not readable",
    ]


def test_a_job_whose_log_was_not_fetched_is_left_through_main(tmp_path: Path) -> None:
    jobs = [_job(attempt=1, job_id=8, name="check-docs", failed_step=_SETUP)]

    code, payload, summary = _run_plan(tmp_path=tmp_path, jobs=jobs, run_attempt=1, logs={})

    assert code == 0
    assert payload["rerun_count"] == 0
    assert "its log was not readable" in summary


def test_a_job_copied_unchanged_into_a_later_attempt_is_not_counted_twice() -> None:
    copied = _job(attempt=1, job_id=5, name="check-format", failed_step=_SETUP)
    jobs = parse_jobs(payload=[copied, {**copied, "attempt": 2}])
    assert jobs is not None

    plan = plan_reruns(jobs=jobs, run_attempt=2, logs={5: _RECORDED_429_LOG})

    assert [(r.attempt, r.wait_seconds) for r in plan.reruns] == [(1, 120)]


def test_only_the_current_attempts_failed_classified_jobs_need_logs() -> None:
    jobs = parse_jobs(
        payload=[
            _job(attempt=1, job_id=1, name="a", failed_step=_SETUP),
            _job(attempt=2, job_id=2, name="a", failed_step=_SETUP),
            _job(attempt=2, job_id=3, name="b", failed_step="just check-lint"),
            _job(attempt=2, job_id=4, name="c", failed_step=None, conclusion="success"),
            _job(attempt=2, job_id=5, name="d", failed_step=_SETUP, conclusion="cancelled"),
        ]
    )
    assert jobs is not None

    assert jobs_needing_logs(jobs=jobs, run_attempt=2) == (1, 2)


def test_an_earlier_non_registry_initialize_failure_does_not_consume_the_one_rerun() -> None:
    jobs = parse_jobs(
        payload=[
            _job(attempt=1, job_id=1, name="check-a", failed_step=_INITIALIZE_CONTAINERS),
            _job(attempt=2, job_id=2, name="check-a", failed_step=_INITIALIZE_CONTAINERS),
        ]
    )
    assert jobs is not None
    pod = "##[error]Pod workflow-1 is unhealthy with phase status Failed\n"
    reset = "##[error]pkg-containers.githubusercontent.com: connection reset by peer\n"

    assert jobs_needing_logs(jobs=jobs, run_attempt=2) == (1, 2)
    plan = plan_reruns(jobs=jobs, run_attempt=2, logs={1: pod, 2: reset})

    assert [(r.job_id, r.attempt) for r in plan.reruns] == [(2, 1)]


def test_an_earlier_initialize_failure_with_an_unreadable_log_does_not_consume_the_one_rerun() -> (
    None
):
    jobs = parse_jobs(
        payload=[
            _job(attempt=1, job_id=1, name="check-a", failed_step=_INITIALIZE_CONTAINERS),
            _job(attempt=2, job_id=2, name="check-a", failed_step=_INITIALIZE_CONTAINERS),
        ]
    )
    assert jobs is not None
    reset = "##[error]pkg-containers.githubusercontent.com: connection reset by peer\n"

    plan = plan_reruns(jobs=jobs, run_attempt=2, logs={2: reset})

    assert [(r.job_id, r.attempt) for r in plan.reruns] == [(2, 1)]
    assert plan.left == ()


def test_an_earlier_registry_initialize_failure_consumes_the_one_rerun() -> None:
    jobs = parse_jobs(
        payload=[
            _job(attempt=1, job_id=1, name="check-a", failed_step=_INITIALIZE_CONTAINERS),
            _job(attempt=2, job_id=2, name="check-a", failed_step=_INITIALIZE_CONTAINERS),
        ]
    )
    assert jobs is not None
    reset = "##[error]pkg-containers.githubusercontent.com: connection reset by peer\n"

    plan = plan_reruns(jobs=jobs, run_attempt=2, logs={1: reset, 2: reset})

    assert plan.reruns == ()
    assert [left.job_id for left in plan.left] == [2]


def test_log_jobs_prints_the_ids_whose_logs_to_fetch(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    jobs_path = tmp_path / "jobs.json"
    _ = jobs_path.write_text(
        json.dumps(
            [
                _job(attempt=1, job_id=11, name="a", failed_step=_SETUP),
                _job(attempt=1, job_id=12, name="b", failed_step="just check-lint"),
                _job(attempt=1, job_id=13, name="c", failed_step=_SETUP),
            ]
        ),
        encoding="utf-8",
    )

    code = main(argv=["log-jobs", "--jobs", str(jobs_path), "--run-attempt", "1"])

    assert code == 0
    assert capsys.readouterr().out == "11\n13\n"


def test_module_runs_under_the_reusable_workflow_bare_pythonpath(*, tmp_path: Path) -> None:
    """The reusable workflow's system Python imports the repository's vendored structlog."""
    jobs_path = tmp_path / "jobs.json"
    log_dir = tmp_path / "logs"
    plan_path = tmp_path / "plan.json"
    summary_path = tmp_path / "summary.md"
    log_dir.mkdir()
    _ = jobs_path.write_text(
        json.dumps([_job(attempt=1, job_id=73, name="check", failed_step=_SETUP)]),
        encoding="utf-8",
    )
    _ = (log_dir / "73.log").write_text(_RECORDED_429_LOG, encoding="utf-8")
    environment = {
        "HOME": str(tmp_path),
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "PYTHONPATH": str(_REPOSITORY_ROOT),
    }

    log_jobs = subprocess.run(
        [
            "python3",
            "-m",
            "livespec_dev_tooling.ci_infra_rerun",
            "log-jobs",
            "--jobs",
            str(jobs_path),
            "--run-attempt",
            "1",
        ],
        capture_output=True,
        check=False,
        cwd=_REPOSITORY_ROOT,
        env=environment,
        text=True,
    )
    plan = subprocess.run(
        [
            "python3",
            "-m",
            "livespec_dev_tooling.ci_infra_rerun",
            "plan",
            "--jobs",
            str(jobs_path),
            "--run-attempt",
            "1",
            "--logs-dir",
            str(log_dir),
            "--plan-out",
            str(plan_path),
            "--summary-out",
            str(summary_path),
            "--repository",
            "thewoolleyman/livespec-dev-tooling",
            "--run-id",
            "41645065357",
        ],
        capture_output=True,
        check=False,
        cwd=_REPOSITORY_ROOT,
        env=environment,
        text=True,
    )

    assert log_jobs.returncode == 0, log_jobs.stderr
    assert log_jobs.stdout == "73\n"
    assert plan.returncode == 0, plan.stderr
    reruns = json.loads(plan_path.read_text(encoding="utf-8"))["reruns"]
    assert [rerun["job_id"] for rerun in reruns] == [73]
    assert [rerun["signature"] for rerun in reruns] == ["action-download-429"]


def test_unreadable_or_malformed_recorded_jobs_plan_nothing(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"
    not_json = tmp_path / "not.json"
    _ = not_json.write_text("{", encoding="utf-8")
    plan_out = tmp_path / "plan.json"
    codes = [
        main(
            argv=[
                "plan",
                "--jobs",
                str(path),
                "--run-attempt",
                "1",
                "--logs-dir",
                str(tmp_path),
                "--plan-out",
                str(plan_out),
                "--summary-out",
                str(tmp_path / "summary.md"),
                "--repository",
                "r",
                "--run-id",
                "1",
            ]
        )
        for path in (missing, not_json)
    ]

    assert codes == [1, 1]
    assert not plan_out.exists()


@pytest.mark.parametrize(
    "payload",
    [
        {"not": "a list"},
        ["not a record"],
        [{"attempt": "1", "id": 1, "name": "a", "steps": []}],
        [{"attempt": 1, "id": 1, "name": "a", "steps": "not a list"}],
        [{"attempt": 1, "id": 1, "name": "a", "steps": ["not a step"]}],
        [{"attempt": 1, "id": 1, "name": "a", "steps": [{"conclusion": "failure"}]}],
    ],
)
def test_a_malformed_recording_parses_to_none(payload: object) -> None:
    assert parse_jobs(payload=payload) is None


def test_a_record_without_a_string_conclusion_is_not_a_failure() -> None:
    record: dict[str, object] = {"attempt": 1, "id": 1, "name": "a", "steps": []}
    jobs = parse_jobs(payload=[record])
    assert jobs is not None

    assert jobs == (
        RecordedJob(attempt=1, job_id=1, name="a", conclusion="", first_failed_step=None),
    )
    assert plan_reruns(jobs=jobs, run_attempt=1, logs={}) == RerunPlan(reruns=(), left=())


def test_an_empty_plan_says_so_and_waits_for_nothing() -> None:
    plan = RerunPlan(reruns=(), left=())

    assert plan_payload(plan=plan) == {
        "rerun_count": 0,
        "left_count": 0,
        "wait_seconds": 0,
        "reruns": [],
        "left": [],
    }
    assert summary_lines(plan=plan, repository="r", run_id="1")[1:] == [
        "- no failed job in the run's current attempt"
    ]


def test_a_left_job_is_named_in_the_payload() -> None:
    plan = RerunPlan(reruns=(), left=(LeftJob(job_id=3, name="x", reason="why"),))

    assert plan_payload(plan=plan)["left"] == [{"job_id": 3, "name": "x", "reason": "why"}]


def test_every_classifier_covers_a_runner_step_with_growing_waits() -> None:
    facts = [
        (
            clf.step in {"Set up job", "Initialize containers"},
            len(clf.waits_seconds) >= 1,
            list(clf.waits_seconds) == sorted(set(clf.waits_seconds)),
            len(clf.signatures) >= 1,
        )
        for clf in CLASSIFIERS
    ]

    assert facts
    assert all(all(fact) for fact in facts)
