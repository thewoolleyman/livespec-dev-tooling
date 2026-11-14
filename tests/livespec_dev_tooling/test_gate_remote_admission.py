"""The paired module-presence test for delegated-gate admission polling."""

from __future__ import annotations

import json
from pathlib import Path

from returns.result import Failure, Success

from livespec_dev_tooling.gate_remote_admission import await_terminal_state
from livespec_dev_tooling.gate_remote_invocation import GateCommandOutcome, GateCommandResult
from livespec_dev_tooling.gate_remote_request import GateRunRequest

__all__: list[str] = []


def test_the_admission_waiter_is_a_public_callable() -> None:
    """The client imports its admission concern through the module's public API."""
    assert callable(await_terminal_state)


def test_an_admitted_job_without_a_terminal_state_uses_its_terminal_bound() -> None:
    """Only a Job that has started can consume the terminal-state poll budget."""
    request = GateRunRequest(
        repo_root=Path("/repo"),
        mirror_url="ssh://mirror/repo.git",
        manifest="apiVersion: batch/v1\nkind: Job\n",
        gate_ref="refs/gates/tree-run",
        poll_timeout_seconds=20.0,
    )
    active = json.dumps({"spec": {"suspend": False}, "status": {}})

    def runner(
        *, argv: list[str], cwd: Path, stdin: str | None = None, stream: bool = False
    ) -> GateCommandOutcome:
        _ = argv, cwd, stdin, stream
        return Success(GateCommandResult(returncode=0, stdout=active, stderr=""))

    def sleeper(*, seconds: float) -> None:
        _ = seconds

    outcome = await_terminal_state(
        request=request,
        runner=runner,
        sleeper=sleeper,
        job_name="gate-widget-7f2qd",
    )

    assert isinstance(outcome, Failure)
    assert (
        outcome.failure().detail
        == "gate-widget-7f2qd was admitted but reached no terminal condition within 20s"
    )


def test_a_watch_window_that_ends_before_the_job_rearms_until_it_gets_the_verdict() -> None:
    """A clean watch-window end is not a no-verdict until the whole budget expires."""
    request = GateRunRequest(
        repo_root=Path("/repo"),
        mirror_url="ssh://mirror/repo.git",
        manifest="apiVersion: batch/v1\nkind: Job\n",
        gate_ref="refs/gates/tree-run",
        poll_timeout_seconds=600.0,
    )
    active = json.dumps({"spec": {"suspend": False}, "status": {}})
    complete = json.dumps({"status": {"conditions": [{"type": "Complete", "status": "True"}]}})
    calls: list[tuple[str, ...]] = []

    def runner(
        *, argv: list[str], cwd: Path, stdin: str | None = None, stream: bool = False
    ) -> GateCommandOutcome:
        _ = cwd, stdin, stream
        calls.append(tuple(argv))
        if len(calls) == 1:
            return Success(GateCommandResult(returncode=0, stdout=active, stderr=""))
        if len(calls) == 2:
            return Success(
                GateCommandResult(
                    returncode=1,
                    stdout="",
                    stderr="Job watch ended before a terminal condition was observed\n",
                )
            )
        return Success(GateCommandResult(returncode=0, stdout=complete, stderr=""))

    def sleeper(*, seconds: float) -> None:
        _ = seconds

    outcome = await_terminal_state(
        request=request,
        runner=runner,
        sleeper=sleeper,
        job_name="gate-widget-7f2qd",
    )

    watches = [argv for argv in calls if "await-gate-terminal-watch" in argv]
    assert isinstance(outcome, Success)
    assert len(watches) == 2
    assert all(argv[-1] == "240s" for argv in watches)


def test_a_watch_that_ends_without_a_verdict_is_rearmed_without_sleeping() -> None:
    """A Job that ends right after a spent watch window is read by an immediate re-arm."""
    request = GateRunRequest(
        repo_root=Path("/repo"),
        mirror_url="ssh://mirror/repo.git",
        manifest="apiVersion: batch/v1\nkind: Job\n",
        gate_ref="refs/gates/tree-run",
        poll_timeout_seconds=600.0,
    )
    active = json.dumps({"spec": {"suspend": False}, "status": {}})
    complete = json.dumps({"status": {"conditions": [{"type": "Complete", "status": "True"}]}})
    watch_stderr = [
        "Job watch ended before a terminal condition was observed\n",
        "kubectl terminal-state watch timed out\n",
    ]
    watches: list[tuple[str, ...]] = []
    naps: list[float] = []

    def runner(
        *, argv: list[str], cwd: Path, stdin: str | None = None, stream: bool = False
    ) -> GateCommandOutcome:
        _ = cwd, stdin, stream
        if "await-gate-terminal-watch" not in argv:
            return Success(GateCommandResult(returncode=0, stdout=active, stderr=""))
        watches.append(tuple(argv))
        if len(watches) <= len(watch_stderr):
            return Success(
                GateCommandResult(returncode=1, stdout="", stderr=watch_stderr[len(watches) - 1])
            )
        return Success(GateCommandResult(returncode=0, stdout=complete, stderr=""))

    def sleeper(*, seconds: float) -> None:
        naps.append(seconds)

    outcome = await_terminal_state(
        request=request,
        runner=runner,
        sleeper=sleeper,
        job_name="gate-widget-7f2qd",
    )

    assert isinstance(outcome, Success)
    assert len(watches) == 3
    assert naps == []
