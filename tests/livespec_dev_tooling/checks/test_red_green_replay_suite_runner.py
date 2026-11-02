"""Mirror coverage for the suite-green subprocess-progress runner."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

__all__: list[str] = []


_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / "livespec_dev_tooling"
    / "checks"
    / "_red_green_replay_suite_runner.py"
)


def test_runner_module_exists_and_exposes_the_progress_bound_api() -> None:
    """The cohesive runner owns the process-group and progress-bound primitives."""
    assert _MODULE_PATH.is_file()
    spec = importlib.util.spec_from_file_location("_rgr_suite_runner_under_test", str(_MODULE_PATH))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    assert callable(module.run_suite)
    assert callable(module.kill_reason)
    assert module.SuiteProgress(clock=lambda: 0.0).output == ""


def test_runner_keeps_a_trailing_partial_utf8_code_point_as_output() -> None:
    """Final decoder output is progress too, rather than silently discarded."""
    spec = importlib.util.spec_from_file_location("_rgr_suite_runner_tail", str(_MODULE_PATH))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    run = module.run_suite(
        argv=[sys.executable, "-c", "import os; os.write(1, b'\\xc3')"],
        bound=module.SuiteBound(stall_seconds=5, ceiling_seconds=None),
    )
    assert run.output == "�"
