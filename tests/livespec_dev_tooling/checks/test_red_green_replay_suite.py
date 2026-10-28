"""Mirror-paired test for `livespec_dev_tooling/checks/_red_green_replay_suite.py`.

The helper carries the suite-green leg's worker-count argv, bounded
timeout, process-group kill, and order-independent output checksum.
"""

from __future__ import annotations

import importlib.util
import sys
import time
from pathlib import Path

__all__: list[str] = []

_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / "livespec_dev_tooling"
    / "checks"
    / "_red_green_replay_suite.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("_rgr_suite_under_test", str(_MODULE_PATH))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_argv_uses_test_nprocs_for_worker_count() -> None:
    mod = _load()
    argv = mod.suite_pytest_argv(environ={"test_nprocs": "4"}, xdist_available=True)
    assert argv == [sys.executable, "-m", "pytest", "--tb=no", "-q", "-n", "4"]


def test_argv_defaults_to_auto_when_unset_or_blank() -> None:
    mod = _load()
    for environ in ({}, {"test_nprocs": ""}, {"test_nprocs": "  "}):
        argv = mod.suite_pytest_argv(environ=environ, xdist_available=True)
        assert argv[-2:] == ["-n", "auto"]


def test_argv_falls_back_to_serial_without_xdist() -> None:
    mod = _load()
    argv = mod.suite_pytest_argv(environ={"test_nprocs": "4"}, xdist_available=False)
    assert argv == [sys.executable, "-m", "pytest", "--tb=no", "-q"]


def test_xdist_importable_matches_find_spec() -> None:
    mod = _load()
    assert mod.xdist_importable() is (importlib.util.find_spec("xdist") is not None)


def test_timeout_default_and_override() -> None:
    mod = _load()
    assert mod.DEFAULT_TIMEOUT_SECONDS == 2400
    assert mod.suite_timeout_seconds(environ={}) == 2400
    assert mod.suite_timeout_seconds(environ={"LIVESPEC_SUITE_GREEN_TIMEOUT_SECONDS": "90"}) == 90
    for bad in ("", "abc", "0", "-5"):
        environ = {"LIVESPEC_SUITE_GREEN_TIMEOUT_SECONDS": bad}
        assert mod.suite_timeout_seconds(environ=environ) == 2400


def test_checksum_ignores_line_order_and_duration() -> None:
    mod = _load()
    first = (
        "..F.  [ 50%]\n[gw0] PASSED a\n[gw1] PASSED b\nWARNING x\nWARNING y\n3 passed in 12.34s\n"
    )
    second = "created: 2/2 workers\nWARNING y\nWARNING x\n3 passed in 0.50s (0:00:00)\n"
    assert mod.canonical_output_checksum(output=first) == mod.canonical_output_checksum(
        output=second
    )
    assert mod.canonical_output_checksum(output=first).startswith("sha256:")


def test_checksum_differs_when_outcome_count_differs() -> None:
    mod = _load()
    one = mod.canonical_output_checksum(output="3 passed in 1.00s\n")
    other = mod.canonical_output_checksum(output="4 passed in 1.00s\n")
    assert one != other


def test_run_suite_captures_output_and_returncode() -> None:
    mod = _load()
    run = mod.run_suite(
        argv=[
            sys.executable,
            "-c",
            "import sys; print('out'); print('err', file=sys.stderr); sys.exit(3)",
        ],
        timeout_seconds=30,
    )
    assert run.returncode == 3
    assert run.timed_out is False
    assert "out" in run.output
    assert "err" in run.output


def _is_gone(pid: int) -> bool:
    # A killed child is either already reaped (no /proc entry) or a zombie;
    # which one depends on timing, so neither arm may be a separate branch
    # that per-file coverage would need luck to reach.
    stat_path = Path(f"/proc/{pid}/stat")
    stat = stat_path.read_text() if stat_path.exists() else "(reaped) Z"
    return stat.rsplit(")", 1)[1].split()[0] == "Z"


def test_run_suite_timeout_kills_the_whole_process_group(tmp_path: Path) -> None:
    mod = _load()
    pid_file = tmp_path / "child.pid"
    script = (
        "import subprocess, sys, time\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(300)'])\n"
        f"open({str(pid_file)!r}, 'w').write(str(child.pid))\n"
        "time.sleep(300)\n"
    )
    run = mod.run_suite(argv=[sys.executable, "-c", script], timeout_seconds=2)
    assert run.timed_out is True
    assert run.returncode is None
    child_pid = int(pid_file.read_text())
    time.sleep(1)
    assert _is_gone(child_pid)
