"""The Rule-26 kill matrix's worker pool: every pending mutant, across isolated trees.

Each worker owns a private copy of the target (see
`mutation_kill_matrix_execution.make_worker_tree`), takes mutants from one
shared queue (one `None` per worker ends it), restores its tree before each
one, applies it with `mutmut apply`, and runs the mutant's selected tests in
one process.  A mutant mutmut cannot apply is recorded as unapplied.  A
worker's error is re-raised on the calling thread, so a broken worker fails
the run instead of thinning it.
"""

from __future__ import annotations

import queue
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from livespec_dev_tooling.mutation_kill_matrix_cache import CachedOutcome
from livespec_dev_tooling.mutation_kill_matrix_execution import (
    PYTHON,
    CommandExecutor,
    WorkerTree,
    import_roots,
    make_worker_tree,
    run_selected,
)
from livespec_dev_tooling.mutation_kill_matrix_stages import MutantPlan

__all__: list[str] = [
    "run_pending",
]


def _work(
    *,
    execute: CommandExecutor,
    tree: WorkerTree,
    pending: queue.SimpleQueue[MutantPlan | None],
    timeout: float,
) -> dict[str, CachedOutcome]:
    """Apply each queued mutant in this worker's own tree and record its outcome."""
    snapshot = {
        path: path.read_bytes()
        for path in tree.root.rglob("*.py")
        if "mutants" not in path.relative_to(tree.root).parts
    }
    results: dict[str, CachedOutcome] = {}
    while (plan := pending.get()) is not None:
        for path, content in snapshot.items():
            _ = path.write_bytes(content)
        applied = execute(
            args=[
                "env",
                *tree.environment,
                *PYTHON,
                "-m",
                "mutmut",
                "apply",
                plan.mutant.identifier,
            ],
            cwd=tree.root,
        )
        if applied.returncode != 0:
            results[plan.mutant.identifier] = CachedOutcome(unapplied=True, killed_by=())
            continue
        outcomes = run_selected(execute=execute, tree=tree, tests=plan.selected, timeout=timeout)
        results[plan.mutant.identifier] = CachedOutcome(
            unapplied=False,
            killed_by=tuple(sorted(test for test, failed in outcomes.items() if failed)),
        )
    return results


def run_pending(
    *,
    execute: CommandExecutor,
    target: Path,
    plans: list[MutantPlan],
    workers: int,
    timeout: float,
    workspace: Path | None,
) -> dict[str, CachedOutcome]:
    """Run every pending mutant across `workers` isolated worker trees."""
    if not plans:
        return {}
    count = max(1, min(workers, len(plans)))
    roots = import_roots(execute=execute, target=target)
    modules = {plan.mutant.identifier.rpartition(".")[0].split(".")[0] for plan in plans}
    pending: queue.SimpleQueue[MutantPlan | None] = queue.SimpleQueue()
    for plan in plans:
        pending.put(plan)
    for _ in range(count):
        pending.put(None)
    with tempfile.TemporaryDirectory(prefix="kill-matrix-workers-", dir=workspace) as scratch:
        trees = [
            make_worker_tree(
                execute=execute,
                target=target,
                workspace=Path(scratch),
                index=index,
                roots=roots,
                modules=modules,
            )
            for index in range(count)
        ]
        with ThreadPoolExecutor(max_workers=count) as pool:
            futures = [
                pool.submit(_work, execute=execute, tree=tree, pending=pending, timeout=timeout)
                for tree in trees
            ]
            results: dict[str, CachedOutcome] = {}
            for future in futures:
                results |= future.result()
    return results
