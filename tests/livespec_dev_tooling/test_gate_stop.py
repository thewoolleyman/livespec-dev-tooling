"""Acceptance scenarios for stopping a detached gate by its durable run id."""

from __future__ import annotations

import argparse
import importlib
import os
import signal
import subprocess
import time
from contextlib import suppress
from pathlib import Path
from types import ModuleType

import pytest
from _pytest.monkeypatch import MonkeyPatch
from returns.result import Success

from livespec_dev_tooling.install_worktree_pack import CANONICAL_GATE_RUN_BODY

__all__: list[str] = []


def _gate_stop() -> ModuleType:
    """Import the stop implementation only after a genuine Red assertion."""
    module_path = Path(__file__).parents[2] / "livespec_dev_tooling" / "gate_stop.py"
    assert module_path.is_file(), module_path
    return importlib.import_module("livespec_dev_tooling.gate_stop")


def _write_runner(*, root: Path) -> Path:
    """Create a minimal repository with the canonical detached runner installed."""
    _ = subprocess.run(
        ["git", "init", "--quiet", "--initial-branch=master"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    script = root / "dev-tooling" / "gate-run.sh"
    script.parent.mkdir()
    _ = script.write_text(CANONICAL_GATE_RUN_BODY, encoding="utf-8")
    script.chmod(0o755)
    return script


def _run(*, script: Path, root: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    """Invoke one runner verb with the source package available to its child."""
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(Path(__file__).parents[2])
    return subprocess.run(
        ["bash", str(script), *args],
        cwd=root,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )


def _await(*, path: Path) -> None:
    """Wait only long enough for the detached child to publish its pid."""
    deadline = time.monotonic() + 10
    while not path.is_file() and time.monotonic() < deadline:
        time.sleep(0.05)
    assert path.is_file(), path


def test_gate_stop_marks_a_running_run_before_ending_its_process(*, tmp_path: Path) -> None:
    """A stopped running gate is terminal, non-successful, and cannot later pass."""
    root = tmp_path / "repo"
    root.mkdir()
    script = _write_runner(root=root)
    started = _run(
        script=script,
        root=root,
        args=[
            "start",
            "--local",
            "--",
            "bash",
            "-c",
            "trap 'exit 0' TERM; while :; do sleep 1; done",
        ],
    )
    assert started.returncode == 0, started.stderr
    run_id = started.stdout.strip()
    run_dir = root / "tmp" / "gate-runs" / run_id
    _await(path=run_dir / "pid")

    try:
        stopped = _run(script=script, root=root, args=["stop", run_id])

        assert stopped.returncode == 0, stopped.stderr
        marker = (run_dir / "stopped").read_text(encoding="utf-8")
        assert "stopped_at=" in marker
        assert "requested_by=" in marker
        for verb in (["status", run_id], ["wait", run_id], ["list", "--all"]):
            result = _run(script=script, root=root, args=verb)
            assert result.returncode == (75 if verb[0] != "list" else 0)
            assert "STOPPED" in result.stdout
            assert "Re-run the gate" not in result.stdout
    finally:
        pid = (run_dir / "pid").read_text(encoding="utf-8").strip()
        if pid.isdigit():
            with suppress(ProcessLookupError):
                os.kill(int(pid), signal.SIGKILL)


def test_gate_stop_refuses_unknown_and_completed_run_ids(*, tmp_path: Path) -> None:
    """Stopping an unknown or completed run cannot add a stop marker."""
    root = tmp_path / "repo"
    root.mkdir()
    script = _write_runner(root=root)

    unknown = _run(script=script, root=root, args=["stop", "not-a-run"])
    assert unknown.returncode == 64

    run_dir = root / "tmp" / "gate-runs" / "finished"
    run_dir.mkdir(parents=True)
    _ = (run_dir / "exit_code").write_text("0\n", encoding="utf-8")
    completed = _run(script=script, root=root, args=["stop", "finished"])
    assert completed.returncode == 1
    assert "PASSED" in completed.stdout
    assert not (run_dir / "stopped").exists()


def test_gate_stop_only_confirms_a_recorded_job_is_gone(
    *, capsys: pytest.CaptureFixture[str], monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    """Stopping signals the client; it must not delete the client's Job itself."""
    gate_stop = _gate_stop()
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _ = (run_dir / "job_name").write_text("gate-job\n", encoding="utf-8")
    _ = (run_dir / "pid").write_text("123\n", encoding="utf-8")
    calls: list[list[str]] = []

    def runner(*, argv: list[str], cwd: Path) -> Success[subprocess.CompletedProcess[str]]:
        _ = cwd
        calls.append(argv)
        return Success(subprocess.CompletedProcess(argv, 0, "", ""))

    monkeypatch.setattr(gate_stop, "default_gate_command_runner", runner)
    monkeypatch.setattr(gate_stop, "_args", lambda: argparse.Namespace(run_dir=run_dir))
    monkeypatch.setattr(gate_stop, "_stop", lambda *, root: {root} - {root})

    assert gate_stop.main() == 1
    assert (run_dir / "stopped").is_file()
    assert "surviving Job gate-job" in capsys.readouterr().out
    assert len(calls) == 1
    assert calls[0][-5:] == ["--namespace", "gates", "get", "job", "gate-job"]
