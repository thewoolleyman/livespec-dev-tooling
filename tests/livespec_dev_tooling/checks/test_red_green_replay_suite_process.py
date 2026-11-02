"""Tests for the suite-green subprocess progress bound."""

from __future__ import annotations

import contextlib
import importlib.util
import sys
import time
import uuid
from pathlib import Path

__all__: list[str] = []

_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / "livespec_dev_tooling"
    / "checks"
    / "_red_green_replay_suite_process.py"
)


def _load():
    spec = importlib.util.spec_from_file_location(
        "_rgr_suite_process_under_test", str(_MODULE_PATH)
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_progress_resets_the_stall_window_and_an_optional_ceiling_still_applies() -> None:
    """Only silence stalls a slow suite, while an operator ceiling remains absolute."""
    assert _MODULE_PATH.is_file()
    mod = _load()
    bound = mod.SuiteBound(stall_seconds=900, ceiling_seconds=None)
    assert mod.kill_reason(started=0.0, last_progress=10_740.0, now=10_800.0, bound=bound) is None
    assert (
        mod.kill_reason(started=0.0, last_progress=9_900.0, now=10_800.0, bound=bound) == "stalled"
    )
    ceiling = mod.SuiteBound(stall_seconds=900, ceiling_seconds=4_800)
    assert mod.kill_reason(started=0.0, last_progress=4_799.0, now=4_799.5, bound=ceiling) is None
    assert (
        mod.kill_reason(started=0.0, last_progress=4_799.0, now=4_800.0, bound=ceiling) == "ceiling"
    )


def test_each_output_chunk_restarts_the_stall_window() -> None:
    mod = _load()
    now = [5.0]
    progress = mod.SuiteProgress(clock=lambda: now[0])
    now[0] = 700.0
    progress.saw(chunk="....")
    now[0] = 1_200.0
    progress.saw(chunk="..F.\n")
    assert progress.last == 1_200.0
    assert progress.output == "......F.\n"


def test_run_suite_captures_combined_output_and_returncode() -> None:
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


def test_a_stalled_run_kills_the_whole_process_group(tmp_path: Path) -> None:
    mod = _load()
    token = f"livespec-stall-killpg-probe-{uuid.uuid4().hex}"
    spawned = tmp_path / "spawned"
    leader = f"sh -c ': > {spawned}; sleep 300; :' {token} & sleep 300; :"

    run = mod.run_suite(
        argv=["sh", "-c", leader],
        bound=mod.SuiteBound(stall_seconds=2, ceiling_seconds=None),
    )

    assert run.timed_out is True
    assert run.kill_reason == "stalled"
    assert run.returncode is None
    assert spawned.exists(), "the marked grandchild never started, so the kill proved nothing"
    hang_guard = time.monotonic() + 30
    while _live_processes_carrying(token) and time.monotonic() < hang_guard:  # pragma: no branch
        time.sleep(0.1)  # pragma: no cover
    assert _live_processes_carrying(token) == []


def test_a_closed_pipe_is_not_progress_so_a_silent_survivor_still_stalls() -> None:
    """EOF on the output pipe is not output; a suite that closes it and idles is killed."""
    mod = _load()
    run = mod.run_suite(
        argv=[sys.executable, "-c", "import os, time; os.close(1); os.close(2); time.sleep(20)"],
        bound=mod.SuiteBound(stall_seconds=2, ceiling_seconds=None),
    )
    assert run.kill_reason == "stalled"
    assert run.timed_out is True
    assert run.returncode is None
