"""Mirror-paired test for the suite-green progress-bound runner."""

from __future__ import annotations

import ast
import contextlib
import errno
import importlib.util
import inspect
import os
import signal
import sys
import threading
import time
import types
import uuid
from pathlib import Path

import pytest

__all__: list[str] = []


_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / "livespec_dev_tooling"
    / "checks"
    / "_red_green_replay_suite_runner.py"
)
_CONFTEST_PATH = Path(__file__).resolve().parents[2] / "conftest.py"


def _load():
    spec = importlib.util.spec_from_file_location("_rgr_suite_runner_under_test", str(_MODULE_PATH))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _process_missing(*_args: object) -> None:
    """Model a process that exits between observation and signalling."""
    raise ProcessLookupError


def _process_forbidden(*_args: object) -> None:
    """Model a process that can be observed but not signalled."""
    raise PermissionError


def test_the_run_is_bounded_by_a_stall_window_and_no_default_wall_clock_ceiling() -> None:
    """A slow host gets as long as it keeps making progress; nothing caps it by default."""
    assert _MODULE_PATH.is_file()
    mod = _load()
    bound = mod.suite_bound(environ={})
    assert bound.stall_seconds == mod.DEFAULT_STALL_SECONDS == 900
    assert bound.ceiling_seconds is None
    assert mod.suite_bound(environ={"LIVESPEC_SUITE_GREEN_STALL_SECONDS": "90"}).stall_seconds == 90
    ceiling = mod.suite_bound(environ={"LIVESPEC_SUITE_GREEN_TIMEOUT_SECONDS": "4800"})
    assert ceiling.ceiling_seconds == 4800
    assert ceiling.stall_seconds == 900
    for bad in ("", "abc", "0", "-5"):
        environ = {
            "LIVESPEC_SUITE_GREEN_STALL_SECONDS": bad,
            "LIVESPEC_SUITE_GREEN_TIMEOUT_SECONDS": bad,
        }
        assert mod.suite_bound(environ=environ) == mod.SuiteBound(
            stall_seconds=900, ceiling_seconds=None
        )


def test_progress_resets_the_stall_window_however_long_the_run_has_lasted() -> None:
    """The kill decision reads the last progress instant, never the start alone."""
    mod = _load()
    bound = mod.SuiteBound(stall_seconds=900, ceiling_seconds=None)
    assert mod.kill_reason(started=0.0, last_progress=10_740.0, now=10_800.0, bound=bound) is None
    assert (
        mod.kill_reason(started=0.0, last_progress=9_900.0, now=10_800.0, bound=bound) == "stalled"
    )


def test_an_operator_ceiling_still_ends_a_suite_that_keeps_making_progress() -> None:
    mod = _load()
    bound = mod.SuiteBound(stall_seconds=900, ceiling_seconds=4800)
    assert mod.kill_reason(started=0.0, last_progress=4_799.0, now=4_799.5, bound=bound) is None
    assert (
        mod.kill_reason(started=0.0, last_progress=4_799.0, now=4_800.0, bound=bound) == "ceiling"
    )


def test_every_chunk_of_output_is_progress() -> None:
    """The tracker stamps each chunk with the clock, so the window restarts on it."""
    mod = _load()
    now = [5.0]
    progress = mod.SuiteProgress(clock=lambda: now[0])
    assert progress.last == 5.0
    now[0] = 700.0
    progress.saw(chunk="....")
    now[0] = 1_200.0
    progress.saw(chunk="..F.\n")
    assert progress.last == 1_200.0
    assert progress.output == "......F.\n"


def test_every_chunk_of_output_renews_the_gate_runners_progress_stamp(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Suite progress reaches gate-run.sh's outer stall bound (livespec-dev-tooling-54usvh).

    The leg captures pytest's output, so gate-run.sh's output.log stays silent
    while the suite works; the runner's progress stamp is the only signal left.
    """
    mod = _load()
    stamp = tmp_path / "progress.stamp"
    stamp.touch()
    os.utime(stamp, (1_000_000, 1_000_000))
    monkeypatch.setenv("LIVESPEC_GATE_RUN_PROGRESS_STAMP", str(stamp))
    progress = mod.SuiteProgress(clock=time.monotonic)

    progress.saw(chunk="....")

    assert stamp.stat().st_mtime > 1_000_000


def test_run_suite_captures_output_and_returncode() -> None:
    mod = _load()
    run = mod.run_suite(
        argv=[
            sys.executable,
            "-c",
            "import sys; print('out'); print('err', file=sys.stderr); sys.exit(3)",
        ],
        bound=mod.SuiteBound(stall_seconds=30, ceiling_seconds=None),
    )
    assert run.returncode == 3
    assert run.timed_out is False
    assert run.kill_reason is None
    assert "out" in run.output
    assert "err" in run.output


# The child declares the run's time itself and moves it only after the runner
# has received its previous line: the verdict rests on output renewing the
# window, never on how fast the host starts a process or schedules a thread.
_RENDEZVOUS_CHILD = """
import os, sys, time

now_path, seen_path, polls_path = sys.argv[1:4]


def read(path):
    with open(path) as handle:
        return float(handle.read())


def put(path, value):
    with open(path + ".tmp", "w") as handle:
        handle.write(value)
    os.replace(path + ".tmp", path)


liveness_deadline = time.monotonic() + 120


def wait_past(path, count):
    while read(path) <= count:
        if time.monotonic() > liveness_deadline:
            sys.exit(3)
        time.sleep(0.01)


assert sys.stdout.isatty()
for now, line in (("0", "collecting tests"), ("1.5", "bringing up xdist workers"), ("3", ".")):
    put(now_path, now)
    seen = read(seen_path)
    print(line, flush=True)
    wait_past(seen_path, seen)
wait_past(polls_path, read(polls_path))
"""


def _bump(*, counter: Path) -> None:
    staged = counter.with_name(counter.name + ".tmp")
    _ = staged.write_text(str(int(float(counter.read_text())) + 1))
    _ = staged.replace(counter)


def test_interactive_collection_and_worker_startup_output_renews_the_stall_window(
    *, tmp_path: Path
) -> None:
    """A terminal-aware pytest session reports work before any test completes.

    The clock reads the time the child declares. The child moves it 1.5 s per
    line, and only once the runner has stamped its previous line, so the run
    spans 3 s against a 2 s window. It survives only because each line renewed
    the window, and it then waits for one more stall check at the 3 s mark.
    """
    mod = _load()
    now, seen, polls = tmp_path / "now", tmp_path / "seen", tmp_path / "polls"
    for path in (now, seen, polls):
        _ = path.write_text("0")
    runner_thread = threading.get_ident()

    def clock() -> float:
        reading = float(now.read_text())
        _bump(counter=polls if threading.get_ident() == runner_thread else seen)
        return reading

    run = mod.run_suite(
        argv=[sys.executable, "-c", _RENDEZVOUS_CHILD, str(now), str(seen), str(polls)],
        bound=mod.SuiteBound(stall_seconds=2, ceiling_seconds=None),
        clock=clock,
    )

    assert run.kill_reason is None
    assert run.returncode == 0
    assert run.timed_out is False
    assert "collecting tests" in run.output
    assert "bringing up xdist workers" in run.output


def test_terminal_reader_completes_when_an_empty_read_ends_its_stream(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The pseudo-terminal reader treats ordinary EOF as a clean stream close."""
    mod = _load()
    assert "fd" in inspect.signature(mod._drain).parameters  # noqa: SLF001
    reads = iter((b"collection\n", b""))
    monkeypatch.setattr(mod.os, "read", lambda _fd, _size: next(reads))
    progress = mod.SuiteProgress(clock=time.monotonic)

    mod._drain(fd=42, progress=progress)  # noqa: SLF001

    assert progress.output == "collection\n"


def test_terminal_reader_propagates_non_terminal_read_failures(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only the terminal's EIO end-of-stream signal is handled as a clean close."""
    mod = _load()
    assert "fd" in inspect.signature(mod._drain).parameters  # noqa: SLF001

    def read_failure(_fd: int, _size: int) -> bytes:
        raise OSError(errno.EBADF, "bad file descriptor")

    monkeypatch.setattr(mod.os, "read", read_failure)
    progress = mod.SuiteProgress(clock=time.monotonic)

    with pytest.raises(OSError, match="bad file descriptor") as raised:
        mod._drain(fd=42, progress=progress)  # noqa: SLF001
    assert raised.value.errno == errno.EBADF


def test_completion_summary_distinguishes_pre_test_output_from_completed_tests() -> None:
    """Only output recording a completed test is reported as having completed one."""
    mod = _load()

    assert mod.test_completion_summary(output="collecting tests\r\n") == "no test had completed"
    assert mod.test_completion_summary(output="") == "no test had completed"
    assert mod.test_completion_summary(output="collecting\r\n..\r\n") == (
        "at least one test had completed"
    )
    assert mod.test_completion_summary(output="[gw0] [ 1%] PASSED tests/test_x.py::t\n") == (
        "at least one test had completed"
    )


def test_completion_summary_sees_completed_tests_through_pseudo_terminal_colour() -> None:
    """Colour escapes pytest writes on a terminal do not hide a completed test."""
    mod = _load()

    assert mod.test_completion_summary(output="\x1b[32m.\x1b[0m\x1b[32m.\x1b[0m") == (
        "at least one test had completed"
    )
    assert mod.test_completion_summary(
        output="[gw0] \x1b[32mPASSED\x1b[0m tests/test_x.py::t\n"
    ) == ("at least one test had completed")
    assert mod.test_completion_summary(output="\x1b[1m\rbringing up nodes...\x1b[0m") == (
        "no test had completed"
    )


def _live_processes_carrying(token: str) -> list[str]:
    """Pids of non-zombie processes whose command line carries `token`."""
    live: list[str] = []
    for proc in Path("/proc").glob("[0-9]*"):
        cmdline, state = "", "Z"
        with contextlib.suppress(OSError):
            cmdline = (proc / "cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
            state = (proc / "stat").read_text().rsplit(")", 1)[1].split()[0]
        live += [proc.name] * (token in cmdline and state != "Z")
    return live


def test_a_silent_suite_is_killed_whole_once_it_stalls(tmp_path: Path) -> None:
    """A stalled suite kills its process group, including a background child."""
    mod = _load()
    token = f"livespec-stall-killpg-probe-{uuid.uuid4().hex}"
    spawned = tmp_path / "spawned"
    leader = f"sh -c ': > {spawned}; sleep 300; :' {token} & printf ready; sleep 300; :"

    run = mod.run_suite(
        argv=["sh", "-c", leader],
        bound=mod.SuiteBound(stall_seconds=2, ceiling_seconds=None),
    )

    assert run.timed_out is True
    assert run.kill_reason == "stalled"
    assert run.returncode is None
    assert "ready" in run.output
    assert spawned.exists(), "the marked child never started, so the kill proved nothing"
    hang_guard = time.monotonic() + 30
    while _live_processes_carrying(token) and time.monotonic() < hang_guard:  # pragma: no branch
        time.sleep(0.1)  # pragma: no cover
    assert not _live_processes_carrying(token)


def test_a_stalled_suite_reaps_a_descendant_that_started_its_own_session() -> None:
    """A stalled suite terminates a session-escaping subprocess too."""
    mod = _load()
    token = f"livespec-stall-session-escape-{uuid.uuid4().hex}"
    escaped = (
        f"setsid {sys.executable} -c 'import time; time.sleep(300)' {token} & "
        "printf ready; sleep 300"
    )
    try:
        run = mod.run_suite(
            argv=["sh", "-c", escaped],
            bound=mod.SuiteBound(stall_seconds=2, ceiling_seconds=None),
        )

        assert run.timed_out is True
        assert run.kill_reason == "stalled"
        assert not _live_processes_carrying(token)
        assert "ending out-of-group descendant pid=" in run.output
        assert token in run.output
    finally:
        _ = [os.kill(int(pid), signal.SIGTERM) for pid in _live_processes_carrying(token)]


def test_process_cleanup_tolerates_unavailable_process_records_and_disappearing_pids(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The cleanup path safely handles incomplete process-table observations."""
    mod = _load()

    def unavailable(**_kwargs: object) -> None:
        raise OSError("ps unavailable")

    monkeypatch.setattr(mod.subprocess, "run", unavailable)
    assert mod.process_table() == {}
    monkeypatch.setattr(
        mod.subprocess,
        "run",
        lambda **_kwargs: types.SimpleNamespace(returncode=1, stdout=""),
    )
    assert mod.process_table() == {}
    listing = types.SimpleNamespace(
        returncode=0, stdout="short\nnot-a-pid 2 3 command\n4 5 6 command line\n"
    )
    monkeypatch.setattr(mod.subprocess, "run", lambda **_kwargs: listing)
    assert mod.process_table() == {4: (5, 6, "command line")}

    monkeypatch.setattr(mod.os, "kill", _process_missing)
    assert mod.is_alive(pid=1) is False

    monkeypatch.setattr(mod.os, "kill", _process_forbidden)
    assert mod.is_alive(pid=1) is True

    class FinishedProcess:
        pid = 1

        def poll(self) -> int:
            return 0

    monkeypatch.setattr(mod, "out_of_group_descendants", lambda **_kwargs: ((2, "escaped"),))
    alive = iter((True, False, True))
    monkeypatch.setattr(mod, "is_alive", lambda **_kwargs: next(alive))
    monkeypatch.setattr(mod.os, "kill", _process_missing)
    monkeypatch.setattr(mod.os, "killpg", _process_missing)
    reported: list[str] = []
    assert mod.end_stalled_suite(proc=FinishedProcess(), report=reported.append) == (
        (2, "escaped"),
    )
    assert reported == ["suite-green: ending out-of-group descendant pid=2 cmdline=escaped\n"]

    alive = iter((True, False, False))
    monkeypatch.setattr(mod, "is_alive", lambda **_kwargs: next(alive))
    assert mod.end_stalled_suite(proc=FinishedProcess()) == ((2, "escaped"),)


def test_the_gate_runners_progress_stamp_is_one_of_the_scrubbed_gate_variables() -> None:
    """The caller's progress stamp is scrubbed like every gate-shaping variable.

    gate-run.sh exports LIVESPEC_GATE_RUN_PROGRESS_STAMP to the gated command, so
    under the detached runner every test saw it set and the `if stamp:` false
    branch of `SuiteProgress.saw` was never taken, which failed
    check-per-file-coverage on a passing suite (livespec-dev-tooling-khjkyu).
    The suite's autouse fixture unsets exactly the variables this tuple names.
    """
    tree = ast.parse(_CONFTEST_PATH.read_text(encoding="utf-8"))
    scrubbed = {
        element.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "_CALLER_GATE_VARIABLES" for t in node.targets)
        and isinstance(node.value, ast.Tuple)
        for element in node.value.elts
        if isinstance(element, ast.Constant)
    }
    assert "LIVESPEC_GATE_RUN_PROGRESS_STAMP" in scrubbed
