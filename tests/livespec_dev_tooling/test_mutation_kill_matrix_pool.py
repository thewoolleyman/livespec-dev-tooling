"""Tests for the kill matrix's worker pool."""

from __future__ import annotations

import importlib
import subprocess
from pathlib import Path

import pytest

__all__: list[str] = []


def test_nothing_pending_runs_nothing(*, tmp_path: Path) -> None:
    """An all-cached run makes no worker tree at all."""
    module = importlib.import_module("livespec_dev_tooling.mutation_kill_matrix_pool")

    assert (
        module.run_pending(
            execute=None, target=tmp_path, plans=[], workers=4, timeout=1.0, workspace=None
        )
        == {}
    )


def test_a_worker_failure_is_raised_on_the_calling_thread(*, tmp_path: Path) -> None:
    """An error inside a worker fails the run instead of vanishing with its thread."""
    module = importlib.import_module("livespec_dev_tooling.mutation_kill_matrix_pool")
    execution = importlib.import_module("livespec_dev_tooling.mutation_kill_matrix_execution")
    stages = importlib.import_module("livespec_dev_tooling.mutation_kill_matrix_stages")
    report = importlib.import_module("livespec_dev_tooling.mutation_kill_matrix")
    target = tmp_path / "pkg"
    target.mkdir()

    def execute(
        *, args: list[str], cwd: Path, timeout: float | None = None
    ) -> subprocess.CompletedProcess[str]:
        if "apply" in args:
            message = "apply exploded"
            raise OSError(message)
        return execution.execute_command(args=args, cwd=cwd, timeout=timeout)

    plan = stages.MutantPlan(
        mutant=report.Mutant(identifier="pkg.x_f__mutmut_1", location="mutmut:pkg.x_f__mutmut_1"),
        span=None,
        selected=[],
        key="k",
    )

    with pytest.raises(OSError, match="apply exploded"):
        _ = module.run_pending(
            execute=execute, target=target, plans=[plan], workers=2, timeout=1.0, workspace=tmp_path
        )
