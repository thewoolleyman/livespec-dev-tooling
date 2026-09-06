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

`_COVERAGE_NAMESPACES` maps each coverage-touching target to a
namespace key. Targets that share a key share one isolated dir (a
producer and the consumer that reads its data file); targets with
distinct keys are fully isolated and run concurrently with no edge.

`_COVERAGE_CONSUMERS` carries the only ordering that survives: a
GENUINE read-after-write DATA dependency, where a consumer reads the
data file a producer wrote into their shared namespace dir. This is NOT
a collision-avoidance edge (those are retired) — the consumer needs the
producer's bytes, so it runs only after the producer completes (the
deferred runner blocks on the producer future).

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
    On failure the LAST lines are the failure-mode digest: each failing
    target's own `failure_mode` records re-printed with the remedy the
    emitting check composed (`check_failure_digest`, work-item
    livespec-dev-tooling-b7dbne), so a self-describing failure survives
    an aggregate long enough to scroll it away.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import cast

from livespec_dev_tooling.check_failure_digest import (
    collect_failure_findings,
    render_failure_digest,
)

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

__all__: list[str] = []

_DEFAULT_MAX_WORKERS: int = 8

# Coverage-namespace assignment (work-item livespec-dev-tooling-cmn).
# Each coverage-touching target is mapped to a namespace key. The
# dispatcher mints ONE unique temp dir per distinct key and exports it
# to the target's `just` subprocess as both COVERAGE_FILE (so pytest-cov
# and its COVERAGE_PROCESS_START children write there) and TMPDIR (so
# any other shared-temp artifact is isolated too). Targets NOT listed
# here run with the inherited environment unchanged.
#
# Targets that share a key share one dir: that is the producer/consumer
# coverage pair below. Distinct keys are fully isolated — their
# `coverage combine` can only glob their own dir, so cross-namespace
# data-file erasure is structurally impossible (no hand-enumerated edge
# needed). This RETIRES the former collision edge that serialized
# check-check-coverage-incremental after check-per-file-coverage: the
# incremental gate now owns its own namespace and runs fully concurrent.
_COVERAGE_NAMESPACES: dict[str, str] = {
    # The full-tree coverage pair shares one data file: per-file-coverage
    # PRODUCES it (runs `pytest -n auto --cov`), check-coverage CONSUMES
    # it (runs `coverage report` against the same file). Same namespace ->
    # same isolated COVERAGE_FILE.
    "check-per-file-coverage": "full-tree",
    "check-coverage": "full-tree",
    # The path-scoped incremental gate runs its OWN coverage-instrumented
    # pytest. Its own namespace isolates its data file from the full-tree
    # pair's `coverage combine`, so it no longer needs to be serialized
    # after per-file-coverage (the retired 7us.6 collision edge).
    "check-check-coverage-incremental": "incremental",
}

# Genuine read-after-write DATA dependencies (consumer -> producer).
# The consumer reads the producer's isolated COVERAGE_FILE, so it must
# start only after the producer has finished writing it. This is the
# ONLY ordering edge that survives the isolation redesign; it is data
# flow, not collision avoidance. Both endpoints MUST share a namespace
# in _COVERAGE_NAMESPACES (they read/write the same file).
_COVERAGE_CONSUMERS: dict[str, str] = {
    "check-coverage": "check-per-file-coverage",
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


def _build_namespace_dirs(
    *, targets: list[str], skip_set: frozenset[str], root: Path
) -> dict[str, Path]:
    """Mint one isolated coverage dir per distinct namespace key in play.

    Walks the non-skipped targets, collects the distinct namespace keys
    they map to via `_COVERAGE_NAMESPACES`, and creates one fresh temp
    directory per key under `root` (each with a `tmp/` subdir for the
    target's TMPDIR). Returns a key -> dir mapping. Targets that share a
    key (the producer/consumer coverage pair) resolve to the same dir, so
    the consumer reads the producer's COVERAGE_FILE; targets with
    distinct keys get separate dirs and can never erase each other's
    data via `coverage combine`.

    `root` MUST be OUTSIDE the governed repo (the system temp dir): the
    per-target TMPDIR points into these dirs, and pytest's `tmp_path`
    fixture derives from TMPDIR — a TMPDIR inside the repo's git worktree
    breaks tests that assume `tmp_path` is not within any git repo.
    """
    keys = {
        _COVERAGE_NAMESPACES[name]
        for name in targets
        if name not in skip_set and name in _COVERAGE_NAMESPACES
    }
    dirs: dict[str, Path] = {}
    for key in sorted(keys):
        ns_dir = Path(tempfile.mkdtemp(prefix=f"covns-{key}-", dir=str(root)))
        (ns_dir / "tmp").mkdir(exist_ok=True)
        dirs[key] = ns_dir
    return dirs


def _target_env(*, name: str, namespace_dirs: dict[str, Path]) -> dict[str, str] | None:
    """Return the isolated env for a coverage-touching target, else None.

    For a target mapped to a coverage namespace, returns a COPY of the
    process environment with COVERAGE_FILE pointed at `<ns_dir>/.coverage`
    and TMPDIR pointed at `<ns_dir>/tmp`. A COVERAGE_PROCESS_START child
    spawned by the target inherits this COVERAGE_FILE, so its data lands
    in the same isolated dir. Returns None for non-coverage targets (the
    subprocess then inherits the parent env unchanged).
    """
    key = _COVERAGE_NAMESPACES.get(name)
    if key is None:
        return None
    ns_dir = namespace_dirs[key]
    env = dict(os.environ)
    env["COVERAGE_FILE"] = str(ns_dir / ".coverage")
    env["TMPDIR"] = str(ns_dir / "tmp")
    return env


def _run_one(*, name: str, cwd: Path, env: dict[str, str] | None) -> TargetResult:
    """Invoke `just <name>` and return a TargetResult with timing and output.

    When `env` is provided it fully replaces the subprocess environment
    (the caller passes a COPY of os.environ with the isolated coverage
    vars overlaid); when None the subprocess inherits the parent env.
    """
    start = time.monotonic()
    completed = subprocess.run(  # noqa: S603
        ["just", name],  # noqa: S607
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
        env=env,
    )
    elapsed = time.monotonic() - start
    return TargetResult(
        name=name,
        skipped=False,
        exit_code=completed.returncode,
        wall_time_s=elapsed,
        output=completed.stdout,
    )


def _deferred_run(
    *, name: str, prereq_fut: Future[TargetResult], cwd: Path, env: dict[str, str] | None
) -> TargetResult:
    """Wait for prereq_fut, then run name — or mark it blocked if prereq failed.

    Used only for a genuine read-after-write DATA dependency (the
    coverage consumer reading the producer's isolated COVERAGE_FILE): the
    consumer cannot start until the producer has written the file it
    reads.
    """
    prereq = prereq_fut.result()
    if prereq.exit_code != 0:
        return TargetResult(
            name=name,
            skipped=True,
            exit_code=1,
            wall_time_s=0.0,
            output=f"BLOCKED: prereq '{prereq.name}' failed (exit {prereq.exit_code})",
        )
    return _run_one(name=name, cwd=cwd, env=env)


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


def _write_failure_digest(*, failed: list[TargetResult]) -> None:
    """Re-print the failing targets' own findings as the aggregate's LAST lines.

    Work-item livespec-dev-tooling-b7dbne. The list of failed target NAMES used
    to be the tail, and a name is not a diagnosis: the `worktree_pack_absent`
    finding that says exactly what to run had scrolled off 313 seconds earlier,
    so the pre-push hook read as a bare `exit status 1`. Both hook aggregates
    reach here — pre-push and pre-commit each delegate to the bare `check`
    recipe this dispatcher backs — so one tail serves both.

    A target that failed WITHOUT emitting a structured record adds nothing and
    the digest stays empty; its captured output above is still the only account
    of it there is.
    """
    findings = [
        finding
        for result in failed
        for finding in collect_failure_findings(target=result.name, output=result.output)
    ]
    _write(text=render_failure_digest(findings=findings))


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


def _submit_target(
    *,
    name: str,
    pool: ThreadPoolExecutor,
    futures: dict[str, Future[TargetResult]],
    namespace_dirs: dict[str, Path],
    cwd: Path,
) -> Future[TargetResult]:
    """Submit one target, deferring it after its data-producer when one applies.

    A target named in `_COVERAGE_CONSUMERS` whose producer is already
    submitted is deferred until the producer future resolves (the
    read-after-write data dependency). Every other target — including
    every coverage producer and the now-independent incremental gate —
    runs immediately with its isolated coverage env.
    """
    env = _target_env(name=name, namespace_dirs=namespace_dirs)
    producer = _COVERAGE_CONSUMERS.get(name)
    if producer is not None and producer in futures:
        return pool.submit(_deferred_run, name=name, prereq_fut=futures[producer], cwd=cwd, env=env)
    return pool.submit(_run_one, name=name, cwd=cwd, env=env)


def _run_all(
    *,
    targets: list[str],
    skip_set: frozenset[str],
    max_workers: int,
    cwd: Path,
    log: structlog.stdlib.BoundLogger,
) -> list[TargetResult]:
    """Submit all targets to the thread pool and collect results as they complete."""
    # Mint the isolated coverage/TMPDIR dirs in the system temp dir
    # (OUTSIDE the governed repo), never under cwd: pytest's `tmp_path`
    # derives from the per-target TMPDIR, and a TMPDIR inside the repo's
    # git worktree breaks tests that assume `tmp_path` is not in a repo.
    namespace_dirs = _build_namespace_dirs(
        targets=targets, skip_set=skip_set, root=Path(tempfile.gettempdir())
    )
    futures: dict[str, Future[TargetResult]] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        for name in targets:
            if name in skip_set:
                continue
            futures[name] = _submit_target(
                name=name, pool=pool, futures=futures, namespace_dirs=namespace_dirs, cwd=cwd
            )
        for fut in as_completed(futures.values()):
            _emit_result(result=fut.result(), log=log)
    results = _collect_ordered_results(targets=targets, skip_set=skip_set, futures=futures)
    # All futures are done: the isolated coverage/TMPDIR dirs are no
    # longer needed (the consumer has already read the producer's data).
    # Best-effort removal so the system temp dir does not accumulate one
    # covns-* tree per `just check` run; ignore_errors keeps a transient
    # removal failure from masking the real check result.
    for ns_dir in namespace_dirs.values():
        shutil.rmtree(ns_dir, ignore_errors=True)
    return results


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
