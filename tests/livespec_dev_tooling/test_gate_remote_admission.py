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
    assert outcome.failure().detail == "gate-widget-7f2qd reached no terminal condition within 20s"
