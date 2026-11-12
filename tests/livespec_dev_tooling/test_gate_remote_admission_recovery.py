"""Coverage for bounded recovery when a terminal-state watch ends normally."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock

from returns.result import Failure, Success

from livespec_dev_tooling.gate_remote_admission import await_terminal_state
from livespec_dev_tooling.gate_remote_invocation import GateCommandOutcome, GateCommandResult
from livespec_dev_tooling.gate_remote_request import GateRunRequest

__all__: list[str] = []


def test_a_watch_timeout_ends_the_terminal_wait_without_restarting_a_poll_loop() -> None:
    """A completed watch timeout is the terminal budget, not a transient API failure."""
    request = GateRunRequest(
        repo_root=Path("/repo"),
        mirror_url="ssh://mirror/repo.git",
        manifest="apiVersion: batch/v1\nkind: Job\n",
        gate_ref="refs/gates/tree-run",
        poll_timeout_seconds=20.0,
    )
    active = json.dumps({"spec": {"suspend": False}, "status": {}})
    calls: list[tuple[str, ...]] = []
    sleeper = Mock()

    def runner(
        *, argv: list[str], cwd: Path, stdin: str | None = None, stream: bool = False
    ) -> GateCommandOutcome:
        _ = cwd, stdin, stream
        calls.append(tuple(argv))
        if len(calls) == 1:
            return Success(GateCommandResult(returncode=0, stdout=active, stderr=""))
        return Success(
            GateCommandResult(
                returncode=1,
                stdout="",
                stderr="Job watch ended before a terminal condition was observed",
            )
        )

    outcome = await_terminal_state(
        request=request,
        runner=runner,
        sleeper=sleeper,
        job_name="gate-widget-7f2qd",
    )

    assert isinstance(outcome, Failure)
    assert len(calls) == 2
    sleeper.assert_not_called()


def test_an_expired_terminal_watch_budget_starts_no_watch_attempt() -> None:
    """A retry is not allowed to extend a terminal wait past its configured budget."""
    request = GateRunRequest(
        repo_root=Path("/repo"),
        mirror_url="ssh://mirror/repo.git",
        manifest="apiVersion: batch/v1\nkind: Job\n",
        gate_ref="refs/gates/tree-run",
        poll_timeout_seconds=20.0,
    )
    active = json.dumps({"spec": {"suspend": False}, "status": {}})
    calls: list[tuple[str, ...]] = []
    sleeper = Mock()
    clock_values = iter((0.0, 20.0))

    def runner(
        *, argv: list[str], cwd: Path, stdin: str | None = None, stream: bool = False
    ) -> GateCommandOutcome:
        _ = cwd, stdin, stream
        calls.append(tuple(argv))
        return Success(GateCommandResult(returncode=0, stdout=active, stderr=""))

    def clock() -> float:
        return next(clock_values)

    outcome = await_terminal_state(
        request=request,
        runner=runner,
        sleeper=sleeper,
        job_name="gate-widget-7f2qd",
        clock=clock,
    )

    assert isinstance(outcome, Failure)
    assert len(calls) == 1
    sleeper.assert_not_called()
