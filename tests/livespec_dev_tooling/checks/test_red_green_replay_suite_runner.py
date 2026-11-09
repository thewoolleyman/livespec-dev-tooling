"""Mirror-paired test for the suite-green progress-bound runner."""

from __future__ import annotations

import contextlib
import errno
import importlib.util
import inspect
import os
import re
import sys
import time
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


def _load():
    spec = importlib.util.spec_from_file_location("_rgr_suite_runner_under_test", str(_MODULE_PATH))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


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


def test_interactive_collection_and_worker_startup_output_renews_the_stall_window() -> None:
    """A terminal-aware pytest session reports work before any test completes."""
    mod = _load()
    run = mod.run_suite(
        argv=[
            sys.executable,
            "-c",
            "import sys, time; "
            "assert sys.stdout.isatty(); "
            "print('collecting tests', flush=True); "
            "time.sleep(1.25); "
            "print('bringing up xdist workers', flush=True); "
            "time.sleep(1.25); "
            "print('.', flush=True)",
        ],
        bound=mod.SuiteBound(stall_seconds=2, ceiling_seconds=None),
    )

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


def _stalled_pytest_run(
    *, project: Path, files: dict[str, str], extra_args: list[str], monkeypatch: pytest.MonkeyPatch
):
    """Run a real pytest project through `run_suite` until its 4 second stall window ends it."""
    mod = _load()
    for name, body in files.items():
        (project / name).write_text(body, encoding="utf-8")
    monkeypatch.chdir(project)
    return mod.run_suite(
        argv=[sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *extra_args],
        bound=mod.SuiteBound(stall_seconds=4, ceiling_seconds=None),
    )


def test_a_stalled_run_names_its_elapsed_seconds_completed_tests_and_last_test(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = _stalled_pytest_run(
        project=tmp_path,
        files={
            "test_slow.py": (
                "import time\n\n\n"
                "def test_fast():\n    pass\n\n\n"
                "def test_hangs():\n    time.sleep(120)\n\n\n"
                "def test_never_reached():\n    pass\n"
            )
        },
        extra_args=[],
        monkeypatch=monkeypatch,
    )

    assert run.kill_reason == "stalled"
    assert run.attribution is not None
    assert "1 of 3 collected tests had completed" in run.attribution
    assert "test_slow.py::test_fast" in run.attribution
    assert re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", run.attribution)
    elapsed = re.search(r"after (\d+) seconds", run.attribution)
    assert elapsed is not None
    assert int(elapsed[1]) >= 4


def test_a_run_ended_during_collection_says_collection_had_not_finished(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = _stalled_pytest_run(
        project=tmp_path,
        files={
            "conftest.py": "import time\n\ntime.sleep(120)\n",
            "test_never.py": "def test_never():\n    pass\n",
        },
        extra_args=[],
        monkeypatch=monkeypatch,
    )

    assert run.kill_reason == "stalled"
    assert run.attribution is not None
    assert "collection had not finished" in run.attribution
    assert "no test had completed" in run.attribution


def test_a_stalled_xdist_run_names_each_running_test_its_duration_and_worker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = _stalled_pytest_run(
        project=tmp_path,
        files={
            "test_slow.py": (
                "import time\n\n\n"
                "def test_fast():\n    pass\n\n\n"
                "def test_hangs():\n    time.sleep(120)\n"
            )
        },
        extra_args=["-n", "2"],
        monkeypatch=monkeypatch,
    )

    assert run.kill_reason == "stalled"
    assert run.attribution is not None
    assert re.search(r"test_slow\.py::test_hangs on worker gw\d+ for \d+ seconds", run.attribution)
    assert "test_fast on" not in run.attribution
    assert "stalled mid-suite" in run.attribution


def test_a_run_that_stalls_after_its_last_test_is_reported_as_a_post_last_test_stall(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = _stalled_pytest_run(
        project=tmp_path,
        files={
            "conftest.py": ("import time\n\n\ndef pytest_sessionfinish():\n    time.sleep(120)\n"),
            "test_done.py": "def test_one():\n    pass\n\n\ndef test_two():\n    pass\n",
        },
        extra_args=[],
        monkeypatch=monkeypatch,
    )

    assert run.kill_reason == "stalled"
    assert run.attribution is not None
    assert "2 of 2 collected tests had completed" in run.attribution
    assert "stalled after its last test rather than mid-suite" in run.attribution
    assert "test_done.py::test_two" in run.attribution
