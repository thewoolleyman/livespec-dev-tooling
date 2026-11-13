"""Suite-green outcome handling extracted from the replay entry point.

This concern owns the result of a locally or remotely run suite: preserving the
evidence trailers for a green run and producing the actionable refusal for a
red or bounded run. The entry point retains scope selection and telemetry.
"""

from __future__ import annotations

import datetime
import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from _red_green_replay_protocol import RED_GREEN_REPLAY_PROTOCOL
from _red_green_replay_suite_runner import (
    CEILING_ENV,
    DEFAULT_STALL_SECONDS,
    STALL_ENV,
    SuiteBound,
    SuiteRun,
    test_completion_summary,
)
from _red_green_replay_trailers import write_trailers

from livespec_dev_tooling.commit_replay_delegate import ReplayVerdict, unrefused

if TYPE_CHECKING:
    import structlog.stdlib

__all__: list[str] = [
    "SuiteOutcomeTools",
    "SuiteRunEvidence",
    "canonical_output_checksum",
    "failure_detail",
    "failure_summary",
    "finish_suite_run",
    "run_suite_candidate",
]

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
_TRACEBACK_LINE = re.compile(r"^\S+\.py:\d+: .+$", re.MULTILINE)
_FAILURE_DETAIL_LIMIT = 4000


def canonical_output_checksum(*, output: str) -> str:
    """Checksum normalized suite output without scheduling or duration noise."""
    lines = {
        _DURATION.sub("in <t>s", line.strip())
        for line in output.splitlines()
        if line.strip() and not _NOISE_LINE.match(line.strip())
    }
    canonical = "\n".join(sorted(lines))
    return f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


def failure_summary(*, output: str) -> str:
    """Return failed node IDs, falling back to a bounded output head."""
    failed_node_ids = _FAILED_SUMMARY_LINE.findall(output)
    return " ".join(failed_node_ids)[:400] if failed_node_ids else " ".join(output.split())[:400]


def failure_detail(*, output: str) -> str:
    """Return each failing one-line traceback, bounded for a refusal."""
    return "\n".join(_TRACEBACK_LINE.findall(output))[:_FAILURE_DETAIL_LIMIT]


@dataclass(frozen=True, kw_only=True)
class SuiteRunEvidence:
    """The suite result plus the evidence its eventual trailers carry."""

    suite_result: SuiteRun
    output_checksum: str
    gate_trailers: tuple[tuple[str, str], ...]


@dataclass(frozen=True, kw_only=True)
class SuiteOutcomeTools:
    """The entry-point seams used to execute and describe a local suite."""

    canonical_output_checksum: Callable[..., str]
    failure_detail: Callable[..., str]
    failure_summary: Callable[..., str]
    run_local_suite: Callable[..., SuiteRun]
    run_replay: Callable[..., ReplayVerdict]


def run_suite_candidate(
    *,
    argv: list[str],
    bound: SuiteBound,
    log: structlog.stdlib.BoundLogger,
    tools: SuiteOutcomeTools,
    job_pytest_argv: list[str] | None = None,
) -> SuiteRunEvidence:
    """Run the delegated or local suite and retain only its supporting evidence."""
    verdict = unrefused(
        verdict=tools.run_replay(
            repo_root=Path.cwd(),
            pytest_argv=job_pytest_argv or ["pytest", *argv[3:]],
        )
    )
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
        return SuiteRunEvidence(
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
        )
    log.info(
        "commit-time replay gated locally",
        check_id="red-green-replay-gated-locally",
        reason=verdict.reason,
    )
    suite_result = tools.run_local_suite(argv=argv, bound=bound)
    return SuiteRunEvidence(
        suite_result=suite_result,
        output_checksum=tools.canonical_output_checksum(output=suite_result.output),
        gate_trailers=(),
    )


def finish_suite_run(
    *,
    run: SuiteRunEvidence,
    bound: SuiteBound,
    log: structlog.stdlib.BoundLogger,
    msg_path: Path,
    scope: str,
    tools: SuiteOutcomeTools,
) -> str:
    """Record the suite result and return its telemetry outcome word."""
    suite_result = run.suite_result
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
        return "ended"
    if suite_result.returncode != 0:
        log.error(
            "suite-red: selected pytest tests do not pass against the staged tree",
            check_id="red-green-replay-suite-red",
            pytest_returncode=suite_result.returncode,
            failure_summary=tools.failure_summary(output=suite_result.output),
            failure_detail=tools.failure_detail(output=suite_result.output),
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
        return "red"
    captured_at = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    write_trailers(
        msg_path=msg_path,
        trailers=(
            ("TDD-Suite-Green-Scope", scope),
            ("TDD-Suite-Green-Output-Checksum", run.output_checksum),
            ("TDD-Suite-Green-Captured-At", captured_at),
            *run.gate_trailers,
        ),
    )
    return "green"
