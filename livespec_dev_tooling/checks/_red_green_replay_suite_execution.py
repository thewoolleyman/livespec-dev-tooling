"""Execution paths for fresh and already-completed suite-green replays."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

from _red_green_replay_suite_outcome import (
    SuiteOutcomeTools,
    SuiteRunEvidence,
    finish_suite_run,
    run_suite_candidate,
)
from _red_green_replay_suite_runner import suite_bound

if TYPE_CHECKING:  # pragma: no cover
    import structlog.stdlib

__all__: list[str] = [
    "SuiteExecutionTools",
    "finish_precomputed_suite_run",
    "run_fresh_suite_green_candidate",
    "run_staged_tests_probe",
]

_ScopeSelector = Callable[..., tuple[str, list[str] | None, tuple[tuple[str, str], ...]]]
_SuiteArgvBuilder = Callable[..., list[str]]
_OutcomeToolsFactory = Callable[[], SuiteOutcomeTools]


@dataclass(frozen=True, kw_only=True)
class SuiteExecutionTools:
    """The selection and execution seams for a fresh suite-green replay."""

    outcome_tools: SuiteOutcomeTools
    scope_selector: _ScopeSelector
    suite_argv: _SuiteArgvBuilder


def run_staged_tests_probe(
    *,
    log: structlog.stdlib.BoundLogger,
    tests_paths: list[str],
    outcome_tools: _OutcomeToolsFactory,
    suite_argv: _SuiteArgvBuilder,
) -> SuiteRunEvidence:
    """Run an isolated test-only routing probe through the replay seam."""
    bound = suite_bound(environ=os.environ)
    argv = suite_argv(test_paths=tests_paths, log=log)
    log.info(
        "suite-green-probe-argv: pytest invocation",
        check_id="red-green-replay-suite-green-probe-argv",
        argv=argv,
        scope="staged-tests",
        stall_seconds=bound.stall_seconds,
        ceiling_seconds=bound.ceiling_seconds,
    )
    return run_suite_candidate(
        argv=argv,
        bound=bound,
        log=log,
        tools=outcome_tools(),
        job_pytest_argv=["pytest", *tests_paths],
    )


def finish_precomputed_suite_run(
    *,
    msg_path: Path,
    log: structlog.stdlib.BoundLogger,
    scope: str,
    run: SuiteRunEvidence,
    tools: SuiteOutcomeTools,
) -> tuple[str, int]:
    """Finish a staged-test probe whose result is already available."""
    outcome = finish_suite_run(
        run=run,
        bound=suite_bound(environ=os.environ),
        log=log,
        msg_path=msg_path,
        scope=scope,
        tools=tools,
    )
    return outcome, 0 if outcome == "green" else 1


def run_fresh_suite_green_candidate(
    *,
    msg_path: Path,
    log: structlog.stdlib.BoundLogger,
    index_tree: str | None,
    staged_paths: list[str],
    tests_paths: list[str] | None,
    tools: SuiteExecutionTools,
) -> tuple[str, str, int]:
    """Select and execute a suite-green replay that has no reusable result."""
    scope, selected_tests, producer_trailers = tools.scope_selector(
        cwd=Path.cwd(),
        index_tree=index_tree,
        staged_paths=staged_paths,
        tests_paths=tests_paths,
    )
    bound = suite_bound(environ=os.environ)
    argv = tools.suite_argv(test_paths=selected_tests, log=log)
    log.info(
        "suite-green-argv: pytest invocation",
        check_id="red-green-replay-suite-green-argv",
        argv=argv,
        scope=scope,
        stall_seconds=bound.stall_seconds,
        ceiling_seconds=bound.ceiling_seconds,
    )
    run = run_suite_candidate(argv=argv, bound=bound, log=log, tools=tools.outcome_tools)
    if producer_trailers:
        run = replace(run, gate_trailers=(*run.gate_trailers, *producer_trailers))
    outcome = finish_suite_run(
        run=run,
        bound=bound,
        log=log,
        msg_path=msg_path,
        scope=scope,
        tools=tools.outcome_tools,
    )
    return scope, outcome, 0 if outcome == "green" else 1
