"""The delegated gate client's host-invocation seam — R4.S7a.

Every test here is hermetic: `shutil.which` and `subprocess.run` are
monkeypatched, so no program is ever spawned and no host is touched.

THE ASYMMETRY THESE TESTS PIN is the whole reason the seam has two tracks. A
command that RAN is a success carrying its exit code as data, whatever that code
is; a command that never ran is a failure. Collapsing either direction — reading
every non-zero exit as a failure, or answering an absent binary with a
fabricated exit code — puts a value on the wrong track, and a caller then reads
it as an answer.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from returns.pipeline import is_successful
from returns.result import Failure, Success

from livespec_dev_tooling.gate_remote_invocation import (
    GateCommandNotRun,
    GateCommandResult,
    default_gate_command_runner,
    default_sleeper,
    require_invocation,
    require_success,
)

__all__: list[str] = []

_ARGV = ["kubectl", "get", "job"]


def _no_program(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every program unresolvable REGARDLESS of the host's real PATH.

    Patching `shutil.which` rather than shadowing PATH: a shim directory only
    works if it is the WHOLE path, and a fixture a real binary can defeat is a
    fixture that cannot fail.
    """

    def _absent(_name: str) -> str | None:
        return None

    monkeypatch.setattr(shutil, "which", _absent)


def _program_at(monkeypatch: pytest.MonkeyPatch, *, path: str = "/usr/bin/kubectl") -> None:
    def _resolved(_name: str) -> str | None:
        return path

    monkeypatch.setattr(shutil, "which", _resolved)


def test_an_absent_binary_is_a_failure_value_rather_than_a_fabricated_exit_code(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A command that never ran and one that ran and exited non-zero differ."""
    _no_program(monkeypatch)
    outcome = default_gate_command_runner(argv=_ARGV, cwd=Path("/repo"))
    assert isinstance(outcome, Failure)
    failure = outcome.failure()
    assert isinstance(failure, GateCommandNotRun)
    assert failure.argv == ("kubectl", "get", "job")
    assert "not on PATH" in failure.detail


def test_a_program_that_cannot_be_spawned_is_a_failure_value_rather_than_a_raise(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An `OSError` out of the seam would abort a gate run mid-flight."""
    _program_at(monkeypatch)

    def _explode(_argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(subprocess, "run", _explode)
    outcome = default_gate_command_runner(argv=_ARGV, cwd=Path("/repo"))
    assert isinstance(outcome, Failure)
    assert "Permission denied" in outcome.failure().detail


def test_a_captured_invocation_carries_its_exit_code_and_both_streams(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A non-zero exit is an ANSWER at this layer, not a failure."""
    _program_at(monkeypatch)
    seen: dict[str, object] = {}

    def _fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        seen.update(kwargs)
        seen["argv"] = argv
        return subprocess.CompletedProcess(args=argv, returncode=3, stdout="out", stderr="err")

    monkeypatch.setattr(subprocess, "run", _fake_run)
    outcome = default_gate_command_runner(argv=_ARGV, cwd=Path("/repo"), stdin="manifest")
    assert outcome == Success(GateCommandResult(returncode=3, stdout="out", stderr="err"))
    assert seen["capture_output"] is True
    assert seen["input"] == "manifest"
    assert seen["cwd"] == "/repo"


def test_a_streaming_invocation_captures_nothing_so_the_child_owns_the_terminal(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`stream=True` must NOT capture: capturing is exactly what would swallow the log.

    A captured child writes into this process instead of the operator's
    terminal, so the one property the log step exists for would be silently
    absent while every assertion about "the command ran" still passed.
    """
    _program_at(monkeypatch)
    seen: dict[str, object] = {}

    def _fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        seen.update(kwargs)
        return subprocess.CompletedProcess(args=argv, returncode=0, stdout=None, stderr=None)

    monkeypatch.setattr(subprocess, "run", _fake_run)
    outcome = default_gate_command_runner(argv=_ARGV, cwd=Path("/repo"), stream=True)
    assert seen["capture_output"] is False
    assert outcome == Success(GateCommandResult(returncode=0, stdout="", stderr=""))


def test_the_default_sleeper_sleeps_for_the_interval_it_is_given(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The production `Sleeper`; the poll loop's only source of real time."""
    naps: list[float] = []
    monkeypatch.setattr("livespec_dev_tooling.gate_remote_invocation.time.sleep", naps.append)
    default_sleeper(seconds=1.5)
    assert naps == [1.5]


def test_require_invocation_passes_a_non_zero_exit_straight_through() -> None:
    """The lenient lifter: the caller wants the number, not a verdict on it."""
    ran = Success(GateCommandResult(returncode=7, stdout="", stderr=""))
    lifted = require_invocation(step="stream-gate-logs", argv=_ARGV, outcome=ran)
    assert is_successful(lifted)
    assert lifted.unwrap().returncode == 7


def test_require_invocation_stamps_the_step_on_a_command_that_never_ran() -> None:
    """`returncode=None` is what says "there was no exit code at all"."""
    never = Failure(GateCommandNotRun(argv=("kubectl",), detail="kubectl not on PATH"))
    lifted = require_invocation(step="stream-gate-logs", argv=_ARGV, outcome=never)
    assert isinstance(lifted, Failure)
    failure = lifted.failure()
    assert failure.step == "stream-gate-logs"
    assert failure.argv == ("kubectl", "get", "job")
    assert failure.returncode is None


def test_require_success_accepts_a_zero_exit() -> None:
    ran = Success(GateCommandResult(returncode=0, stdout="ok", stderr=""))
    lifted = require_success(step="push-gate-ref", argv=_ARGV, outcome=ran)
    assert is_successful(lifted)
    assert lifted.unwrap().stdout == "ok"


def test_require_success_turns_a_non_zero_exit_into_the_step_failing() -> None:
    """The strict lifter carries the real code and the program's own stderr."""
    ran = Success(GateCommandResult(returncode=128, stdout="", stderr="remote rejected\n"))
    lifted = require_success(step="push-gate-ref", argv=_ARGV, outcome=ran)
    assert isinstance(lifted, Failure)
    failure = lifted.failure()
    assert failure.step == "push-gate-ref"
    assert failure.returncode == 128
    assert failure.detail == "remote rejected\n"


def test_require_success_reports_a_command_that_never_ran_without_inventing_a_code() -> None:
    never = Failure(GateCommandNotRun(argv=("git",), detail="git not on PATH"))
    lifted = require_success(step="push-gate-ref", argv=_ARGV, outcome=never)
    assert isinstance(lifted, Failure)
    assert lifted.failure().returncode is None
