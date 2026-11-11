"""Retry failures only when the changed tree cannot have caused them.

The pytest-rerunfailures marker is deliberately added only after a conservative
working-tree analysis. An analysis failure therefore means ``touched`` rather
than granting a retry on incomplete evidence.
"""

from __future__ import annotations

import ast
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest

from livespec_dev_tooling.flake_retry_changes import change_paths, withheld_reason
from livespec_dev_tooling.flake_retry_decisions import (
    RETRY_ATTEMPTS,
    RETRY_DELAY_SECONDS,
    ModuleFacts,
    RetryPolicy,
    retry_marker_for,
)
from livespec_dev_tooling.flake_retry_finalizers import preserve_finalizers

if TYPE_CHECKING:
    from collections.abc import Iterable

    from _pytest.terminal import TerminalReporter

__all__: list[str] = [
    "RETRY_ATTEMPTS",
    "RETRY_DELAY_SECONDS",
    "RetryResult",
    "announce_retries",
    "mark_untouched_tests",
    "record_report",
    "retry_marker_for",
    "retry_summary",
    "write_retry_records",
]

_RESULTS: dict[str, RetryResult] = {}
_WITHHELD: list[str] = []
_WORKER_WITHHELD_KEY = "livespec_flake_retry_withheld"


@dataclass(frozen=True, kw_only=True)
class RetryResult:
    """The final outcome of a test pytest-rerunfailures has retried."""

    nodeid: str
    attempts: int
    outcome: str


def mark_untouched_tests(
    *, root: Path, items: list[pytest.Item], can_retry: bool = True
) -> str | None:
    """Mark only tests proven untouched by this session's complete change set.

    `flaky` is pytest-rerunfailures' marker. A consumer can load this plugin
    through its entry point without that package installed, and there the
    marker is unregistered and `--strict-markers` kills collection
    (livespec-dev-tooling-he3pf2). With no rerunfailures in the session nothing
    is marked: an untouched failure then simply stands, unretried.
    """
    if not can_retry:
        return None
    paths = change_paths(repo_root=root)
    if paths is None:
        return withheld_reason()
    memo: dict[Path, ModuleFacts | None] = {}
    markers: dict[Path, dict[str, int] | None] = {}
    for item in items:
        test_path = Path(str(item.path))
        if test_path not in markers:
            markers[test_path] = retry_marker_for(
                repo_root=root,
                test_path=test_path,
                change_paths=paths,
                memo=memo,
                retry_policy=RetryPolicy(
                    attempts=RETRY_ATTEMPTS,
                    delay_seconds=RETRY_DELAY_SECONDS,
                ),
                parse=ast.parse,
            )
        marker = markers[test_path]
        if marker is not None:
            item.add_marker(pytest.mark.flaky(**marker))
    return None


def record_report(*, report: pytest.TestReport) -> None:
    """Keep final outcomes for rerunfailures' individual retry reports."""
    if report.when != "call":
        return
    previous = _RESULTS.get(report.nodeid)
    outcome = cast(str, report.outcome)
    if outcome == "rerun":
        _RESULTS[report.nodeid] = RetryResult(
            nodeid=report.nodeid,
            attempts=(previous.attempts if previous else 0) + 1,
            outcome="rerun",
        )
    elif previous is not None:
        _RESULTS[report.nodeid] = RetryResult(
            nodeid=report.nodeid, attempts=previous.attempts + 1, outcome=outcome
        )


def write_retry_records(*, repo_root: Path, results: Iterable[RetryResult]) -> Path:
    """Write one JSON line for each retried node id beneath the repository tmp tree."""
    output = repo_root / "tmp" / "flake-retries" / "retries.jsonl"
    _ = output.parent.mkdir(parents=True, exist_ok=True)
    _ = output.write_text(
        "".join(json.dumps(result.__dict__, sort_keys=True) + "\n" for result in results),
        encoding="utf-8",
    )
    return output


def retry_summary(*, results: Iterable[RetryResult]) -> str:
    """Render the loud terminal block required for every retry decision."""
    rows = [f"{result.nodeid}: {result.attempts} attempts, {result.outcome}" for result in results]
    return "FLAKE-RETRIED\n" + "\n".join(rows)


def announce_retries(
    *, terminalreporter: TerminalReporter, root: Path, withheld: str | None = None
) -> None:
    """Persist and announce retry evidence without changing pytest's final verdict."""
    annotate = os.environ.get("GITHUB_ACTIONS") == "true"
    if withheld is not None:
        _ = terminalreporter.write_sep("=", "FLAKE-RETRY-WITHHELD")
        _ = terminalreporter.write_line(f"no failing test is retried this session: {withheld}")
        if annotate:
            _ = terminalreporter.write_line(f"::warning::FLAKE-RETRY-WITHHELD {withheld}")
    results = list(_RESULTS.values())
    if not results:
        return
    _ = write_retry_records(repo_root=root, results=results)
    _ = terminalreporter.write_sep("=", "FLAKE-RETRIED")
    for line in retry_summary(results=results).splitlines()[1:]:
        _ = terminalreporter.write_line(line)
    if annotate:
        for result in results:
            _ = terminalreporter.write_line(f"::warning::FLAKE-RETRIED {result.nodeid}")


def _workeroutput(*, holder: object) -> dict[str, object] | None:
    """Return xdist's optional worker-output mapping without importing xdist."""
    candidate = cast(object, vars(holder).get("workeroutput"))
    return cast(dict[str, object], candidate) if isinstance(candidate, dict) else None


def _record_withheld(*, withheld: str | None) -> None:
    """Keep one withholding reason for the controller's terminal summary."""
    if withheld is not None and withheld not in _WITHHELD:
        _WITHHELD.append(withheld)


# PYTEST CALLS ITS HOOKS POSITIONALLY. pluggy reads a hook's argument names off
# its signature and passes them by position, so a keyword-only hook receives
# nothing, and a `*args` hook receives nothing either (that shape INTERNALERRORed
# every session, run 01M6GVFTX08S). Each hook is therefore the bound `__call__`
# of a small adapter: the dunder takes pytest's fixed positional convention, and
# it hands straight on to the keyword-only function that does the work.
class _CollectionHook:
    def __call__(
        self, session: pytest.Session, config: pytest.Config, items: list[pytest.Item]
    ) -> None:
        withheld = mark_untouched_tests(
            root=Path(str(session.config.rootpath)),
            items=items,
            can_retry=config.pluginmanager.hasplugin("rerunfailures"),
        )
        _WITHHELD[:] = []
        _record_withheld(withheld=withheld)


class _ConfigureHook:
    def __call__(self, config: pytest.Config) -> None:
        """Adapt pytest's positional hook call to the keyword-only setup helper."""
        preserve_finalizers(config=config)


class _SessionFinishHook:
    def __call__(self, session: pytest.Session, exitstatus: int) -> None:
        """Send a worker's withholding reason to xdist's controller."""
        del exitstatus
        workeroutput = _workeroutput(holder=session.config)
        if workeroutput is not None and _WITHHELD:
            workeroutput[_WORKER_WITHHELD_KEY] = _WITHHELD[0]


class _NodeDownHook:
    @pytest.hookimpl(optionalhook=True)
    def __call__(self, node: object, error: object | None) -> None:
        """Collect the worker withholding reason before the controller summarizes."""
        del error
        workeroutput = _workeroutput(holder=node)
        withheld = None if workeroutput is None else workeroutput.get(_WORKER_WITHHELD_KEY)
        _record_withheld(withheld=withheld if isinstance(withheld, str) else None)


class _ReportHook:
    def __call__(self, report: pytest.TestReport) -> None:
        record_report(report=report)


class _SummaryHook:
    def __call__(
        self, terminalreporter: TerminalReporter, exitstatus: int, config: pytest.Config
    ) -> None:
        del exitstatus
        announce_retries(
            terminalreporter=terminalreporter,
            root=Path(str(config.rootpath)),
            withheld=_WITHHELD[0] if _WITHHELD else None,
        )


pytest_collection_modifyitems = _CollectionHook().__call__
pytest_configure = _ConfigureHook().__call__
pytest_sessionfinish = _SessionFinishHook().__call__
pytest_testnodedown = _NodeDownHook().__call__
pytest_runtest_logreport = _ReportHook().__call__
pytest_terminal_summary = _SummaryHook().__call__
