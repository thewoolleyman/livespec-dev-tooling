"""A check runner killed by SIGTERM or SIGHUP leaves no coverage directory behind.

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
