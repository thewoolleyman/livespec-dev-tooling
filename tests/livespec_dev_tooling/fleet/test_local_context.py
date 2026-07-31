"""Tests for `livespec_dev_tooling/fleet/_local_context.py`.

`CommandResult` is the value type local rows exchange; `LocalContext`
carries the target checkout + the command seam; `default_command_runner`
is the real subprocess seam (a missing program lands on the FAILURE
track rather than answering with a fabricated exit code). The runner is
exercised across its missing-program (real `shutil.which`), default-cwd,
and explicit-cwd branches; the latter two patch `subprocess.run` rather
than spawning a child (no `--cov` self-instrumentation race).
`LocalContext.exec` is checked to forward the checkout as the working
directory.

⚠️ `test_default_runner_missing_program_...` was CORRECTED, not updated.
It read `assert result.returncode == 127` and was NAMED
`..._is_synthetic_127`, so the fabricated sentinel was written into the
suite as expected behavior — in the name as well as the assertion — and
the honest conversion read as a regression against it. A test name is a
claim like any other. See `test_local_command_invocation_railway.py`.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from returns.io import IOFailure, IOSuccess
from returns.unsafe import unsafe_perform_io

from livespec_dev_tooling.fleet._invocation_failure import BINARY_ABSENT
from livespec_dev_tooling.fleet._local_context import (
    CommandOutcome,
    CommandResult,
    LocalContext,
    default_command_runner,
)

if TYPE_CHECKING:
    import pytest

__all__: list[str] = []


def test_command_result_carries_returncode_and_streams() -> None:
    result = CommandResult(returncode=2, stdout="out", stderr="err")
    assert result.returncode == 2
    assert result.stdout == "out"
    assert result.stderr == "err"


def test_default_runner_missing_program_is_a_failure_value() -> None:
    """A binary genuinely absent from the REAL PATH, not a patched `which`."""
    result = default_command_runner(args=["livespec-not-a-real-binary-xyz"])
    assert isinstance(result, IOFailure)
    failure = unsafe_perform_io(result.failure())
    assert failure.kind == BINARY_ABSENT
    assert "not on PATH" in failure.detail


def test_default_runner_maps_subprocess_result_with_default_cwd(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, object] = {}

    def fake_run(cmd, *, capture_output, text, check, cwd):
        del capture_output, text, check
        captured["cmd"] = cmd
        captured["cwd"] = cwd
        return subprocess.CompletedProcess(args=cmd, returncode=3, stdout="hi", stderr="boom")

    monkeypatch.setattr(shutil, "which", lambda program: f"/usr/bin/{program}")
    monkeypatch.setattr(subprocess, "run", fake_run)
    result = default_command_runner(args=["sometool", "-x"])
    assert isinstance(result, IOSuccess)
    answer = unsafe_perform_io(result.unwrap())
    assert answer.returncode == 3
    assert answer.stdout == "hi"
    assert answer.stderr == "boom"
    assert captured["cmd"] == ["sometool", "-x"]
    assert captured["cwd"] is None


def test_default_runner_forwards_explicit_cwd_as_string(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, object] = {}

    def fake_run(cmd, *, capture_output, text, check, cwd):
        del capture_output, text, check
        captured["cwd"] = cwd
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(shutil, "which", lambda program: f"/usr/bin/{program}")
    monkeypatch.setattr(subprocess, "run", fake_run)
    result = default_command_runner(args=["sometool"], cwd=tmp_path)
    assert unsafe_perform_io(result.unwrap()).returncode == 0
    assert captured["cwd"] == str(tmp_path)


def test_exec_forwards_checkout_as_cwd(*, tmp_path: Path) -> None:
    seen: dict[str, object] = {}

    def runner(*, args: list[str], cwd: Path | None = None) -> CommandOutcome:
        seen["args"] = args
        seen["cwd"] = cwd
        return IOSuccess(CommandResult(returncode=0, stdout="", stderr=""))

    ctx = LocalContext(checkout=tmp_path, home=tmp_path / "home", run=runner)
    outcome = ctx.exec(args=["git", "status"])
    assert unsafe_perform_io(outcome.unwrap()).returncode == 0
    assert seen["args"] == ["git", "status"]
    assert seen["cwd"] == tmp_path
