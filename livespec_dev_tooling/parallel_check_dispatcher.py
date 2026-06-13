"""parallel_check_dispatcher — run just-check targets concurrently.

Replaces the serial for-loop in the check: justfile recipe with
concurrent subprocess dispatch. Independent targets run at up to
--workers concurrency; dependency edges for shared on-disk artifacts
are enforced so dependent targets never start before their prerequisite.

Dependency edges (shared on-disk artifacts):
  check-coverage → check-per-file-coverage
    check-per-file-coverage writes the .coverage data file; check-coverage
    reads it. Never run them concurrently; check-coverage is scheduled
    via a deferred runner that blocks until check-per-file-coverage
    completes. Any other shared-artifact pairs found in the future should
    be added to _ARTIFACT_PREREQS with a comment naming the shared file.

CLI:
    python -m livespec_dev_tooling.parallel_check_dispatcher
        [--workers N] [--skip SPACE_SEP_LIST] [--] TARGET ...

    --workers N       Max concurrent just-target subprocesses.
                      Default: min(cpu_count, 8).
    --skip LIST       Space-separated list of targets to skip.
    TARGET ...        Ordered target list (positional, after optional --).

Exit 0: all non-skipped targets passed. Exit 1: one or more failed.

Output:
    Human-readable per-target headers + captured output on stdout.
    Machine-readable per-target timing events on stderr (structlog JSON)
    for e60 observability.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import cast

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

__all__: list[str] = []

_DEFAULT_MAX_WORKERS: int = 8

# Shared on-disk artifact dependency edges.
# Format: dependent_target -> prerequisite_target.
# check-coverage reads the .coverage file that check-per-file-coverage writes;
# never schedule them concurrently; check-coverage runs only after the prereq
# completes (the deferred runner blocks on prereq_fut.result()).
#
# check-check-coverage-incremental runs its OWN coverage-instrumented pytest
# (writing .coverage.check-coverage-incremental) and then `coverage report`
# against that data file. A concurrent check-per-file-coverage
# (`pytest -n auto --cov`) runs `coverage combine`, which globs and erases
# `.coverage*` data files in the repo root — including the incremental gate's
# file. Run concurrently they race and the incremental gate intermittently
# reports "No data to report" and hard-fails. Serialize it after
# per-file-coverage (same edge as check-coverage) so there is no concurrent
# coverage writer when the incremental gate reads its data file. The double
# `check-` prefix is the real aggregate target name (the recipe is
# `check-check-coverage-incremental`), which is what the dispatcher schedules.
_ARTIFACT_PREREQS: dict[str, str] = {
    "check-coverage": "check-per-file-coverage",
    "check-check-coverage-incremental": "check-per-file-coverage",
}


class TargetResult:
    """Result of running (or skipping) a single just-check target."""

    def __init__(
        self,
        *,
        name: str,
        skipped: bool,
        exit_code: int,
        wall_time_s: float,
        output: str,
    ) -> None:
        self.name = name
        self.skipped = skipped
        self.exit_code = exit_code
        self.wall_time_s = wall_time_s
        self.output = output


def _configure_logger() -> structlog.stdlib.BoundLogger:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    return structlog.get_logger("parallel_check_dispatcher")


def _cap_workers(*, requested: int | None) -> int:
    """Return the effective worker count: min(cpu_count, requested or DEFAULT)."""
    cap = requested if requested is not None else _DEFAULT_MAX_WORKERS
    return max(1, min(os.cpu_count() or 1, cap))


def _run_one(*, name: str, cwd: Path) -> TargetResult:
    """Invoke `just <name>` and return a TargetResult with timing and output."""
    start = time.monotonic()
    completed = subprocess.run(  # noqa: S603
        ["just", name],  # noqa: S607
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    elapsed = time.monotonic() - start
    return TargetResult(
        name=name,
        skipped=False,
        exit_code=completed.returncode,
        wall_time_s=elapsed,
        output=completed.stdout,
    )


def _deferred_run(*, name: str, prereq_fut: Future[TargetResult], cwd: Path) -> TargetResult:
    """Wait for prereq_fut, then run name — or mark it blocked if prereq failed."""
    prereq = prereq_fut.result()
    if prereq.exit_code != 0:
        return TargetResult(
            name=name,
            skipped=True,
            exit_code=1,
            wall_time_s=0.0,
            output=f"BLOCKED: prereq '{prereq.name}' failed (exit {prereq.exit_code})",
        )
    return _run_one(name=name, cwd=cwd)


def _write(*, text: str) -> None:
    """Write text to stdout and flush; discards the byte-count return value."""
    _ = sys.stdout.write(text)
    _ = sys.stdout.flush()


def _emit_result(*, result: TargetResult, log: structlog.stdlib.BoundLogger) -> None:
    """Write the per-target header + captured output to stdout; log timing to stderr."""
    if result.skipped:
        _write(text=f"\n::: just {result.name} (skipped)\n")
        return
    status = "FAILED" if result.exit_code != 0 else "ok"
    _write(text=f"\n::: just {result.name} [{status}, wall: {result.wall_time_s:.1f}s]\n")
    if result.output:
        _write(text=result.output)
    log.info(
        "target_completed",
        target=result.name,
        exit_code=result.exit_code,
        wall_s=round(result.wall_time_s, 3),
    )


def _write_timing_table(*, results: list[TargetResult]) -> None:
    """Write the per-target wall-time table (longest first) for e60 observability."""
    _write(text="\nper-target wall times (longest first):\n")
    for r in sorted(results, key=lambda x: x.wall_time_s, reverse=True):
        if not r.skipped:
            _write(text=f"  {r.wall_time_s:6.1f}s  {r.name}\n")


def _emit_summary(*, results: list[TargetResult], log: structlog.stdlib.BoundLogger) -> int:
    """Write timing summary to stdout; return 0 if all passed, 1 if any failed."""
    passed = [r for r in results if not r.skipped and r.exit_code == 0]
    failed = [r for r in results if not r.skipped and r.exit_code != 0]
    skipped = [r for r in results if r.skipped]
    counts = f"passed: {len(passed)}, failed: {len(failed)}, skipped: {len(skipped)}"
    _write(text=f"\n--- parallel check summary ---\n{counts}\n")
    _write_timing_table(results=results)
    if failed:
        _write(text=f"\nFailed targets ({len(failed)}):\n")
        for r in failed:
            _write(text=f"  - {r.name}\n")
        log.error("check_aggregate_failed", failed=[r.name for r in failed])
        return 1
    _write(text=f"\nAll {len(passed)} targets passed.\n")
    log.info("check_aggregate_passed", passed=len(passed))
    return 0


def _collect_ordered_results(
    *,
    targets: list[str],
    skip_set: frozenset[str],
    futures: dict[str, Future[TargetResult]],
) -> list[TargetResult]:
    """Return results in original target order (all futures are done by this point)."""
    results: list[TargetResult] = []
    for name in targets:
        if name in skip_set:
            results.append(
                TargetResult(name=name, skipped=True, exit_code=0, wall_time_s=0.0, output="")
            )
        else:
            results.append(futures[name].result())
    return results


def _run_all(
    *,
    targets: list[str],
    skip_set: frozenset[str],
    max_workers: int,
    cwd: Path,
    log: structlog.stdlib.BoundLogger,
) -> list[TargetResult]:
    """Submit all targets to the thread pool and collect results as they complete."""
    futures: dict[str, Future[TargetResult]] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        for name in targets:
            if name in skip_set:
                continue
            prereq = _ARTIFACT_PREREQS.get(name)
            if prereq is not None and prereq in futures:
                futures[name] = pool.submit(
                    _deferred_run, name=name, prereq_fut=futures[prereq], cwd=cwd
                )
            else:
                futures[name] = pool.submit(_run_one, name=name, cwd=cwd)
        for fut in as_completed(futures.values()):
            _emit_result(result=fut.result(), log=log)
    return _collect_ordered_results(targets=targets, skip_set=skip_set, futures=futures)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Parallel just-check dispatcher with core-budget cap."
    )
    _ = parser.add_argument("--workers", type=int, default=None, help="Max concurrent targets.")
    _ = parser.add_argument("--skip", type=str, default="", help="Space-separated skip list.")
    _ = parser.add_argument("targets", nargs="*", help="Ordered target list.")
    return parser.parse_args()


def main() -> int:
    log = _configure_logger()
    args = _parse_args()
    skip_str: str = cast(str, args.skip)
    skip_set: frozenset[str] = frozenset(skip_str.split())
    max_workers = _cap_workers(requested=cast(int | None, args.workers))
    cwd = Path.cwd()
    log.info(
        "parallel_check_dispatcher_starting",
        targets=len(cast(list[str], args.targets)),
        workers=max_workers,
        skip=list(skip_set),
    )
    results = _run_all(
        targets=cast(list[str], args.targets),
        skip_set=skip_set,
        max_workers=max_workers,
        cwd=cwd,
        log=log,
    )
    return _emit_summary(results=results, log=log)


if __name__ == "__main__":
    raise SystemExit(main())
