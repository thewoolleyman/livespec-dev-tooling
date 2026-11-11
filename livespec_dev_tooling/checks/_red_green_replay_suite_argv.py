"""Worker-count selection and replay evidence for suite-green commands."""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:  # pragma: no cover
    import structlog.stdlib

from livespec_dev_tooling.allowed_cpus import allowed_cpu_count
from livespec_dev_tooling.checks._red_green_replay_suite_runner import (
    SuiteBound,
    SuiteRun,
)
from livespec_dev_tooling.commit_replay_delegate import ReplayVerdict

__all__: list[str] = [
    "SuiteGreenReplay",
    "SuiteReplayRunners",
    "TestOnlyHandlers",
    "dispatch_tests_only_staged",
    "lane_worker_count",
    "run_staged_tests_probe",
    "visible_cpu_count",
]

_LANE_ENV: str = "LIVESPEC_CI_LANE"
_PARALLELISM_ENV: str = "LIVESPEC_TEST_PARALLELISM"


class SuiteGreenReplay(NamedTuple):
    """One suite-green replay verdict and the evidence it can certify."""

    suite_result: SuiteRun
    output_checksum: str
    gate_trailers: tuple[tuple[str, str], ...]
    bound: SuiteBound


@dataclass(frozen=True, kw_only=True)
class SuiteReplayRunners:
    """The suite module's environment-specific replay collaborators."""

    argv_builder: Callable[[list[str] | None], list[str]]
    output_checksum: Callable[[str], str]
    bound_factory: Callable[..., SuiteBound]
    replay_runner: Callable[..., ReplayVerdict]
    suite_runner: Callable[..., SuiteRun]


@dataclass(frozen=True, kw_only=True)
class TestOnlyHandlers:
    """The Red and Green handlers selected by the supervisor module."""

    has_shared_support: Callable[[list[str]], bool]
    run_probe: Callable[[list[str]], SuiteGreenReplay]
    handle_red: Callable[..., int]
    handle_suite: Callable[..., int]


def lane_worker_count(*, environ: Mapping[str, str], visible_cpus: int) -> str:
    """Return the consumers' lane-aware suite-green worker count."""
    if environ.get(_LANE_ENV, "local") == "hosted":
        return "auto"
    explicit = environ.get(_PARALLELISM_ENV, "").strip()
    if explicit:
        return explicit
    return str(max(1, visible_cpus // 4))


def visible_cpu_count(*, affinity: Callable[[int], set[int]] | None, cpu_count: int | None) -> int:
    """Return how many CPUs this process may use.

    `affinity` is `os.sched_getaffinity`, which only Linux provides; elsewhere
    (macOS) the count falls back to `os.cpu_count()`, and to 1 when that is
    unknown.
    """
    return allowed_cpu_count(cpu_max=None, affinity=affinity, cpu_count=cpu_count)


def run_staged_tests_probe(
    *,
    log: structlog.stdlib.BoundLogger,
    tests_paths: list[str] | None,
    runners: SuiteReplayRunners,
) -> SuiteGreenReplay:
    """Run a staged-test replay once and retain the verdict for certification."""
    bound = runners.bound_factory(environ=os.environ)
    argv = runners.argv_builder(tests_paths)
    log.info(
        "suite-green-argv: pytest invocation",
        check_id="red-green-replay-suite-green-argv",
        argv=argv,
        scope="staged-tests" if tests_paths else "full-suite",
        stall_seconds=bound.stall_seconds,
        ceiling_seconds=bound.ceiling_seconds,
    )
    verdict = runners.replay_runner(repo_root=Path.cwd(), pytest_argv=["pytest", *argv[3:]])
    if (
        not verdict.local
        and verdict.exit_status is not None
        and verdict.job_name is not None
        and verdict.tree_hash is not None
        and verdict.output_checksum is not None
    ):
        log.info(
            "commit-time replay gated by a gate Job",
            check_id="red-green-replay-delegated",
            job_name=verdict.job_name,
            tree_hash=verdict.tree_hash,
        )
        return SuiteGreenReplay(
            suite_result=SuiteRun(
                returncode=verdict.exit_status,
                output=verdict.reason,
                timed_out=False,
            ),
            output_checksum=verdict.output_checksum,
            gate_trailers=(
                ("TDD-Suite-Green-Gate-Job", verdict.job_name),
                ("TDD-Suite-Green-Staged-Tree", verdict.tree_hash),
            ),
            bound=bound,
        )
    log.info(
        "commit-time replay gated locally",
        check_id="red-green-replay-gated-locally",
        reason=verdict.reason,
    )
    suite_result = runners.suite_runner(argv=argv, bound=bound)
    return SuiteGreenReplay(
        suite_result=suite_result,
        output_checksum=runners.output_checksum(suite_result.output),
        gate_trailers=(),
        bound=bound,
    )


def dispatch_tests_only_staged(
    *,
    msg_path: Path,
    log: structlog.stdlib.BoundLogger,
    staged_paths: list[str],
    tests_paths: list[str],
    declares_red_intent: bool,
    handlers: TestOnlyHandlers,
) -> int:
    """Route test-only staging through Red or its reusable Green replay.

    Shared test support staged with no test module has no test of its own to
    fail or pass (pytest exits 5), so it is never a Red whatever the subject
    declares: it is green-verified by the full suite it can affect. A passing
    probe is reused as the suite-green verdict only when that leg would run the
    same staged tests, so each staged test module runs once in total.
    """
    shared_support = handlers.has_shared_support(staged_paths)
    if shared_support and not any(Path(path).name.startswith("test_") for path in tests_paths):
        return handlers.handle_suite(
            msg_path=msg_path,
            log=log,
            staged_paths=staged_paths,
            tests_paths=tests_paths,
        )
    if declares_red_intent:
        return handlers.handle_red(msg_path=msg_path, log=log, tests_paths=tests_paths)
    probe = handlers.run_probe(tests_paths)
    if probe.suite_result.returncode != 0:
        return handlers.handle_red(msg_path=msg_path, log=log, tests_paths=tests_paths)
    return handlers.handle_suite(
        msg_path=msg_path,
        log=log,
        staged_paths=staged_paths,
        tests_paths=tests_paths,
        replay=None if shared_support else probe,
    )
