"""Tests for the bounded commands used by delegated gate waits."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import time
from pathlib import Path

import pytest
from returns.result import Failure, Success

from livespec_dev_tooling.gate_remote_admission import await_terminal_state
from livespec_dev_tooling.gate_remote_invocation import (
    GateCommandOutcome,
    GateCommandResult,
    default_gate_command_runner,
)
from livespec_dev_tooling.gate_remote_request import GateRunRequest
from livespec_dev_tooling.gate_remote_wait_commands import (
    admission_read_argv,
    terminal_watch_argv,
)

__all__: list[str] = []


def test_admission_reads_are_wrapped_and_bounded() -> None:
    """Admission reads keep the credential wrapper and their request deadline."""
    argv = admission_read_argv(namespace="gates", job_name="gate-widget-7f2qd")

    assert argv[:3] == ["with-gates-kubeconfig", "sh", "-ceu"]
    assert 'timeout 270s "$@" --output json --request-timeout=240s' in argv[3]
    assert argv[4:] == [
        "await-gate-admission-read",
        "kubectl",
        "--namespace",
        "gates",
        "get",
        "job",
        "gate-widget-7f2qd",
    ]


def test_terminal_watches_cap_the_window_and_renew_progress() -> None:
    """A terminal watch has a 240-second cap while the Job remains running."""
    argv = terminal_watch_argv(
        namespace="gates",
        job_name="gate-widget-7f2qd",
        remaining_seconds=999.0,
    )

    assert argv[:3] == ["with-gates-kubeconfig", "sh", "-ceu"]
    assert "sleep 30" in argv[3]
    assert 'kubectl --namespace "$namespace" get job "$job_name" --watch --output json' in argv[3]
    assert argv[4:] == [
        "await-gate-terminal-watch",
        "gate-widget-7f2qd",
        "gates",
        "240s",
    ]


def test_terminal_watches_round_a_short_remaining_wait_up_to_one_second() -> None:
    """A nonzero watch deadline never becomes an invalid zero-second request."""
    argv = terminal_watch_argv(
        namespace="gates",
        job_name="gate-widget-7f2qd",
        remaining_seconds=0.1,
    )

    assert argv[-1] == "1s"


@pytest.mark.parametrize(
    ("argv", "kubectl_output"),
    [
        (
            admission_read_argv(namespace="gates", job_name="gate-widget-7f2qd"),
            '{"spec":{"suspend":false},"status":{}}',
        ),
        (
            terminal_watch_argv(
                namespace="gates", job_name="gate-widget-7f2qd", remaining_seconds=999.0
            ),
            '{"status":{"conditions":[{"type":"Complete","status":"True"}]}}',
        ),
    ],
)
def test_completed_wait_commands_release_the_captured_runner_promptly(
    *,
    argv: list[str],
    kubectl_output: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The heartbeat must not retain the runner's pipes after a Job response."""
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()
    wrapper = stub_dir / "with-gates-kubeconfig"
    _ = wrapper.write_text('#!/bin/sh\nexec "$@"\n', encoding="utf-8")
    wrapper.chmod(0o755)
    kubectl = stub_dir / "kubectl"
    _ = kubectl.write_text(
        f"#!/bin/sh\nprintf '%s\\n' '{kubectl_output}'\n",
        encoding="utf-8",
    )
    kubectl.chmod(0o755)
    monkeypatch.setenv("PATH", f"{stub_dir}{os.pathsep}{os.environ['PATH']}")

    started = time.monotonic()
    outcome = default_gate_command_runner(argv=argv, cwd=tmp_path)
    elapsed = time.monotonic() - started

    assert isinstance(outcome, Success)
    assert outcome.unwrap().returncode == 0
    assert elapsed < 10.0


@pytest.mark.parametrize(
    ("argv", "kubectl_output"),
    [
        (
            admission_read_argv(namespace="gates", job_name="gate-widget-7f2qd"),
            '{"spec":{"suspend":false},"status":{}}',
        ),
        (
            terminal_watch_argv(
                namespace="gates", job_name="gate-widget-7f2qd", remaining_seconds=999.0
            ),
            '{"status":{"conditions":[{"type":"Complete","status":"True"}]}}',
        ),
    ],
)
def test_completed_wait_commands_do_not_depend_on_signal_delivery_to_stop_their_heartbeat(
    *,
    argv: list[str],
    kubectl_output: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A lost or ignored TERM must not keep a finished wait command alive.

    A shell heartbeat stopped by `kill` + `wait` can lose the TERM while it sits
    in `wait`, and a TERM ignored on entry cannot be trapped at all. The command
    then blocks on its heartbeat for the whole sleep, or forever.
    """
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()
    wrapper = stub_dir / "with-gates-kubeconfig"
    _ = wrapper.write_text('#!/bin/sh\nexec "$@"\n', encoding="utf-8")
    wrapper.chmod(0o755)
    kubectl = stub_dir / "kubectl"
    _ = kubectl.write_text(
        f"#!/bin/sh\nprintf '%s\\n' '{kubectl_output}'\n",
        encoding="utf-8",
    )
    kubectl.chmod(0o755)
    monkeypatch.setenv("PATH", f"{stub_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("LIVESPEC_GATE_RUN_PROGRESS_STAMP", str(tmp_path / "stamp"))

    previous = signal.signal(signal.SIGTERM, signal.SIG_IGN)
    try:
        process = subprocess.Popen(
            argv,
            cwd=tmp_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
    finally:
        _ = signal.signal(signal.SIGTERM, previous)
    try:
        _ = process.communicate(timeout=10.0)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        _ = process.communicate()
        pytest.fail("the wait command was still blocked on its heartbeat after its Job answered")
    assert process.returncode == 0


def test_terminal_wait_stops_when_its_deadline_elapses_between_watch_windows() -> None:
    """A watch re-arm cannot spend past the terminal-state wait deadline."""
    request = GateRunRequest(
        repo_root=Path("/repo"),
        mirror_url="ssh://mirror/repo.git",
        manifest="apiVersion: batch/v1\nkind: Job\n",
        gate_ref="refs/gates/tree-run",
        poll_timeout_seconds=20.0,
    )
    active = json.dumps({"spec": {"suspend": False}, "status": {}})
    clocks = iter((0.0, 0.0, 10.0, 10.0, 20.0))

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
        clock=lambda: next(clocks),
    )

    assert isinstance(outcome, Failure)
    assert outcome.failure().detail.endswith("reached no terminal condition within 20s")
