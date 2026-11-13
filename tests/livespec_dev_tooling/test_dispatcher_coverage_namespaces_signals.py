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


def _start_dispatcher(
    *, work: Path, bin_dir: Path, scratch: Path, marker: Path, action: str
) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        [sys.executable, *_RUNNERS["dispatcher"]],
        cwd=work,
        env=_runner_environment(bin_dir=bin_dir, scratch=scratch, marker=marker, action=action),
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


def _dispatcher_workspace(*, tmp_path: Path) -> tuple[Path, Path, Path]:
    work = tmp_path / "work"
    scratch = tmp_path / "scratch"
    bin_dir = tmp_path / "bin"
    for directory in (work, scratch, bin_dir):
        directory.mkdir()
    just = bin_dir / "just"
    _ = just.write_text(_FAKE_JUST)
    just.chmod(0o755)
    return work, scratch, bin_dir


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


def test_a_new_runner_reclaims_a_sigkilled_namespace_but_leaves_a_live_aggregate_alone(
    *, tmp_path: Path
) -> None:
    """A startup sweep reclaims a SIGKILL leak without changing a live verdict."""
    work, scratch, bin_dir = _dispatcher_workspace(tmp_path=tmp_path)
    killed = _start_dispatcher(
        work=work,
        bin_dir=bin_dir,
        scratch=scratch,
        marker=tmp_path / "killed-running",
        action="sleep",
    )
    processes = [killed]
    try:
        _wait_for_marker(marker=tmp_path / "killed-running")
        killed.kill()
        assert killed.wait(timeout=30) != 0
        assert len(list(scratch.glob("covns-*"))) == 1

        live = _start_dispatcher(
            work=work,
            bin_dir=bin_dir,
            scratch=scratch,
            marker=tmp_path / "live-running",
            action="sleep",
        )
        processes.append(live)
        _wait_for_marker(marker=tmp_path / "live-running")
        live_dirs = sorted(scratch.glob("covns-*"))
        assert len(live_dirs) == 1

        reclaimer = _start_dispatcher(
            work=work,
            bin_dir=bin_dir,
            scratch=scratch,
            marker=tmp_path / "reclaimer-running",
            action="pass",
        )
        assert reclaimer.wait(timeout=30) == 0
        assert sorted(scratch.glob("covns-*")) == live_dirs
        assert live.poll() is None
    finally:
        for process in processes:
            with suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
            _ = process.wait()


def test_reclaim_removes_only_dead_or_old_unrecorded_namespaces(*, tmp_path: Path) -> None:
    """A valid dead record and an old absent record are the only reclaimable states."""
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
        namespace_dir=directories["reused"],
        creator={"pid": os.getpid(), "start_time": "different"},
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
    "creator",
    [
        "{",
        [],
        {"pid": 0, "start_time": "invalid"},
        {"pid": "bad", "start_time": "invalid"},
        {"pid": 1, "start_time": ""},
    ],
)
def test_reclaim_keeps_an_old_namespace_with_a_malformed_creator_record(
    *, tmp_path: Path, creator: object, caplog: pytest.LogCaptureFixture
) -> None:
    """Malformed records are not absent records, even after the 24-hour grace period."""
    namespace_dir = tmp_path / "covns-malformed"
    namespace_dir.mkdir()
    _write_creator_record(namespace_dir=namespace_dir, creator=creator)
    old_time = time.time() - 24 * 60 * 60 - 1
    os.utime(namespace_dir, (old_time, old_time))

    namespaces.reclaim_abandoned_namespace_dirs(root=tmp_path)

    assert namespace_dir.is_dir()
    assert "malformed creator record" in caplog.text


def test_reclaim_keeps_and_logs_an_old_namespace_with_an_unreadable_creator_record(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """An unreadable record leaves ownership unknown rather than making it stale."""
    namespace_dir = tmp_path / "covns-unreadable"
    namespace_dir.mkdir()
    _write_creator_record(namespace_dir=namespace_dir, creator={"pid": 1, "start_time": "value"})
    old_time = time.time() - 24 * 60 * 60 - 1
    os.utime(namespace_dir, (old_time, old_time))
    original_read_text = namespaces.Path.read_text

    def refuse_record(path: Path, *, encoding: str) -> str:
        if path.name == ".livespec-coverage-creator.json":
            raise PermissionError(path)
        return original_read_text(path, encoding=encoding)

    monkeypatch.setattr(namespaces.Path, "read_text", refuse_record)
    namespaces.reclaim_abandoned_namespace_dirs(root=tmp_path)

    assert namespace_dir.is_dir()
    assert "could not read creator record" in caplog.text


@pytest.mark.parametrize("failure", ["permission", "unparsable"])
def test_reclaim_keeps_and_logs_a_namespace_when_creator_state_cannot_be_observed(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    failure: str,
) -> None:
    """Only an absent or positively different process can prove a creator is gone."""
    namespace_dir = tmp_path / "covns-unobservable"
    namespace_dir.mkdir()
    _write_creator_record(
        namespace_dir=namespace_dir, creator={"pid": os.getpid(), "start_time": "recorded"}
    )
    original_read_text = namespaces.Path.read_text

    def read_text(path: Path, *, encoding: str) -> str:
        if str(path).startswith("/proc/"):
            if failure == "permission":
                raise PermissionError(path)
            return "not a proc stat record"
        return original_read_text(path, encoding=encoding)

    monkeypatch.setattr(namespaces.Path, "read_text", read_text)
    namespaces.reclaim_abandoned_namespace_dirs(root=tmp_path)

    assert namespace_dir.is_dir()
    assert "could not observe coverage creator" in caplog.text


def test_reclaim_logs_a_failed_removal_but_continues(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A deletion failure never changes a subsequent runner's outcome."""
    dead = tmp_path / "covns-dead"
    live = tmp_path / "covns-live"
    dead.mkdir()
    live.mkdir()
    _write_creator_record(namespace_dir=dead, creator={"pid": 999_999_999, "start_time": "gone"})
    _write_creator_record(namespace_dir=live, creator={"pid": 999_999_999, "start_time": "gone"})
    original_rmtree = namespaces.shutil.rmtree

    def fail_first(path: Path) -> None:
        if path == dead:
            raise PermissionError(path)
        original_rmtree(path)

    monkeypatch.setattr(namespaces.shutil, "rmtree", fail_first)
    namespaces.reclaim_abandoned_namespace_dirs(root=tmp_path)

    assert dead.is_dir()
    assert not live.exists()


def test_a_namespace_without_an_observable_creator_identity_has_no_creator_record(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A runner writes no partial identity when procfs cannot identify itself."""

    def no_start_time(*, pid: int) -> None:
        _ = pid

    monkeypatch.setattr(namespaces, "process_start_time", no_start_time)

    directories = namespaces.build_namespace_dirs(
        targets=["check-coverage"], skip_set=frozenset(), root=tmp_path
    )

    namespace_dir = directories["full-tree"]
    assert not (namespace_dir / ".livespec-coverage-creator.json").exists()
    assert "could not observe this runner's start time" in caplog.text


def test_process_start_time_returns_none_when_procfs_cannot_be_read(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An inaccessible procfs entry never produces a partial creator record."""

    def refuse_procfs(path: Path, *, encoding: str) -> str:
        _ = (path, encoding)
        raise PermissionError(path)

    monkeypatch.setattr(namespaces.Path, "read_text", refuse_procfs)

    assert namespaces.process_start_time(pid=os.getpid()) is None


def test_reclaim_leaves_a_namespace_that_vanishes_during_record_lookup(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A concurrently removed namespace is skipped without making the sweep fail."""
    namespace_dir = tmp_path / "covns-vanishing"
    namespace_dir.mkdir()
    original_read_text = namespaces.Path.read_text

    def vanish(path: Path, *, encoding: str) -> str:
        if path.name == ".livespec-coverage-creator.json":
            namespace_dir.rmdir()
            raise FileNotFoundError(path)
        return original_read_text(path, encoding=encoding)

    monkeypatch.setattr(namespaces.Path, "read_text", vanish)
    namespaces.reclaim_abandoned_namespace_dirs(root=tmp_path)

    assert not namespace_dir.exists()


def test_reclaim_logs_invalid_json_and_an_unstatable_absent_namespace(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A sweep logs uncertain state and leaves it rather than guessing it is stale."""
    invalid = tmp_path / "covns-invalid-json"
    unstatable = tmp_path / "covns-unstatable"
    invalid.mkdir()
    unstatable.mkdir()
    _ = (invalid / ".livespec-coverage-creator.json").write_text("{", encoding="utf-8")
    original_stat = namespaces.Path.stat

    def refuse_namespace_stat(path: Path, *, follow_symlinks: bool = True) -> os.stat_result:
        if path == unstatable:
            raise PermissionError(path)
        return original_stat(path, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(namespaces.Path, "stat", refuse_namespace_stat)
    namespaces.reclaim_abandoned_namespace_dirs(root=tmp_path)

    assert invalid.is_dir()
    assert original_stat(unstatable).st_mode
    assert "malformed creator record" in caplog.text
    assert "could not stat coverage namespace" in caplog.text


def test_reclaim_silently_skips_a_directory_that_vanishes_during_removal(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A race with normal cleanup is not an error and cannot stop the sweep."""
    namespace_dir = tmp_path / "covns-rmtree-race"
    namespace_dir.mkdir()
    _write_creator_record(
        namespace_dir=namespace_dir, creator={"pid": 999_999_999, "start_time": "gone"}
    )
    original_rmtree = namespaces.shutil.rmtree

    def remove_then_report_missing(path: Path) -> None:
        original_rmtree(path)
        raise FileNotFoundError(path)

    monkeypatch.setattr(namespaces.shutil, "rmtree", remove_then_report_missing)
    namespaces.reclaim_abandoned_namespace_dirs(root=tmp_path)

    assert not namespace_dir.exists()


def test_reclaim_ignores_a_matching_file_and_logs_a_creator_record_write_failure(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Only directories are reclaimed, and a record-write failure remains fail-open."""
    matching_file = tmp_path / "covns-not-a-directory"
    _ = matching_file.write_text("keep", encoding="utf-8")
    original_write_text = namespaces.Path.write_text

    def refuse_creator_record(path: Path, data: str, *, encoding: str) -> int:
        if path.name == ".livespec-coverage-creator.json":
            raise PermissionError(path)
        return original_write_text(path, data, encoding=encoding)

    monkeypatch.setattr(namespaces.Path, "write_text", refuse_creator_record)
    directories = namespaces.build_namespace_dirs(
        targets=["check-coverage"], skip_set=frozenset(), root=tmp_path
    )

    assert matching_file.read_text(encoding="utf-8") == "keep"
    assert not (directories["full-tree"] / ".livespec-coverage-creator.json").exists()
    assert "could not record coverage creator" in caplog.text
