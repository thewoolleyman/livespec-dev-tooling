"""Mutmut adapter for the portable Rule-26 mutation kill-matrix report.

The report model lives separately so other mutation engines can emit exactly
the same document.  This adapter uses only mutmut's public command-line
surface and runs no language model and no network service.  One run:

1. generates, measures and plans (see `mutation_kill_matrix_stages`): the
   mutant catalogue (generated only, never `mutmut run`), per-test coverage
   with the baseline failures it reveals, and each mutant's selected tests
   and cache key;
2. reuses every cached outcome whose inputs are unchanged (see
   `mutation_kill_matrix_cache`);
3. runs every other mutant in a worker's private copy of the target, all of
   its selected tests in one process, each keeping its own outcome (see
   `mutation_kill_matrix_pool` and `mutation_kill_matrix_execution`).

It writes the report, the cache, and, given a previous report, the
what-changed summary.  The target itself is never mutated.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from livespec_dev_tooling.mutation_kill_matrix import (
    MutationKillMatrixReport,
    RunMetadata,
    build_report,
    write_json,
    write_report,
)
from livespec_dev_tooling.mutation_kill_matrix_cache import CachedOutcome, load_cache, save_cache
from livespec_dev_tooling.mutation_kill_matrix_changes import build_changes
from livespec_dev_tooling.mutation_kill_matrix_execution import CommandExecutor, execute_command
from livespec_dev_tooling.mutation_kill_matrix_pool import run_pending
from livespec_dev_tooling.mutation_kill_matrix_selection import (
    COVERAGE_GUIDED_METHOD,
    FULL_MATRIX_METHOD,
)
from livespec_dev_tooling.mutation_kill_matrix_stages import (
    ENGINE_VERSION,
    MutantPlan,
    generate,
    measure,
    plan_mutants,
)

__all__: list[str] = [
    "CACHE_PATH",
    "CHANGES_PATH",
    "REPORT_PATH",
    "RunOptions",
    "execute_command",
    "main",
    "run_kill_matrix",
    "source_revision",
]


REPORT_PATH = Path("reports/mutation-kill-matrix.json")
CHANGES_PATH = Path("reports/mutation-kill-matrix-changes.json")
CACHE_PATH = Path("reports/mutation-kill-matrix-cache.json")
_DEFAULT_TIMEOUT_SECONDS = 60.0
_NO_APPLIED = (
    "no generated mutant could be applied: the applied mutant set is empty, "
    "so the kill matrix has nothing to attribute"
)


@dataclass(frozen=True, kw_only=True)
class RunOptions:
    """How one run is executed; none of these change the matrix content."""

    workers: int = 1
    per_test_timeout: float = _DEFAULT_TIMEOUT_SECONDS
    cache_path: Path | None = None
    previous_report: Path | None = None
    workspace: Path | None = None


def source_revision(*, target: Path) -> str:
    """Return the target's revision, or a useful value for a standalone fixture."""
    result = execute_command(args=["git", "rev-parse", "HEAD"], cwd=target)
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def _write_outputs(
    *,
    target: Path,
    report: MutationKillMatrixReport,
    plans: list[MutantPlan],
    outcomes: dict[str, CachedOutcome],
    options: RunOptions,
) -> None:
    """Write the report, the cache and, given a previous report, the summary."""
    write_report(report=report, path=target / REPORT_PATH)
    if options.cache_path is not None:
        save_cache(
            path=options.cache_path,
            entries={plan.key: outcomes[plan.mutant.identifier] for plan in plans},
        )
    if options.previous_report is not None:
        previous = json.loads(options.previous_report.read_text(encoding="utf-8"))
        write_json(
            document=build_changes(previous=previous, current=report.to_dict()),
            path=target / CHANGES_PATH,
        )


def run_kill_matrix(
    *,
    target: Path,
    source_revision: str,
    execute: CommandExecutor = execute_command,
    options: RunOptions | None = None,
) -> MutationKillMatrixReport:
    """Run each mutmut mutant against the tests that execute it and write one report."""
    options = options or RunOptions()
    generated, tests = generate(execute=execute, target=target)
    coverage, baseline_failures = measure(
        execute=execute, target=target, tests=tests, timeout=options.per_test_timeout
    )
    plans = plan_mutants(
        execute=execute,
        target=target,
        generated=generated,
        attributable=[test for test in tests if test not in baseline_failures],
        coverage=coverage,
        timeout=options.per_test_timeout,
    )
    cache = load_cache(path=options.cache_path)
    reused = {
        plan.mutant.identifier: cache[plan.key]
        for plan in plans
        if cache is not None and plan.key in cache
    }
    outcomes = reused | run_pending(
        execute=execute,
        target=target,
        plans=[plan for plan in plans if plan.mutant.identifier not in reused],
        workers=options.workers,
        timeout=options.per_test_timeout,
        workspace=options.workspace,
    )
    unapplied = frozenset(mutant for mutant, outcome in outcomes.items() if outcome.unapplied)
    if len(unapplied) == len(plans):
        raise RuntimeError(_NO_APPLIED)
    collected = set(tests)
    report = build_report(
        engine_name="mutmut",
        engine_version=ENGINE_VERSION,
        source_revision=source_revision,
        test_selection_method=FULL_MATRIX_METHOD if coverage is None else COVERAGE_GUIDED_METHOD,
        mutants=[plan.mutant for plan in plans],
        tests=tests,
        killers_by_mutant={
            mutant: set(outcome.killed_by) & collected for mutant, outcome in outcomes.items()
        },
        unapplied_mutants=unapplied,
        selected_for_unapplied=frozenset(
            test for plan in plans if plan.mutant.identifier in unapplied for test in plan.selected
        ),
        baseline_failures=baseline_failures,
        per_test_timeout_seconds=options.per_test_timeout,
        run=RunMetadata(
            workers=options.workers, incremental=cache is not None, reused_mutants=len(reused)
        ),
    )
    _write_outputs(target=target, report=report, plans=plans, outcomes=outcomes, options=options)
    return report


def _parser() -> argparse.ArgumentParser:
    """Describe the on-demand command line."""
    parser = argparse.ArgumentParser(description="Generate a Rule-26 mutation kill matrix.")
    _ = parser.add_argument(
        "target", type=Path, help="package root containing pyproject.toml and tests"
    )
    _ = parser.add_argument(
        "--workers",
        type=int,
        default=os.cpu_count() or 1,
        help="parallel workers (default: CPU count)",
    )
    _ = parser.add_argument(
        "--timeout",
        type=float,
        default=_DEFAULT_TIMEOUT_SECONDS,
        help="per-test timeout in seconds; a test that exceeds it against a mutant kills it",
    )
    _ = parser.add_argument(
        "--previous-report",
        type=Path,
        help="earlier report to write a what-changed summary against",
    )
    _ = parser.add_argument(
        "--cache", type=Path, help=f"result cache path (default: <target>/{CACHE_PATH})"
    )
    _ = parser.add_argument(
        "--no-cache", action="store_true", help="neither read nor write a cache"
    )
    _ = parser.add_argument(
        "--workspace",
        type=Path,
        help="directory for the worker trees (default: the system temp dir)",
    )
    return parser


def main(*, argv: list[str] | None = None) -> int:
    """Generate a Rule-26 report for the target package path supplied by just."""
    parser = _parser()
    arguments = parser.parse_args(argv)
    target = arguments.target.resolve()
    if not target.is_dir():
        parser.error(f"target package path is not a directory: {target}")
    if arguments.workers < 1:
        parser.error("--workers must be at least 1")
    previous = arguments.previous_report.resolve() if arguments.previous_report else None
    if previous is not None and not previous.is_file():
        parser.error(f"previous report is not a file: {previous}")
    options = RunOptions(
        workers=arguments.workers,
        per_test_timeout=arguments.timeout,
        cache_path=None if arguments.no_cache else (arguments.cache or target / CACHE_PATH),
        previous_report=previous,
        workspace=arguments.workspace,
    )
    try:
        _ = run_kill_matrix(
            target=target,
            source_revision=source_revision(target=target),
            execute=execute_command,
            options=options,
        )
    except RuntimeError as error:
        _ = sys.stderr.write(f"mutation-kill-matrix: {error}\n")
        return 1
    _ = sys.stdout.write(f"mutation-kill-matrix: wrote {target / REPORT_PATH}\n")
    _ = sys.stdout.write(
        "mutation-kill-matrix: no previous report given, so no what-changed summary was written\n"
        if previous is None
        else f"mutation-kill-matrix: wrote {target / CHANGES_PATH}\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
