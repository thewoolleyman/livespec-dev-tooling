"""Tests for the kill matrix's generate, measure and plan stages."""

from __future__ import annotations

import importlib
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

__all__: list[str] = []


def _scripted(
    outputs: list[subprocess.CompletedProcess[str]],
) -> Callable[..., subprocess.CompletedProcess[str]]:
    def execute(
        *, args: list[str], cwd: Path, timeout: float | None = None
    ) -> subprocess.CompletedProcess[str]:
        _ = args, cwd, timeout
        return outputs.pop(0)

    return execute


@pytest.mark.parametrize(
    ("outputs", "message"),
    [
        ([subprocess.CompletedProcess([], 1, "", "")], "mutmut could not generate"),
        (
            [
                subprocess.CompletedProcess([], 0, "", ""),
                subprocess.CompletedProcess([], 2, "", ""),
            ],
            "mutmut results failed",
        ),
        (
            [
                subprocess.CompletedProcess([], 0, "", ""),
                subprocess.CompletedProcess([], 0, "", ""),
            ],
            "mutmut generated no mutants",
        ),
        (
            [
                subprocess.CompletedProcess([], 0, "", ""),
                subprocess.CompletedProcess([], 0, "M1: survived\n", ""),
                subprocess.CompletedProcess([], 2, "", ""),
            ],
            "pytest collection failed",
        ),
    ],
)
def test_generation_refuses_unusable_mutmut_output(
    *, tmp_path: Path, outputs: list[subprocess.CompletedProcess[str]], message: str
) -> None:
    """A failed or empty measurement cannot become a Rule-26 report."""
    module = importlib.import_module("livespec_dev_tooling.mutation_kill_matrix_stages")

    with pytest.raises(RuntimeError, match=message):
        _ = module.generate(execute=_scripted(outputs), target=tmp_path)


def test_generation_lists_mutants_and_collected_tests(*, tmp_path: Path) -> None:
    """mutmut's rows become portable mutants and pytest's quiet output becomes node ids."""
    module = importlib.import_module("livespec_dev_tooling.mutation_kill_matrix_stages")
    outputs = [
        subprocess.CompletedProcess([], 0, "", ""),
        subprocess.CompletedProcess([], 0, "    pkg.x_f__mutmut_1: killed\n", ""),
        subprocess.CompletedProcess([], 0, "t.py::a\nt.py::b[x y]\n2 tests collected\n", ""),
    ]

    mutants, tests = module.generate(execute=_scripted(outputs), target=tmp_path)

    assert [mutant.identifier for mutant in mutants] == ["pkg.x_f__mutmut_1"]
    assert tests == ["t.py::a"]


def test_generation_only_generates_and_never_runs_mutmuts_own_mutation_run(
    *, tmp_path: Path
) -> None:
    """The engine needs mutmut's catalogue, not its run.

    `mutmut run` in 3.2.3 also runs mutmut's own per-test stats pass, a clean
    test run and a forked run of every mutant, all of which the engine
    discards.  Generation goes through mutmut's own generation functions.
    """
    module = importlib.import_module("livespec_dev_tooling.mutation_kill_matrix_stages")
    calls: list[list[str]] = []
    outputs = [
        subprocess.CompletedProcess([], 0, "", ""),
        subprocess.CompletedProcess([], 0, "    pkg.x_f__mutmut_1: not checked\n", ""),
        subprocess.CompletedProcess([], 0, "t.py::a\n", ""),
    ]

    def execute(
        *, args: list[str], cwd: Path, timeout: float | None = None
    ) -> subprocess.CompletedProcess[str]:
        _ = cwd, timeout
        calls.append(args)
        return outputs.pop(0)

    _ = module.generate(execute=execute, target=tmp_path)

    generation = calls[0]
    assert generation[generation.index("-c") + 1].count("create_mutants()") == 1
    assert all(call[-1] != "run" for call in calls)
