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
        ([subprocess.CompletedProcess([], 2, "", "")], "mutmut run failed"),
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
                subprocess.CompletedProcess([], 1, "", ""),
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
