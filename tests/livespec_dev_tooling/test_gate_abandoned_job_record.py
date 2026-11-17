"""An abandoned gate Job's last log lines are saved before the Job is deleted.

The delegated client used to delete a Job that reached no terminal condition and
keep nothing of what its containers had said, so the step that hung could never
be named (livespec-dev-tooling-yrjatv). Before it deletes the Job the client now
saves the last 200 log lines of every container of the Job's pod to a file beside
the gate run's own record, and the no-verdict refusal names that file. The pod
prints its own process tree into those lines (`gate-process-tree-watchdog.sh`),
so the client needs no pods/exec credential.

Every test runs against a canned runner: the client's only reach into the world.
"""

from __future__ import annotations

import dataclasses
import json
import signal
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from returns.result import Failure, Success

from livespec_dev_tooling._gate_abandoned_job_record import abandoned_job_record_path
from livespec_dev_tooling.gate_remote_client import GateRunRequest, run_gate
from livespec_dev_tooling.gate_remote_invocation import (
    GateCommandNotRun,
    GateCommandOutcome,
    GateCommandResult,
)

if TYPE_CHECKING:
    from collections.abc import Callable

__all__: list[str] = []

_JOB = "gate-widget-7f2qd"
_POD = "gate-widget-7f2qd-x9k4p"
_CREATED = json.dumps({"apiVersion": "batch/v1", "kind": "Job", "metadata": {"name": _JOB}})
_SUSPENDED = json.dumps(
    {
        "spec": {"suspend": True},
        "status": {"conditions": [{"type": "Suspended", "status": "False"}]},
    }
)
_PODS = json.dumps(
    {
        "items": [
            {
                "metadata": {"name": _POD},
                "spec": {
                    "initContainers": [{"name": "fetch-tree"}],
                    "containers": [{"name": "gate"}],
                },
            }
        ]
    }
)
_TREE_LINE = "  4242  4100 00:31:07 S  \\_ sleep 99999"


def _request(*, repo_root: Path) -> GateRunRequest:
    return GateRunRequest(
        repo_root=repo_root,
        mirror_url="host:/mirror/widget.git",
        manifest="kind: Job\n",
        gate_ref="refs/gates/abc-1",
        admission_timeout_seconds=20.0,
        poll_timeout_seconds=20.0,
    )


def _cluster(
    *,
    deleted: list[str],
    refuse: str = "",
    pods: str = _PODS,
    logs_for: Callable[[str], str] | None = None,
) -> Callable[..., GateCommandOutcome]:
    """A canned cluster whose Job never leaves Suspended, recording the order of its calls."""

    def runner(
        *, argv: list[str], cwd: Path, stdin: str | None = None, stream: bool = False
    ) -> GateCommandOutcome:
        _ = (cwd, stdin, stream)
        code, out, err = 0, _SUSPENDED, ""
        if "create" in argv:
            out = _CREATED
        elif "delete" in argv and "job" in argv:
            deleted.append("job")
            out = ""
        elif "--delete" in argv:
            deleted.append("ref")
            out = ""
        elif "logs" in argv:
            deleted.append("logs")
            container = argv[argv.index("--container") + 1]
            assert argv[argv.index("--tail") + 1] == "200"
            out = logs_for(container) if logs_for else f"{container} said hello\n"
            code, out, err = (1, "", "logs refused\n") if refuse == "logs" else (0, out, "")
        elif "pods" in argv and "json" in argv:
            out = pods
            code, out, err = (1, "", "pods refused\n") if refuse == "pods" else (0, out, "")
        return Success(GateCommandResult(returncode=code, stdout=out, stderr=err))

    return runner


def _no_sleep(*, seconds: float) -> None:
    _ = seconds


def test_a_no_verdict_refusal_names_the_saved_file_that_holds_every_containers_last_lines(
    *, tmp_path: Path
) -> None:
    """Logs of the init and the gate container land in the file the refusal names, before the delete."""
    order: list[str] = []

    def logs_for(container: str) -> str:
        return f"{container} said hello\n{_TREE_LINE}\n" if container == "gate" else "fetched\n"

    request = _request(repo_root=tmp_path)
    outcome = run_gate(
        request=request, runner=_cluster(deleted=order, logs_for=logs_for), sleeper=_no_sleep
    )
    assert isinstance(outcome, Failure)
    saved = abandoned_job_record_path(request=request, job_name=_JOB)
    text = saved.read_text(encoding="utf-8")
    facts = [
        str(saved) in outcome.failure().detail,
        "fetch-tree" in text,
        "fetched" in text,
        "gate said hello" in text,
        _TREE_LINE in text,
        order.index("logs") < order.index("job"),
    ]
    assert all(facts)


def test_the_saved_file_sits_in_the_gate_runs_own_record_directory_when_one_is_named(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The gate runner's progress stamp lives in the run's directory, and the file lands beside it."""
    run_dir = tmp_path / "gate-runs" / "20261117T000000Z-1"
    run_dir.mkdir(parents=True)
    monkeypatch.setenv("LIVESPEC_GATE_RUN_PROGRESS_STAMP", str(run_dir / "progress.stamp"))
    request = _request(repo_root=tmp_path / "elsewhere")
    assert abandoned_job_record_path(request=request, job_name=_JOB).parent == run_dir


def test_a_log_read_that_fails_is_recorded_in_the_file_and_the_job_is_still_deleted(
    *, tmp_path: Path
) -> None:
    """A refused read never stops the delete, and the file says what was refused."""
    order: list[str] = []
    request = _request(repo_root=tmp_path)
    outcome = run_gate(
        request=request, runner=_cluster(deleted=order, refuse="logs"), sleeper=_no_sleep
    )
    assert isinstance(outcome, Failure)
    saved = abandoned_job_record_path(request=request, job_name=_JOB)
    text = saved.read_text(encoding="utf-8")
    assert all(["logs refused" in text, "job" in order, str(saved) in outcome.failure().detail])


def test_a_pod_list_that_fails_is_recorded_in_the_file_and_the_job_is_still_deleted(
    *, tmp_path: Path
) -> None:
    """A refused pod read is recorded the same way."""
    order: list[str] = []
    request = _request(repo_root=tmp_path)
    outcome = run_gate(
        request=request, runner=_cluster(deleted=order, refuse="pods"), sleeper=_no_sleep
    )
    assert isinstance(outcome, Failure)
    saved = abandoned_job_record_path(request=request, job_name=_JOB)
    text = saved.read_text(encoding="utf-8")
    assert all(["pods refused" in text, "job" in order])


def test_an_interrupted_wait_saves_the_logs_and_names_the_file(*, tmp_path: Path) -> None:
    """A signal that stops the wait goes through the same save, and the refusal names the file."""
    order: list[str] = []
    request = _request(repo_root=tmp_path)

    def interrupted_sleep(*, seconds: float) -> None:
        _ = seconds
        signal.raise_signal(signal.SIGTERM)

    outcome = run_gate(
        request=dataclasses.replace(request, poll_interval_seconds=1.0),
        runner=_cluster(deleted=order),
        sleeper=interrupted_sleep,
    )
    assert isinstance(outcome, Failure)
    saved = abandoned_job_record_path(request=request, job_name=_JOB)
    assert all(
        [
            str(saved) in outcome.failure().detail,
            saved.read_text(encoding="utf-8") != "",
            order.index("logs") < order.index("job"),
        ]
    )


@pytest.mark.parametrize(
    ("pods", "expected"),
    [
        ("not json", "unreadable answer"),
        (json.dumps({"items": []}), "had no pod"),
    ],
)
def test_an_unusable_pod_answer_is_recorded_and_the_job_is_still_deleted(
    *, tmp_path: Path, pods: str, expected: str
) -> None:
    """A pod list that is not JSON, or names no pod, is said so in the file."""
    order: list[str] = []
    request = _request(repo_root=tmp_path)
    outcome = run_gate(
        request=request, runner=_cluster(deleted=order, pods=pods), sleeper=_no_sleep
    )
    assert isinstance(outcome, Failure)
    saved = abandoned_job_record_path(request=request, job_name=_JOB)
    assert all([expected in saved.read_text(encoding="utf-8"), "job" in order])


def test_a_file_that_cannot_be_written_never_stops_the_delete(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The record's own directory being a regular file leaves the delete and the refusal intact."""
    monkeypatch.delenv("LIVESPEC_GATE_RUN_PROGRESS_STAMP", raising=False)
    order: list[str] = []
    blocker = tmp_path / "tmp"
    _ = blocker.write_text("in the way", encoding="utf-8")
    outcome = run_gate(
        request=_request(repo_root=tmp_path), runner=_cluster(deleted=order), sleeper=_no_sleep
    )
    assert isinstance(outcome, Failure)
    assert all(["job" in order, outcome.failure().step == "await-gate-terminal"])


def test_a_command_that_never_ran_is_recorded_as_not_run(*, tmp_path: Path) -> None:
    """A kubectl that is not installed reads as `did not run`, not as a refusal."""
    order: list[str] = []
    inner = _cluster(deleted=order)

    def runner(
        *, argv: list[str], cwd: Path, stdin: str | None = None, stream: bool = False
    ) -> GateCommandOutcome:
        if "pods" in argv and "json" in argv:
            return Failure(GateCommandNotRun(argv=tuple(argv), detail="kubectl not on PATH"))
        return inner(argv=argv, cwd=cwd, stdin=stdin, stream=stream)

    request = _request(repo_root=tmp_path)
    outcome = run_gate(request=request, runner=runner, sleeper=_no_sleep)
    assert isinstance(outcome, Failure)
    saved = abandoned_job_record_path(request=request, job_name=_JOB)
    assert all(
        ["did not run: kubectl not on PATH" in saved.read_text(encoding="utf-8"), "job" in order]
    )
