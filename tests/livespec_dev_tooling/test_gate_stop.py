"""Acceptance scenarios for stopping a detached gate by its durable run id."""

from __future__ import annotations

import argparse
import importlib
import os
import signal
import subprocess
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
    assert (run_dir / "pid").is_file()

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
        with suppress(ProcessLookupError, ValueError):
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

    _ = (run_dir / "exit_code").write_text("128\n", encoding="utf-8")
    interrupted = _run(script=script, root=root, args=["stop", "finished"])
    assert interrupted.returncode == 1
    assert "DIED_WITHOUT_VERDICT" in interrupted.stdout


def test_gate_runner_usage_names_gate_stop_as_the_supported_cancellation_path(
    *, tmp_path: Path
) -> None:
    """Operators are told not to signal a run and are given the stop command."""
    root = tmp_path / "repo"
    root.mkdir()
    script = _write_runner(root=root)

    usage = _run(script=script, root=root, args=[])

    assert usage.returncode == 64
    assert "signalling its pid or process group is not" in usage.stderr
    assert "gate-stop" in usage.stderr


def test_gate_stop_marks_a_live_run_even_when_its_pid_is_unavailable(
    *, capsys: pytest.CaptureFixture[str], monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    """A stop marker wins the race with a child that has not published its pid."""
    gate_stop = _gate_stop()
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    monkeypatch.setattr(gate_stop, "_args", lambda: argparse.Namespace(run_dir=run_dir))

    assert gate_stop.main() == 1
    assert (run_dir / "stopped").is_file()
    assert "has no live pid" in capsys.readouterr().out


def test_gate_stop_reports_a_completed_failed_run(
    *, capsys: pytest.CaptureFixture[str], monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    """A completed non-zero gate reads as FAILED without a stop marker."""
    gate_stop = _gate_stop()
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _ = (run_dir / "exit_code").write_text("7\n", encoding="utf-8")
    monkeypatch.setattr(gate_stop, "_args", lambda: argparse.Namespace(run_dir=run_dir))

    assert gate_stop.main() == 1
    assert "FAILED" in capsys.readouterr().out


def test_gate_stop_handles_an_unreadable_process_environment(
    *, monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    """An unreadable process environment does not make stopping another run fail."""
    gate_stop = _gate_stop()
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _ = (run_dir / "pid").write_text("123\n", encoding="utf-8")
    monkeypatch.setattr(gate_stop, "_args", lambda: argparse.Namespace(run_dir=run_dir))

    def stopped(*, root: int) -> set[int]:
        _ = root
        return set()

    monkeypatch.setattr(gate_stop, "_stop", stopped)

    class UnreadableEnvironment:
        """A proc entry whose environment cannot be inspected."""

        def read_bytes(self) -> bytes:
            raise OSError

    class ProcessEntry:
        """One numeric process directory in the fake procfs."""

        name = "123"

        def __truediv__(self, name: str) -> UnreadableEnvironment:
            assert name == "environ"
            return UnreadableEnvironment()

    class ProcRoot:
        """Only the procfs operation the marked-process scan requires."""

        def iterdir(self) -> list[ProcessEntry]:
            return [ProcessEntry()]

    path = gate_stop.Path
    monkeypatch.setattr(
        gate_stop, "Path", lambda value: ProcRoot() if value == "/proc" else path(value)
    )

    assert gate_stop.main() == 0


def test_gate_stop_follows_every_descendant_before_signalling(
    *, monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    """A stop sees the child that a detached gate process forked."""
    gate_stop = _gate_stop()
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _ = (run_dir / "pid").write_text("123\n", encoding="utf-8")
    monkeypatch.setattr(gate_stop, "_args", lambda: argparse.Namespace(run_dir=run_dir))
    signalled: list[int] = []

    def settled(*, pids: set[int]) -> set[int]:
        _ = pids
        return set()

    monkeypatch.setattr(gate_stop, "_settle", settled)
    monkeypatch.setattr(gate_stop.os, "kill", lambda pid, _signal: signalled.append(pid))

    class Readable:
        """A tiny process-status file with a single parent relationship."""

        def __init__(self, *, text: str = "", data: bytes = b"") -> None:
            self.text = text
            self.data = data

        def read_bytes(self) -> bytes:
            return self.data

        def read_text(self, *, encoding: str) -> str:
            _ = encoding
            return self.text

    class Unreadable:
        """A procfs status file that disappears during the scan."""

        def read_text(self, *, encoding: str) -> str:
            _ = encoding
            raise OSError

    class ProcessEntry:
        """A procfs entry that can be a gate root or its descendant."""

        def __init__(
            self,
            *,
            name: str,
            status: Readable | Unreadable,
            marked: bool = False,
        ) -> None:
            self.name = name
            self.status = status
            self.marked = marked

        def __truediv__(self, name: str) -> Readable | Unreadable:
            marker = f"LIVESPEC_GATE_RUN_DIR={run_dir}".encode() if self.marked else b""
            return {"status": self.status, "environ": Readable(data=marker)}[name]

    class ProcRoot:
        """The minimal procfs surface used for tree and marker discovery."""

        def iterdir(self) -> list[ProcessEntry]:
            return [
                ProcessEntry(name="123", status=Readable(text="PPid:\t1\n"), marked=True),
                ProcessEntry(name="456", status=Readable(text="PPid:\t123\n")),
                ProcessEntry(name="999", status=Readable(text="PPid:\tnot-a-pid\n")),
                ProcessEntry(name="1000", status=Unreadable()),
            ]

    path = gate_stop.Path
    monkeypatch.setattr(
        gate_stop, "Path", lambda value: ProcRoot() if value == "/proc" else path(value)
    )

    assert gate_stop.main() == 0
    assert signalled == [123, 456]


def test_gate_stop_terms_every_attributed_process_before_any_kill(
    *, monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    """The separately-sessioned hook client gets the client's cleanup chance first."""
    gate_stop = _gate_stop()
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _ = (run_dir / "pid").write_text("123\n", encoding="utf-8")
    monkeypatch.setattr(gate_stop, "_args", lambda: argparse.Namespace(run_dir=run_dir))
    monkeypatch.setattr(gate_stop, "_tree", lambda *, root: {root})
    monkeypatch.setattr(
        gate_stop, "_marked_processes", lambda *, run_dir: {456} if run_dir.is_dir() else set()
    )
    monkeypatch.setattr(gate_stop, "_job_gone", lambda *, run_dir: run_dir.is_dir())
    signals: list[tuple[int, set[int]]] = []
    monkeypatch.setattr(
        gate_stop,
        "_signal",
        lambda *, pids, signal_number: signals.append((signal_number, set(pids))),
    )
    monkeypatch.setattr(gate_stop, "_settle", lambda *, pids: set(pids))

    assert gate_stop.main() == 1
    assert signals == [
        (signal.SIGTERM, {123, 456}),
        (signal.SIGKILL, {123, 456}),
    ]


def test_gate_stop_tolerates_a_process_that_disappears_during_signalling(
    *, monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    """A vanished process is not reported as a surviving process."""
    gate_stop = _gate_stop()
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _ = (run_dir / "pid").write_text("123\n", encoding="utf-8")
    monkeypatch.setattr(gate_stop, "_args", lambda: argparse.Namespace(run_dir=run_dir))
    monkeypatch.setattr(gate_stop, "_tree", lambda *, root: {root})
    monkeypatch.setattr(
        gate_stop.os, "kill", lambda *_args: (_ for _ in ()).throw(ProcessLookupError)
    )

    assert gate_stop.main() == 0


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


def test_gate_stop_names_surviving_processes(
    *, capsys: pytest.CaptureFixture[str], monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    """A stop reports each local survivor instead of claiming it ended the run."""
    gate_stop = _gate_stop()
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _ = (run_dir / "pid").write_text("123\n", encoding="utf-8")
    monkeypatch.setattr(gate_stop, "_args", lambda: argparse.Namespace(run_dir=run_dir))
    monkeypatch.setattr(gate_stop, "_stop", lambda *, root: {root})

    def no_marked_processes(*, run_dir: Path) -> set[int]:
        _ = run_dir
        return set()

    monkeypatch.setattr(gate_stop, "_stop_marked", no_marked_processes)

    assert gate_stop.main() == 1
    assert "surviving processes: [123]" in capsys.readouterr().out
