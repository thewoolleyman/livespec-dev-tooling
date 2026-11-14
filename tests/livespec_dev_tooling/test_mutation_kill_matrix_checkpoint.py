"""Tests that a long kill-matrix run keeps its finished outcomes while it runs.

A full target runs about 30 million selected tests (82,617 mutants of the
orchestrator), which outlasts any one 24-hour Job.  Run 20261110t2 and run
20261111t1 would each have lost everything at their deadline, because the
cache was written only at the very end.  So the run checkpoints the cache as
mutants finish, a later run reuses those outcomes through the ordinary
content-keyed cache, and each checkpoint reports how far execution has got.
"""

from __future__ import annotations

import importlib
import io
import subprocess
from pathlib import Path

from livespec_dev_tooling.mutation_kill_matrix import Mutant

__all__: list[str] = []


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def _checkpoint(*, path: Path | None, clock: _Clock, stream: io.StringIO) -> object:
    module = importlib.import_module("livespec_dev_tooling.mutation_kill_matrix_checkpoint")
    cache = importlib.import_module("livespec_dev_tooling.mutation_kill_matrix_cache")
    return module.Checkpoint(
        path=path,
        keys={"pkg.x_f__mutmut_1": "key-1", "pkg.x_f__mutmut_2": "key-2"},
        seeded={"key-0": cache.CachedOutcome(unapplied=False, killed_by=("tests/t.py::reused",))},
        total=2,
        every_seconds=300.0,
        clock=clock,
        stream=stream,
    )


def test_a_checkpoint_saves_finished_and_reused_outcomes_once_its_interval_passes(
    *, tmp_path: Path
) -> None:
    """Nothing is written inside the interval; after it, the cache holds every outcome so far."""
    cache = importlib.import_module("livespec_dev_tooling.mutation_kill_matrix_cache")
    path = tmp_path / "cache.json"
    clock = _Clock()
    stream = io.StringIO()
    checkpoint = _checkpoint(path=path, clock=clock, stream=stream)
    killed = cache.CachedOutcome(unapplied=False, killed_by=("tests/t.py::kills",))

    clock.now = 10.0
    checkpoint.record(identifier="pkg.x_f__mutmut_1", outcome=killed)
    assert not path.exists()
    assert stream.getvalue() == ""

    clock.now = 301.0
    checkpoint.record(
        identifier="pkg.x_f__mutmut_2", outcome=cache.CachedOutcome(unapplied=True, killed_by=())
    )
    saved = cache.load_cache(path=path)
    assert saved == {
        "key-0": cache.CachedOutcome(unapplied=False, killed_by=("tests/t.py::reused",)),
        "key-1": killed,
        "key-2": cache.CachedOutcome(unapplied=True, killed_by=()),
    }
    assert stream.getvalue() == "mutation-kill-matrix: executed 2/2 mutants\n"
    assert [entry.name for entry in tmp_path.iterdir()] == ["cache.json"]


def test_a_checkpoint_without_a_cache_path_still_reports_progress(*, tmp_path: Path) -> None:
    """A --no-cache run writes no cache, but its log still says how far execution has got."""
    cache = importlib.import_module("livespec_dev_tooling.mutation_kill_matrix_cache")
    clock = _Clock()
    stream = io.StringIO()
    checkpoint = _checkpoint(path=None, clock=clock, stream=stream)

    clock.now = 400.0
    checkpoint.record(
        identifier="pkg.x_f__mutmut_1", outcome=cache.CachedOutcome(unapplied=True, killed_by=())
    )

    assert stream.getvalue() == "mutation-kill-matrix: executed 1/2 mutants\n"
    assert list(tmp_path.iterdir()) == []


def test_the_pool_reports_each_finished_mutant_as_it_finishes(*, tmp_path: Path) -> None:
    """The pool hands every outcome to its callback, so a checkpoint never waits for the end."""
    pool = importlib.import_module("livespec_dev_tooling.mutation_kill_matrix_pool")
    execution = importlib.import_module("livespec_dev_tooling.mutation_kill_matrix_execution")
    stages = importlib.import_module("livespec_dev_tooling.mutation_kill_matrix_stages")
    target = tmp_path / "pkg"
    target.mkdir()

    def execute(
        *, args: list[str], cwd: Path, timeout: float | None = None
    ) -> subprocess.CompletedProcess[str]:
        if "apply" in args:
            return subprocess.CompletedProcess(args, 1, "", "cannot apply")
        return execution.execute_command(args=args, cwd=cwd, timeout=timeout)

    plans = [
        stages.MutantPlan(
            mutant=Mutant(identifier=identifier, location=f"mutmut:{identifier}"),
            span=None,
            selected=[],
            key=f"key-{identifier}",
        )
        for identifier in ("pkg.x_f__mutmut_1", "pkg.x_f__mutmut_2")
    ]
    seen: list[tuple[str, bool]] = []

    results = pool.run_pending(
        execute=execute,
        target=target,
        plans=plans,
        workers=2,
        timeout=1.0,
        workspace=tmp_path,
        on_outcome=lambda *, identifier, outcome: seen.append((identifier, outcome.unapplied)),
    )

    assert sorted(seen) == [("pkg.x_f__mutmut_1", True), ("pkg.x_f__mutmut_2", True)]
    assert all(outcome.unapplied for outcome in results.values())
