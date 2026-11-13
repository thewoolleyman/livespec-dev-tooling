"""Tests-only commit routing for the Red and suite-green replay legs."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from _red_green_replay_modes import _handle_red_mode, _handle_suite_green_mode
from _red_green_replay_suite import (
    has_shared_test_support,
    run_staged_tests_probe,
    stages_only_shared_test_support,
)

if TYPE_CHECKING:  # pragma: no cover
    import structlog.stdlib

__all__: list[str] = ["dispatch_tests_only"]


def dispatch_tests_only(
    *,
    declares_red_intent: bool,
    msg_path: Path,
    log: structlog.stdlib.BoundLogger,
    staged_paths: list[str],
    tests_paths: list[str],
) -> int:
    """Route tests-only staging and reuse only an isolated passing probe."""
    if declares_red_intent:
        return _handle_red_mode(msg_path=msg_path, log=log, tests_paths=tests_paths)
    if stages_only_shared_test_support(staged_paths=staged_paths, tests_paths=tests_paths):
        return _handle_suite_green_mode(
            msg_path=msg_path,
            log=log,
            staged_paths=staged_paths,
            tests_paths=tests_paths,
        )
    if not has_shared_test_support(staged_paths=staged_paths):
        probe = run_staged_tests_probe(log=log, tests_paths=tests_paths)
        if probe.suite_result.returncode != 0:
            return _handle_red_mode(msg_path=msg_path, log=log, tests_paths=tests_paths)
        return _handle_suite_green_mode(
            msg_path=msg_path,
            log=log,
            staged_paths=staged_paths,
            tests_paths=tests_paths,
            precomputed_run=probe,
        )
    return _handle_suite_green_mode(
        msg_path=msg_path,
        log=log,
        staged_paths=staged_paths,
        tests_paths=tests_paths,
    )
