"""parallel_check_dispatcher — run just-check targets concurrently.

Replaces the serial for-loop in the check: justfile recipe with
concurrent subprocess dispatch. Independent targets run at up to
--workers concurrency.

Coverage-data isolation by construction (work-item
livespec-dev-tooling-cmn)
--------------------------------------------------------------------
Several check targets run a coverage-instrumented pytest. Under
`pytest --cov`, coverage's `.pth` startup hook sets
`COVERAGE_PROCESS_START` in the environment, so any python subprocess a
test spawns SELF-instruments and writes a `.coverage.*` parallel data
file. `pytest -n auto --cov` then runs `coverage combine`, which GLOBS
and ERASES every `.coverage*` file beside the data file. Run two
coverage-touching targets concurrently against the SAME directory and
one target's combine sweeps the other target's (or its subprocess
child's) data file mid-run — intermittently emptying it and producing a
flaky "No data to report" red.

The previous fix was a hand-enumerated `_ARTIFACT_PREREQS` edge list:
every newly-discovered collision pair was serialized by hand. That
list rots — the collisions you forget to enumerate become production
flakes. This dispatcher instead makes collisions STRUCTURALLY
IMPOSSIBLE: each coverage namespace gets its OWN isolated filesystem
context (a unique temp dir exported as `COVERAGE_FILE` + `TMPDIR` to the
target's `just` subprocess). A `COVERAGE_PROCESS_START` child inherits
that `COVERAGE_FILE` location, so the subprocess case is fixed for free
WITHOUT banning subprocesses; a target's `coverage combine` can only
glob its OWN namespace dir, so it can never erase another namespace's
data. `TMPDIR` isolation extends the same guarantee to any other
shared-temp collision not yet discovered.

`COVERAGE_NAMESPACES` (in `_dispatcher_coverage_namespaces`) maps each coverage-touching target to a
namespace key. Targets that share a key share one isolated dir (a
producer and the consumer that reads its data file); targets with
distinct keys are fully isolated and run concurrently with no edge.

`COVERAGE_CONSUMERS` (in the same module) carries the only ordering that survives: a
GENUINE read-after-write DATA dependency, where a consumer reads the
data file a producer wrote into their shared namespace dir. This is NOT
a collision-avoidance edge (those are retired) — the consumer needs the
producer's bytes, so it runs only after the producer completes (the
shared runner holds the consumer until its producer has exited 0).

CLI:
    python -m livespec_dev_tooling.parallel_check_dispatcher
        [--workers N] [--skip SPACE_SEP_LIST] [--] TARGET ...

    --workers N       Max concurrent just-target subprocesses, bounded by
                      the CPUs the process may use. Default: the CPUs the
                      process may use (cgroup cpu.max quota, else affinity
                      mask), capped at 8.
    --skip LIST       Space-separated list of targets to skip.
    TARGET ...        Ordered target list (positional, after optional --).

Exit 0: all non-skipped targets passed. Exit 1: one or more failed.

Every target is launched by the shared runner in `_check_target_runner`, the
same one the expedited incident paths use (livespec-dev-tooling-oqpw6t): stdin
closed and output spooled to a temporary file. This dispatcher passes no
deadline, so a target stays in this process's group, a group kill still takes
it, and it runs to completion however long it takes.

Output:
    Human-readable per-target headers + captured output on stdout.
    Machine-readable per-target timing events on stderr (structlog JSON)
    for e60 observability.
"""

from __future__ import annotations

import functools
import os
import sys
from pathlib import Path
from typing import cast

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

from livespec_dev_tooling._check_target_runner import (  # noqa: E402
    BLOCKED,
    TargetOutcome,
    TargetRun,
    cap_workers,
    run_targets,
)
from livespec_dev_tooling._dispatcher_coverage_namespaces import (  # noqa: E402
    COVERAGE_CONSUMERS,
    isolated_environments,
)
from livespec_dev_tooling._pyright_warmup import warm_locked_pyright  # noqa: E402
from livespec_dev_tooling.allowed_cpus import current_allowed_cpu_count  # noqa: E402
from livespec_dev_tooling.check_failure_digest import (  # noqa: E402
    failure_digest_lines,
)
from livespec_dev_tooling.parallel_check_dispatcher_cli import parse_args  # noqa: E402

__all__: list[str] = []


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


def _as_result(*, outcome: TargetOutcome) -> TargetResult:
    """Project the shared runner's outcome onto this dispatcher's result shape.

    A consumer whose data producer failed is reported skipped with exit 1, as
    before. With no deadline a target always yields a measured return code, so
    the fallback 1 applies only to the blocked case.
    """
    return TargetResult(
        name=outcome.name,
        skipped=outcome.status == BLOCKED,
        exit_code=1 if outcome.returncode is None else outcome.returncode,
        wall_time_s=outcome.wall_time_s,
        output=outcome.output,
    )


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


def _emit_outcome(*, outcome: TargetOutcome, log: structlog.stdlib.BoundLogger) -> None:
    """Emit one target's result as the shared runner reports it complete."""
    _emit_result(result=_as_result(outcome=outcome), log=log)


def _write_timing_table(*, results: list[TargetResult]) -> None:
    """Write the per-target wall-time table (longest first) for e60 observability."""
    _write(text="\nper-target wall times (longest first):\n")
    for r in sorted(results, key=lambda x: x.wall_time_s, reverse=True):
        if not r.skipped:
            _write(text=f"  {r.wall_time_s:6.1f}s  {r.name}\n")


def _write_failure_digest(*, failed: list[TargetResult]) -> None:
    """Restate the failed targets' failure modes and remedies as the LAST lines.

    Written AFTER the `check_aggregate_failed` log record, which structlog
    sends to stderr, so on a merged terminal the digest is genuinely the tail
    — which is the whole point. A pre-push hook that streams 313 seconds of
    output and then exits 1 has already scrolled the finding that explains the
    failure off the screen (measured 2026-08-20, `worktree_pack_absent`), and
    the remedy is only useful where the operator is still looking.
    """
    for line in failure_digest_lines(failures=[(r.name, r.output) for r in failed]):
        _write(text=f"{line}\n")


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
        _write_failure_digest(failed=failed)
        return 1
    _write(text=f"\nAll {len(passed)} targets passed.\n")
    log.info("check_aggregate_passed", passed=len(passed))
    return 0


def _run_all(
    *,
    targets: list[str],
    skip_set: frozenset[str],
    max_workers: int,
    cwd: Path,
    log: structlog.stdlib.BoundLogger,
) -> list[TargetResult]:
    """Run every target through the shared runner; return results in target order."""
    # Each coverage namespace gets its own isolated COVERAGE_FILE + TMPDIR, and
    # a consumer in `COVERAGE_CONSUMERS` waits for its producer (the
    # read-after-write data dependency); every other target, including every
    # coverage producer and the independent incremental gate, starts at once.
    names = [name for name in targets if name not in skip_set]
    with isolated_environments(names=names, base=None) as environments:
        outcomes = run_targets(
            runs=[
                TargetRun(
                    name=name,
                    argv=("just", name),
                    env=environments[name],
                    after=COVERAGE_CONSUMERS.get(name),
                )
                for name in names
            ],
            cwd=cwd,
            max_workers=max_workers,
            on_complete=functools.partial(_emit_outcome, log=log),
        )
    ran = {outcome.name: _as_result(outcome=outcome) for outcome in outcomes}
    results = [
        TargetResult(name=name, skipped=True, exit_code=0, wall_time_s=0.0, output="")
        if name in skip_set
        else ran[name]
        for name in targets
    ]
    return results


def main() -> int:
    log = _configure_logger()
    args = parse_args()
    skip_str: str = cast(str, args.skip)
    skip_set: frozenset[str] = frozenset(skip_str.split())
    max_workers = cap_workers(
        requested=cast(int | None, args.workers), allowed=current_allowed_cpu_count()
    )
    cwd = Path.cwd()
    already_warmed = os.environ.pop("LIVESPEC_PYRIGHT_WARMED", None) == "1"
    log.info(
        "parallel_check_dispatcher_starting",
        targets=len(cast(list[str], args.targets)),
        workers=max_workers,
        skip=list(skip_set),
    )
    if warm_locked_pyright(cwd=cwd, already_warmed=already_warmed) != 0:
        _write(text="ERROR: pyright provisioning failed; no check target started.\n")
        return 1
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
