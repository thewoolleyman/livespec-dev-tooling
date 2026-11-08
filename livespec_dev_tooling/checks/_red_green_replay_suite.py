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

import datetime
import hashlib
import importlib.util
import os
import re
import sys
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
from _red_green_replay_protocol import RED_GREEN_REPLAY_PROTOCOL  # noqa: E402
from _red_green_replay_suite_argv import lane_worker_count, visible_cpu_count  # noqa: E402
from _red_green_replay_suite_runner import (  # noqa: E402
    CEILING_ENV,
    DEFAULT_STALL_SECONDS,
    STALL_ENV,
    SuiteBound,
    SuiteRun,
    run_suite,
    suite_bound,
    test_completion_summary,
)
from _red_green_replay_trailers import write_trailers  # noqa: E402

from livespec_dev_tooling.commit_replay_delegate import run_replay  # noqa: E402
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
    run_touched_tests = bool(tests_paths) and not has_shared_test_support(staged_paths=staged_paths)
    selected_tests = tests_paths if run_touched_tests else None
    scope = "staged-tests" if run_touched_tests else "full-suite"
    log.info(
        "suite-green-candidate: product/test change without a Red leg; selecting replay scope",
        check_id="red-green-replay-suite-green-candidate",
        staged_paths=staged_paths,
        tests_paths=selected_tests,
    )
    if scope == "full-suite" and reuse_pre_commit_evidence(
        evidence=read_pre_commit_evidence(cwd=Path.cwd()),
        index_tree=staged_tree_hash(cwd=Path.cwd()),
        log=log,
        msg_path=msg_path,
    ):
        return 0
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
    verdict = run_replay(repo_root=Path.cwd(), pytest_argv=["pytest", *argv[3:]])
    if (
        not verdict.local
        and verdict.exit_status is not None
        and verdict.job_name is not None
        and verdict.tree_hash is not None
        and verdict.output_checksum is not None
    ):
        suite_result = SuiteRun(
            returncode=verdict.exit_status,
            output=verdict.reason,
            timed_out=False,
        )
        output_checksum = verdict.output_checksum
        gate_trailers = (
            ("TDD-Suite-Green-Gate-Job", verdict.job_name),
            ("TDD-Suite-Green-Staged-Tree", verdict.tree_hash),
        )
        log.info(
            "commit-time replay gated by a gate Job",
            check_id="red-green-replay-delegated",
            job_name=verdict.job_name,
            tree_hash=verdict.tree_hash,
        )
    else:
        suite_result = run_suite(argv=argv, bound=bound)
        output_checksum = canonical_output_checksum(output=suite_result.output)
        gate_trailers: tuple[tuple[str, str], ...] = ()
        log.info(
            "commit-time replay gated locally",
            check_id="red-green-replay-gated-locally",
            reason=verdict.reason,
        )
    if suite_result.timed_out:
        timeout_message = (
            f"suite-green-timeout: the suite-green leg was killed ({suite_result.kill_reason}): "
            f"its stall window is {bound.stall_seconds}s with no new output ({STALL_ENV}) "
            f"and its total ceiling is {bound.ceiling_seconds or 'unset'} ({CEILING_ENV}); "
            f"{test_completion_summary(output=suite_result.output)}; "
            "the pytest process group was killed"
        )
        log.error(
            timeout_message,
            check_id="red-green-replay-suite-green-timeout",
            leg="suite-green",
            kill_reason=suite_result.kill_reason,
            stall_seconds=bound.stall_seconds,
            ceiling_seconds=bound.ceiling_seconds,
            stall_env_var=STALL_ENV,
            timeout_env_var=CEILING_ENV,
            hint=(
                "The suite-green leg is bounded by progress: it is killed only after "
                f"{STALL_ENV} seconds (default {DEFAULT_STALL_SECONDS}) without a byte of "
                f"output, or past {CEILING_ENV} seconds in total when that opt-in ceiling "
                "is set. Parallelism comes from `test_nprocs`."
            ),
            protocol=RED_GREEN_REPLAY_PROTOCOL,
        )
        return 1
    suite_output = suite_result.output
    if suite_result.returncode != 0:
        log.error(
            "suite-red: selected pytest tests do not pass against the staged tree",
            check_id="red-green-replay-suite-red",
            pytest_returncode=suite_result.returncode,
            failure_summary=_suite_failure_summary(output=suite_output),
            failure_detail=_suite_failure_detail(output=suite_output),
            hint=(
                "The green-verified leg requires its selected tests to pass (exit 0; "
                "an empty selection, pytest exit 5, also rejects): a behavior-"
                "preserving change must keep every existing test green. If this "
                "change is SUPPOSED to alter behavior, author it via the ritual "
                "instead: Red commit (stage the failing test alone), then Green "
                "amend (stage the impl)."
            ),
            protocol=RED_GREEN_REPLAY_PROTOCOL,
        )
        return 1
    captured_at = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    write_trailers(
        msg_path=msg_path,
        trailers=(
            ("TDD-Suite-Green-Scope", scope),
            ("TDD-Suite-Green-Output-Checksum", output_checksum),
            ("TDD-Suite-Green-Captured-At", captured_at),
            *gate_trailers,
        ),
    )
    return 0


handle_suite_green_mode = _handle_suite_green_mode
