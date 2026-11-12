"""Coverage namespace cleanup survives signals and reclaims SIGKILL leaks.

Work-item livespec-dev-tooling-8o8e.16. `isolated_environments` removes its
`covns-*` directories in a `finally`, but Python's default action for SIGTERM
and SIGHUP ends the process without unwinding, so every gate-runner stall kill,
lefthook hook hangup and harness kill leaked one directory per namespace. Only a
real runner process shows that, so each test starts one (allowlisted in
`subprocess_spawn_allowlist`; the child's coverage startup is scrubbed), points
its TMPDIR at an empty directory, waits until a coverage-touching target is
running, signals the runner and lists that directory.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from contextlib import suppress
from pathlib import Path

import pytest

import livespec_dev_tooling._dispatcher_coverage_namespaces as namespaces

__all__: list[str] = []
pytestmark = pytest.mark.integration

_ROOT = Path(__file__).resolve().parents[2]

# A fake `just` that records it is running, then holds the target open.
_FAKE_JUST = """#!/bin/sh
touch "$RUNNING_MARKER"
case "${FAKE_JUST_ACTION:-sleep}" in
    sleep) exec sleep 120 ;;
    pass) exit 0 ;;
esac
"""

_LOCAL_GATES = """
import sys
from pathlib import Path
from livespec_dev_tooling.incident_local_gates import GateSelection, GateSpec, execute_plan
gate = GateSpec(name="check-coverage", command=("just", "check-coverage"), classification="fast")
execute_plan(
    plan=(GateSelection(gate=gate, selected=True, reason="selected"),),
    cwd=Path(sys.argv[1]),
)
"""

_CI_ENTRY = """
import os
import sys
from pathlib import Path
from livespec_dev_tooling.incident_ci_entry import CiEntry
from livespec_dev_tooling.incident_ci_policy import CiEvent, CiTarget
entry = CiEntry(
    repo=Path(sys.argv[1]),
    targets=(CiTarget(name="check-coverage", classification="fast"),),
)
event = CiEvent(kind="push", repository="owner/repo", base_sha="a" * 40, head_sha="b" * 40)
environ = dict(os.environ)
plan = entry.plan(event=event, payload="not-json", environ=environ)
assert plan is not None
entry.execute(
    plan=plan,
    names=("check-coverage",),
    report=Path(sys.argv[1]) / "report.jsonl",
    payload="not-json",
    environ=environ,
)
"""

_RUNNERS: dict[str, list[str]] = {
    "dispatcher": [
        "-m",
        "livespec_dev_tooling.parallel_check_dispatcher",
        "check-coverage",
    ],
    "local-gates": ["-c", _LOCAL_GATES],
    "ci-entry": ["-c", _CI_ENTRY],
}


def _runner_environment(
    *, bin_dir: Path, scratch: Path, marker: Path, action: str = "sleep"
) -> dict[str, str]:
    environment = {
        key: value
        for key, value in os.environ.items()
        if key != "COVERAGE_PROCESS_START" and not key.startswith("COV_CORE_")
    }
    environment["PATH"] = f"{bin_dir}{os.pathsep}{environment['PATH']}"
    environment["PYTHONPATH"] = str(_ROOT)
    environment["TMPDIR"] = str(scratch)
    environment["RUNNING_MARKER"] = str(marker)
    environment["FAKE_JUST_ACTION"] = action
    environment["LIVESPEC_PYRIGHT_WARMED"] = "1"
    return environment


def _start_runner(
    *, work: Path, bin_dir: Path, scratch: Path, marker: Path, action: str
) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        [sys.executable, *_RUNNERS["dispatcher"]],
        cwd=work,
        env=_runner_environment(
            bin_dir=bin_dir,
            scratch=scratch,
            marker=marker,
            action=action,
        ),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def _wait_for_marker(*, marker: Path) -> None:
    started = time.monotonic()
    while not marker.exists() and time.monotonic() - started < 30:
        time.sleep(0.05)
    assert marker.exists(), "the coverage target never started"


def _runner_workspace(*, tmp_path: Path) -> tuple[Path, Path, Path]:
    work = tmp_path / "work"
    scratch = tmp_path / "scratch"
    bin_dir = tmp_path / "bin"
    for directory in (work, scratch, bin_dir):
        directory.mkdir()
    just = bin_dir / "just"
    _ = just.write_text(_FAKE_JUST)
    just.chmod(0o755)
    return work, scratch, bin_dir


def _creator_record(*, namespace_dir: Path) -> dict[str, object]:
    record = namespace_dir / ".livespec-coverage-creator.json"
    assert record.is_file(), "each coverage namespace must record its creator identity"
    loaded = json.loads(record.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _assert_creator_identity(*, namespace_dirs: list[Path], pid: int) -> None:
    assert len(namespace_dirs) == 1
    creator = _creator_record(namespace_dir=namespace_dirs[0])
    assert creator["pid"] == pid
    assert isinstance(creator["start_time"], str) and creator["start_time"]


def _write_creator_record(*, namespace_dir: Path, creator: object) -> None:
    _ = (namespace_dir / ".livespec-coverage-creator.json").write_text(
        json.dumps(creator), encoding="utf-8"
    )


def _signal_runner(*, tmp_path: Path, runner: str, signum: int) -> tuple[int, list[str], bool]:
    work = tmp_path / "work"
    scratch = tmp_path / "scratch"
    bin_dir = tmp_path / "bin"
    for directory in (work, scratch, bin_dir):
        directory.mkdir()
    just = bin_dir / "just"
    _ = just.write_text(_FAKE_JUST)
    just.chmod(0o755)
    marker = tmp_path / "running"
    argv = [*_RUNNERS[runner], str(work)] if _RUNNERS[runner][0] == "-c" else _RUNNERS[runner]
    process = subprocess.Popen(
        [sys.executable, *argv],
        cwd=work,
        env=_runner_environment(bin_dir=bin_dir, scratch=scratch, marker=marker),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        started = time.monotonic()
        while not marker.exists() and time.monotonic() - started < 60:
            time.sleep(0.05)
        process.send_signal(signum)
        status = process.wait(timeout=30)
    finally:
        # The held target sleeps in the runner's own session; reap the session.
        with suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
        _ = process.wait()
    return status, sorted(path.name for path in scratch.iterdir()), marker.exists()


@pytest.mark.parametrize("runner", sorted(_RUNNERS))
@pytest.mark.parametrize("signum", [signal.SIGTERM, signal.SIGHUP])
def test_a_signalled_check_runner_removes_its_coverage_directories_and_exits_non_zero(
    tmp_path: Path, runner: str, signum: int
) -> None:
    status, leftovers, was_running = _signal_runner(tmp_path=tmp_path, runner=runner, signum=signum)
    assert was_running
    assert status != 0
    assert leftovers == []


def test_a_new_runner_reclaims_a_sigkilled_runners_coverage_directory_but_leaves_a_live_runner_alone(
    tmp_path: Path,
) -> None:
    """A startup sweep reclaims a SIGKILL leak without disturbing a live aggregate."""
    work, scratch, bin_dir = _runner_workspace(tmp_path=tmp_path)

    killed_marker = tmp_path / "killed-running"
    killed = _start_runner(
        work=work, bin_dir=bin_dir, scratch=scratch, marker=killed_marker, action="sleep"
    )
    processes = [killed]
    try:
        _wait_for_marker(marker=killed_marker)
        initial_dirs = sorted(scratch.glob("covns-*"))
        _assert_creator_identity(namespace_dirs=initial_dirs, pid=killed.pid)
        killed.kill()
        assert killed.wait(timeout=30) != 0
        leaked = sorted(scratch.glob("covns-*"))
        assert len(leaked) == 1, "SIGKILL must leave the first runner's namespace behind"

        live_marker = tmp_path / "live-running"
        live = _start_runner(
            work=work, bin_dir=bin_dir, scratch=scratch, marker=live_marker, action="sleep"
        )
        processes.append(live)
        _wait_for_marker(marker=live_marker)
        live_dirs = sorted(scratch.glob("covns-*"))
        assert len(live_dirs) == 1, "the next runner must reclaim the SIGKILL leak on startup"

        reclaimer = _start_runner(
            work=work,
            bin_dir=bin_dir,
            scratch=scratch,
            marker=tmp_path / "reclaimer-running",
            action="pass",
        )
        assert reclaimer.wait(timeout=30) == 0
        assert sorted(scratch.glob("covns-*")) == live_dirs
        assert live.poll() is None, "the live aggregate's verdict must remain undisturbed"
    finally:
        for process in processes:
            with suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
            _ = process.wait()


def test_reclaim_removes_dead_and_old_unrecorded_namespaces_but_keeps_live_and_recent_ones(
    *, tmp_path: Path
) -> None:
    """A startup sweep preserves only a namespace a live process still owns."""
    assert hasattr(namespaces, "reclaim_abandoned_namespace_dirs")
    reclaim = namespaces.reclaim_abandoned_namespace_dirs
    start_time = namespaces.process_start_time(pid=os.getpid())
    assert start_time is not None
    directories = {
        name: tmp_path / f"covns-{name}" for name in ("dead", "live", "reused", "old", "recent")
    }
    for directory in directories.values():
        directory.mkdir()
    _write_creator_record(
        namespace_dir=directories["dead"], creator={"pid": 999_999_999, "start_time": "gone"}
    )
    _write_creator_record(
        namespace_dir=directories["live"], creator={"pid": os.getpid(), "start_time": start_time}
    )
    _write_creator_record(
        namespace_dir=directories["reused"], creator={"pid": os.getpid(), "start_time": "different"}
    )
    old_time = time.time() - 24 * 60 * 60 - 1
    os.utime(directories["old"], (old_time, old_time))

    reclaim(root=tmp_path)

    assert not directories["dead"].exists()
    assert directories["live"].is_dir()
    assert not directories["reused"].exists()
    assert not directories["old"].exists()
    assert directories["recent"].is_dir()


@pytest.mark.parametrize(
    ("creator", "unreadable"),
    [
        ("{", False),
        ([], False),
        ({"pid": "bad", "start_time": "value"}, False),
        ({"pid": 1, "start_time": 1}, False),
        ({"pid": 1, "start_time": "value"}, True),
    ],
)
def test_reclaim_handles_invalid_creator_records_using_the_unrecorded_directory_age(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, creator: object, unreadable: bool
) -> None:
    """Unreadable and malformed records are safe only after their directory is old."""
    assert hasattr(namespaces, "reclaim_abandoned_namespace_dirs")
    reclaim = namespaces.reclaim_abandoned_namespace_dirs
    namespace_dir = tmp_path / "covns-invalid"
    namespace_dir.mkdir()
    _write_creator_record(namespace_dir=namespace_dir, creator=creator)
    if unreadable:

        def refuse_read(path: Path, *, encoding: str) -> str:
            _ = (path, encoding)
            raise OSError("permission denied")

        monkeypatch.setattr(namespaces.Path, "read_text", refuse_read)

    reclaim(root=tmp_path)
    assert namespace_dir.is_dir()
    old_time = time.time() - 24 * 60 * 60 - 1
    os.utime(namespace_dir, (old_time, old_time))
    reclaim(root=tmp_path)
    assert not namespace_dir.exists()


def test_process_start_time_handles_a_vanished_pid_and_an_unparsable_stat_line(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A creator cannot be trusted when procfs cannot identify its process."""
    assert hasattr(namespaces, "process_start_time")
    assert namespaces.process_start_time(pid=999_999_999) is None

    def unreadable_stat(path: Path, *, encoding: str) -> str:
        _ = (path, encoding)
        return "not a proc stat record"

    monkeypatch.setattr(namespaces.Path, "read_text", unreadable_stat)
    assert namespaces.process_start_time(pid=os.getpid()) is None


def test_reclaim_logs_an_unremovable_dead_namespace_and_carries_on(
    *, tmp_path: Path, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed best-effort removal never prevents the next runner from starting."""
    assert hasattr(namespaces, "reclaim_abandoned_namespace_dirs")
    reclaim = namespaces.reclaim_abandoned_namespace_dirs
    namespace_dir = tmp_path / "covns-dead"
    namespace_dir.mkdir()
    _write_creator_record(
        namespace_dir=namespace_dir, creator={"pid": 999_999_999, "start_time": "gone"}
    )

    def refuse_remove(path: Path) -> None:
        assert path == namespace_dir
        raise OSError("permission denied")

    monkeypatch.setattr(namespaces.shutil, "rmtree", refuse_remove)
    reclaim(root=tmp_path)

    assert namespace_dir.is_dir()
    assert "could not remove abandoned coverage namespace" in caplog.text
