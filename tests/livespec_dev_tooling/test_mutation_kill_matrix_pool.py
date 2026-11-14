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


def test_a_run_without_an_outcome_callback_still_returns_every_outcome(*, tmp_path: Path) -> None:
    """The callback is optional: the pool's own result is the same with or without one."""
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
            return subprocess.CompletedProcess(args, 1, "", "cannot apply")
        return execution.execute_command(args=args, cwd=cwd, timeout=timeout)

    plan = stages.MutantPlan(
        mutant=report.Mutant(identifier="pkg.x_f__mutmut_1", location="mutmut:pkg.x_f__mutmut_1"),
        span=None,
        selected=[],
        key="k",
    )

    results = module.run_pending(
        execute=execute, target=target, plans=[plan], workers=1, timeout=1.0, workspace=tmp_path
    )

    assert set(results) == {"pkg.x_f__mutmut_1"}
    assert results["pkg.x_f__mutmut_1"].unapplied


def test_small_selections_checkpoint_first_without_losing_work(*, tmp_path: Path) -> None:
    """Cheap mutants yield checkpoints before heavy ones; equal costs keep input order."""
    module = importlib.import_module("livespec_dev_tooling.mutation_kill_matrix_pool")
    execution = importlib.import_module("livespec_dev_tooling.mutation_kill_matrix_execution")
    stages = importlib.import_module("livespec_dev_tooling.mutation_kill_matrix_stages")
    report = importlib.import_module("livespec_dev_tooling.mutation_kill_matrix")
    target = tmp_path / "pkg"
    target.mkdir()
    applied: list[str] = []
    checkpoints: list[str] = []

    def execute(
        *, args: list[str], cwd: Path, timeout: float | None = None
    ) -> subprocess.CompletedProcess[str]:
        if "apply" in args:
            applied.append(args[-1])
            return subprocess.CompletedProcess(args, 1, "", "cannot apply")
        return execution.execute_command(args=args, cwd=cwd, timeout=timeout)

    def checkpoint(*, identifier: str, outcome: object) -> None:
        _ = outcome
        checkpoints.append(identifier)

    identifiers = [f"pkg.x_f__mutmut_{index}" for index in range(1, 5)]
    plans = [
        stages.MutantPlan(
            mutant=report.Mutant(identifier=identifier, location=f"mutmut:{identifier}"),
            span=None,
            selected=[f"test_module.py::test_{index}" for index in range(size)],
            key=identifier,
        )
        for identifier, size in zip(identifiers, (200, 1, 1, 5), strict=True)
    ]
    original_order = [plan.mutant.identifier for plan in plans]

    results = module.run_pending(
        execute=execute,
        target=target,
        plans=plans,
        workers=1,
        timeout=1.0,
        workspace=tmp_path,
        on_outcome=checkpoint,
    )

    expected = [identifiers[index] for index in (1, 2, 3, 0)]
    assert applied == expected
    assert checkpoints == expected
    assert set(results) == set(identifiers)
    assert all(outcome.unapplied for outcome in results.values())
    assert [plan.mutant.identifier for plan in plans] == original_order
