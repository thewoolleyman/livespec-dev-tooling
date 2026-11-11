"""Suite-green leg helpers for `red_green_replay`.

The green-verified leg runs the staged tests for a test-only change, unless
shared test support changed; every other case runs the full pytest suite
inside the commit-msg hook. On a large suite a serial run takes tens of
minutes, so this helper module parallelizes it under pytest-xdist (worker count from the
`test_nprocs` env var when a justfile exports it, else the consumers'
lane-aware rule). Its sibling runner bounds local replay on progress: a
stall window renewed by every output chunk, plus an optional operator
ceiling, each of which kills the whole process group (xdist workers
included). The output checksum remains independent of line ordering and
run duration.

Split out of `_red_green_replay_modes.py` to keep that module under the
file-LLOC ceiling. The leading underscore marks a private sibling.
"""

from __future__ import annotations

import hashlib
import importlib.util
import os
import re
import sys
import time
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    import structlog.stdlib

# Make the script's own directory importable so the sibling `_*` modules
# resolve when this module is loaded standalone (the importlib test path).
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from _red_green_replay_pre_commit import (  # noqa: E402
    PreCommitAggregateEvidence,
    reuse_pre_commit_evidence,
    staged_tree_hash,
)
from _red_green_replay_suite_argv import lane_worker_count, visible_cpu_count  # noqa: E402
from _red_green_replay_suite_outcome import (  # noqa: E402
    SuiteOutcomeTools,
    finish_suite_run,
    run_suite_candidate,
)
from _red_green_replay_suite_runner import (  # noqa: E402
    CEILING_ENV,
    DEFAULT_STALL_SECONDS,
    STALL_ENV,
    SuiteBound,
    SuiteRun,
    run_suite,
    suite_bound,
)

from livespec_dev_tooling.commit_replay_delegate import run_replay  # noqa: E402
from livespec_dev_tooling.gate_outcome_telemetry import emit_suite_green_outcome  # noqa: E402
from livespec_dev_tooling.green_token import read_pre_commit_evidence  # noqa: E402

__all__: list[str] = [
    "CEILING_ENV",
    "DEFAULT_STALL_SECONDS",
    "STALL_ENV",
    "PreCommitAggregateEvidence",
    "SuiteBound",
    "SuiteRun",
    "_handle_suite_green_mode",
    "canonical_output_checksum",
    "handle_suite_green_mode",
    "has_shared_test_support",
    "run_suite",
    "staged_tree_hash",
    "stages_only_shared_test_support",
    "suite_bound",
    "suite_pytest_argv",
    "xdist_importable",
]

_NPROCS_ENV: str = "test_nprocs"

# Lines that vary with xdist scheduling or terminal progress, not with the
# suite's verdict: worker chatter, `created: N/N workers`, `N workers [M items]`
# and `....F..  [ 42%]` progress rows.
_NOISE_LINE = re.compile(
    "".join(
        (
            r"^(\[gw\d+\].*|created: \d+/\d+ workers?.*|\d+ workers? \[\d+ items?\].*",
            r"|[.FEsxXR]*\s*\[\s*\d+%\])$",
        )
    )
)
_DURATION = re.compile(r"\bin \d+(?:\.\d+)?s(?: \(\d+:\d{2}:\d{2}\))?")
_FAILED_SUMMARY_LINE = re.compile(r"^(?:FAILED|ERROR)\s+(\S+)", re.MULTILINE)
# One `--tb=line` traceback: `<path>.py:<line>: <exception text>`. Kept so a
# refused commit names WHY a test failed, not only which one did: a `--tb=no`
# run threw that text away (livespec-dev-tooling-ymjw5d).
_TRACEBACK_LINE = re.compile(r"^\S+\.py:\d+: .+$", re.MULTILINE)
_FAILURE_DETAIL_LIMIT = 4000


def suite_pytest_argv(
    *,
    environ: Mapping[str, str],
    test_paths: list[str] | None = None,
    xdist_available: bool,
    visible_cpus: int,
) -> list[str]:
    """Return pytest argv for the suite or the supplied staged test paths."""
    argv = [sys.executable, "-m", "pytest", "--tb=line", "-q"]
    if not xdist_available:
        return [*argv, *(test_paths or [])]
    nprocs = environ.get(_NPROCS_ENV, "").strip() or lane_worker_count(
        environ=environ, visible_cpus=visible_cpus
    )
    return [*argv, "-n", nprocs, *(test_paths or [])]


def xdist_importable() -> bool:
    """Return True iff pytest-xdist is importable under this interpreter."""
    return importlib.util.find_spec("xdist") is not None


def has_shared_test_support(*, staged_paths: list[str]) -> bool:
    """Return whether staged test material can affect tests it does not name.

    Files below ``tests/`` other than ``test_*.py`` modules are conservatively
    shared support, except Markdown documentation. That includes
    ``conftest.py``, package initializers, fixture modules, and fixture data;
    any can alter collection or behavior outside the named test files.
    """
    return any(
        path.startswith("tests/")
        and not (Path(path).suffix == ".py" and Path(path).name.startswith("test_"))
        and Path(path).suffix.lower() not in {".md", ".markdown"}
        for path in staged_paths
    )


def stages_only_shared_test_support(*, staged_paths: list[str], tests_paths: list[str]) -> bool:
    """Return whether shared test support is staged with no test module beside it.

    Such a staging has no test of its own to fail or pass (pytest exits 5), so
    it is never a Red: it is green-verified by the full suite it can affect.
    """
    return has_shared_test_support(staged_paths=staged_paths) and not any(
        Path(path).name.startswith("test_") for path in tests_paths
    )


def canonical_output_checksum(*, output: str) -> str:
    """Checksum the sorted set of non-noise lines, durations normalized.

    Two runs of the same green suite differ in line order (xdist), in
    progress rows, and in elapsed time; none of that may move the digest.
    The pytest summary line (`N passed, M skipped`) is kept, so a changed
    outcome count does.
    """
    lines = {
        _DURATION.sub("in <t>s", line.strip())
        for line in output.splitlines()
        if line.strip() and not _NOISE_LINE.match(line.strip())
    }
    canonical = "\n".join(sorted(lines))
    return f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


def _suite_failure_summary(*, output: str) -> str:
    """Return pytest failure node ids, falling back to the bounded output head."""
    failed_node_ids = _FAILED_SUMMARY_LINE.findall(output)
    if failed_node_ids:
        return " ".join(failed_node_ids)[:400]
    return " ".join(output.split())[:400]


def _suite_failure_detail(*, output: str) -> str:
    """Return each failing test's one-line traceback, bounded in size."""
    return "\n".join(_TRACEBACK_LINE.findall(output))[:_FAILURE_DETAIL_LIMIT]


def _suite_argv(*, test_paths: list[str] | None, log: structlog.stdlib.BoundLogger) -> list[str]:
    """Build the local suite command, recording the serial fallback when needed."""
    xdist_available = xdist_importable()
    if not xdist_available:
        log.warning(
            "suite-green-serial-fallback: pytest-xdist not importable; running the suite serially",
            check_id="red-green-replay-suite-green-serial-fallback",
            hint="Add pytest-xdist to this repo's dev dependencies to parallelize this leg.",
        )
    return suite_pytest_argv(
        environ=os.environ,
        test_paths=test_paths,
        xdist_available=xdist_available,
        visible_cpus=visible_cpu_count(
            affinity=getattr(os, "sched_getaffinity", None), cpu_count=os.cpu_count()
        ),
    )


def _suite_outcome_tools() -> SuiteOutcomeTools:
    """Bind the suite entry point's execution and refusal-description seams."""
    return SuiteOutcomeTools(
        canonical_output_checksum=canonical_output_checksum,
        failure_detail=_suite_failure_detail,
        failure_summary=_suite_failure_summary,
        run_local_suite=run_suite,
        run_replay=run_replay,
    )


def _suite_scope(
    *, staged_paths: list[str], tests_paths: list[str] | None
) -> tuple[str, list[str] | None]:
    """Select the narrow staged-test scope only when support is isolated."""
    run_touched_tests = bool(tests_paths) and not has_shared_test_support(staged_paths=staged_paths)
    return ("staged-tests", tests_paths) if run_touched_tests else ("full-suite", None)


def _handle_suite_green_mode(
    *,
    msg_path: Path,
    log: structlog.stdlib.BoundLogger,
    staged_paths: list[str],
    tests_paths: list[str] | None = None,
) -> int:
    """Green-verify a product/test change that carries no new failing test.

    The green-verified leg (user design correction 2026-06-11): a
    behavior-preserving product change runs the full pytest suite.
    A passing test-only cleanup runs only its staged test modules,
    unless shared support was staged, because support can affect
    tests the commit does not name. Exit 0 is the ONLY green outcome
    (pytest exit 5, zero tests collected, proves nothing and rejects).
    On green, the `TDD-Suite-Green-*` trailer shape (scope, output
    checksum, captured-at — mirroring the Red-leg evidence fields)
    lands in the commit message so the commit-range validation
    recognizes the commit as verified.
    """
    scope, selected_tests = _suite_scope(staged_paths=staged_paths, tests_paths=tests_paths)
    started = time.monotonic()
    index_tree = staged_tree_hash(cwd=Path.cwd())
    mode: str | None = None
    outcome: str | None = None
    exit_status = 1
    log.info(
        "suite-green-candidate: product/test change without a Red leg; selecting replay scope",
        check_id="red-green-replay-suite-green-candidate",
        staged_paths=staged_paths,
        tests_paths=selected_tests,
    )
    try:
        if scope == "full-suite" and reuse_pre_commit_evidence(
            evidence=read_pre_commit_evidence(cwd=Path.cwd()),
            index_tree=index_tree,
            log=log,
            msg_path=msg_path,
        ):
            mode = "reused"
            outcome = "green"
            exit_status = 0
        else:
            bound = suite_bound(environ=os.environ)
            argv = _suite_argv(test_paths=selected_tests, log=log)
            log.info(
                "suite-green-argv: pytest invocation",
                check_id="red-green-replay-suite-green-argv",
                argv=argv,
                scope=scope,
                stall_seconds=bound.stall_seconds,
                ceiling_seconds=bound.ceiling_seconds,
            )
            tools = _suite_outcome_tools()
            run = run_suite_candidate(
                argv=argv,
                bound=bound,
                log=log,
                tools=tools,
            )
            mode = "ran"
            outcome = finish_suite_run(
                run=run,
                bound=bound,
                log=log,
                msg_path=msg_path,
                scope=scope,
                tools=tools,
            )
            exit_status = 0 if outcome == "green" else 1
    except SystemExit:
        outcome = "red"
        raise
    else:
        return exit_status
    finally:
        emit_suite_green_outcome(
            cwd=str(Path.cwd()),
            tree_hash=index_tree,
            mode=mode,
            scope=scope,
            outcome=outcome,
            duration_seconds=time.monotonic() - started,
        )


handle_suite_green_mode = _handle_suite_green_mode
