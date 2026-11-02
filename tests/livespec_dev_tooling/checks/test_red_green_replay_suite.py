"""Mirror-paired test for `livespec_dev_tooling/checks/_red_green_replay_suite.py`.

The helper carries the suite-green leg's worker-count argv, progress-bounded
run, process-group kill, and order-independent output checksum.
"""

from __future__ import annotations

import importlib.util
import inspect
import sys
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
    argv = mod.suite_pytest_argv(
        environ={"test_nprocs": "4"}, xdist_available=True, visible_cpus=32
    )
    assert argv == [sys.executable, "-m", "pytest", "--tb=line", "-q", "-n", "4"]


def test_argv_accepts_staged_test_paths() -> None:
    """A test-only suite-green leg selects its staged test files."""
    mod = _load()
    assert "test_paths" in inspect.signature(mod.suite_pytest_argv).parameters
    argv = mod.suite_pytest_argv(
        environ={},
        test_paths=["tests/test_changed.py"],
        xdist_available=True,
        visible_cpus=32,
    )
    assert argv[-3:] == ["-n", "8", "tests/test_changed.py"]


def test_shared_test_support_excludes_documentation_but_keeps_executable_support() -> None:
    """Only material that can affect other tests broadens suite-green replay."""
    mod = _load()
    assert hasattr(mod, "has_shared_test_support")
    assert not mod.has_shared_test_support(
        staged_paths=["tests/test_changed.py", "tests/prompts/CLAUDE.md"]
    )
    assert mod.has_shared_test_support(staged_paths=["tests/test_changed.py", "tests/conftest.py"])
    assert mod.has_shared_test_support(
        staged_paths=["tests/test_changed.py", "tests/fixtures/user.json"]
    )


# Without `test_nprocs` (most consumers compute it in a script and never export
# it) the worker count follows the SAME lane-aware rule their justfiles use:
# `auto` only on the hosted CI lane, then LIVESPEC_TEST_PARALLELISM, then a
# quarter of the visible CPUs (min 1). Never a bare `auto` elsewhere: in a
# factory pod xdist's `auto` sees every HOST core (32-72) against a 4-cpu quota.
def test_argv_unset_uses_auto_only_on_the_hosted_lane() -> None:
    mod = _load()
    argv = mod.suite_pytest_argv(
        environ={"LIVESPEC_CI_LANE": "hosted"}, xdist_available=True, visible_cpus=32
    )
    assert argv[-2:] == ["-n", "auto"]


def test_argv_unset_honours_livespec_test_parallelism() -> None:
    mod = _load()
    argv = mod.suite_pytest_argv(
        environ={"test_nprocs": " ", "LIVESPEC_TEST_PARALLELISM": "6"},
        xdist_available=True,
        visible_cpus=32,
    )
    assert argv[-2:] == ["-n", "6"]


def test_argv_unset_uses_a_quarter_of_visible_cpus_minimum_one() -> None:
    mod = _load()
    cases = ((32, "8"), (72, "18"), (4, "1"), (1, "1"))
    for visible_cpus, expected in cases:
        argv = mod.suite_pytest_argv(environ={}, xdist_available=True, visible_cpus=visible_cpus)
        assert argv[-2:] == ["-n", expected]


def test_argv_falls_back_to_serial_without_xdist() -> None:
    mod = _load()
    argv = mod.suite_pytest_argv(
        environ={"test_nprocs": "4"}, xdist_available=False, visible_cpus=32
    )
    assert argv == [sys.executable, "-m", "pytest", "--tb=line", "-q"]


def test_xdist_importable_matches_find_spec() -> None:
    mod = _load()
    assert mod.xdist_importable() is (importlib.util.find_spec("xdist") is not None)


def test_the_run_uses_a_stall_window_with_an_optional_total_ceiling() -> None:
    """A slow host gets as long as it keeps printing; there is no default ceiling."""
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
        bound=mod.SuiteBound(stall_seconds=30, ceiling_seconds=None),
    )
    assert run.returncode == 3
    assert run.timed_out is False
    assert run.kill_reason is None
    assert "out" in run.output
    assert "err" in run.output
