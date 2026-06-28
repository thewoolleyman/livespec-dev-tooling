"""Tests for `livespec_dev_tooling/fleet/_local_context.py`.

`CommandResult` is the value type local rows exchange; `LocalContext`
carries the target checkout + the command seam; `default_command_runner`
is the real subprocess seam (a missing program degrades to a synthetic
exit-127 result rather than raising). The runner is exercised across its
missing-program (real `shutil.which` → synthetic 127), default-cwd, and
explicit-cwd branches; the latter two patch `subprocess.run` rather than
spawning a child (no `--cov` self-instrumentation race). `LocalContext.exec`
is checked to forward the checkout as the working directory.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from livespec_dev_tooling.fleet._local_context import (
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


def test_default_runner_missing_program_is_synthetic_127() -> None:
    result = default_command_runner(args=["livespec-not-a-real-binary-xyz"])
    assert result.returncode == 127
    assert "not on PATH" in result.stderr


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
    assert result.returncode == 3
    assert result.stdout == "hi"
    assert result.stderr == "boom"
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
    assert result.returncode == 0
    assert captured["cwd"] == str(tmp_path)


def test_exec_forwards_checkout_as_cwd(*, tmp_path: Path) -> None:
    seen: dict[str, object] = {}

    def runner(*, args: list[str], cwd: Path | None = None) -> CommandResult:
        seen["args"] = args
        seen["cwd"] = cwd
        return CommandResult(returncode=0, stdout="", stderr="")

    ctx = LocalContext(checkout=tmp_path, home=tmp_path / "home", run=runner)
    outcome = ctx.exec(args=["git", "status"])
    assert outcome.returncode == 0
    assert seen["args"] == ["git", "status"]
    assert seen["cwd"] == tmp_path
