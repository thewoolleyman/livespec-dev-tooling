"""Retry failures only when the changed tree cannot have caused them.

The pytest-rerunfailures marker is deliberately added only after a conservative
working-tree analysis. An analysis failure therefore means ``touched`` rather
than granting a retry on incomplete evidence.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest

from livespec_dev_tooling.flake_retry_announcement import (
    announce,
    retry_summary,
    write_retry_records,
)
from livespec_dev_tooling.flake_retry_changes import change_paths, withheld_reason
from livespec_dev_tooling.flake_retry_decisions import (
    RETRY_ATTEMPTS,
    RETRY_DELAY_SECONDS,
    retry_withheld_reason_for,
    session_withheld_reason,
)
from livespec_dev_tooling.flake_retry_decisions import (
    retry_marker_for as _retry_marker_for,
)
from livespec_dev_tooling.flake_retry_finalizers import preserve_finalizers
from livespec_dev_tooling.flake_retry_records import RetryResult, failure_from
from livespec_dev_tooling.flake_retry_sessions import enter_session, is_nested, leave_session

if TYPE_CHECKING:
    from _pytest.terminal import TerminalReporter

    from livespec_dev_tooling.flake_retry_decisions import Closure, _ModuleFacts

__all__: list[str] = [
    "RETRY_ATTEMPTS",
    "RETRY_DELAY_SECONDS",
    "RetryResult",
    "announce_retries",
    "ast",
    "mark_untouched_tests",
    "record_report",
    "retry_marker_for",
    "retry_summary",
    "write_retry_records",
]

_RESULTS: dict[str, RetryResult] = {}
_FAILED_NODEIDS: set[str] = set()
_SESSION_WITHHELD: list[str] = []
_WITHHELD_BY_NODEID: dict[str, str] = {}
_WORKER_WITHHELD_KEY = "livespec_flake_retry_withheld"
_LIVE_SESSIONS: list[object] = []


def retry_marker_for(
    *,
    repo_root: Path,
    test_path: Path,
    change_paths: set[Path],
    memo: dict[Path, _ModuleFacts | None] | None = None,
    closures: dict[Path, Closure] | None = None,
    session_checked: bool = False,
) -> dict[str, int] | None:
    """Forward the hook's live retry-policy overrides to the extracted decision."""
    return _retry_marker_for(
        repo_root=repo_root,
        test_path=test_path,
        change_paths=change_paths,
        memo=memo,
        closures=closures,
        session_checked=session_checked,
        retry_attempts=RETRY_ATTEMPTS,
        retry_delay_seconds=RETRY_DELAY_SECONDS,
    )


def mark_untouched_tests(
    *,
    root: Path,
    items: list[pytest.Item],
    can_retry: bool = True,
    withheld_by_nodeid: dict[str, str] = _WITHHELD_BY_NODEID,
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
    memo: dict[Path, _ModuleFacts | None] = {}
    closures: dict[Path, Closure] = {}
    withheld = session_withheld_reason(
        repo_root=root,
        test_paths=(Path(str(item.path)) for item in items),
        change_paths=paths,
        memo=memo,
    )
    if withheld is not None:
        return withheld
    for item in items:
        test_path = Path(str(item.path))
        retry_withheld = retry_withheld_reason_for(
            repo_root=root,
            test_path=test_path,
            memo=memo,
            change_paths=paths,
            closures=closures,
        )
        if retry_withheld is not None:
            nodeid = getattr(item, "nodeid", None)
            if isinstance(nodeid, str):
                withheld_by_nodeid[nodeid] = retry_withheld
            continue
        marker = retry_marker_for(
            repo_root=root,
            test_path=test_path,
            change_paths=paths,
            memo=memo,
            closures=closures,
            session_checked=True,
        )
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
        failure = failure_from(longrepr=getattr(report, "longrepr", ""))
        _RESULTS[report.nodeid] = RetryResult(
            nodeid=report.nodeid,
            attempts=(previous.attempts if previous else 0) + 1,
            outcome="rerun",
            failures=(*previous.failures, failure) if previous else (failure,),
        )
    elif previous is not None:
        _RESULTS[report.nodeid] = RetryResult(
            nodeid=report.nodeid,
            attempts=previous.attempts + 1,
            outcome=outcome,
            failures=(
                (*previous.failures, failure_from(longrepr=getattr(report, "longrepr", "")))
                if outcome == "failed"
                else previous.failures
            ),
        )


def announce_retries(
    *,
    terminalreporter: TerminalReporter,
    root: Path,
    withheld: str | None = None,
    withheld_by_nodeid: dict[str, str] | None = None,
) -> None:
    """Persist and announce retry evidence without changing pytest's final verdict."""
    announce(
        terminalreporter=terminalreporter,
        root=root,
        results=list(_RESULTS.values()),
        withheld=withheld,
        withheld_by_nodeid=withheld_by_nodeid,
    )


def _workeroutput(*, holder: object) -> dict[str, object] | None:
    """Return xdist's optional worker-output mapping without importing xdist."""
    candidate = cast(object, vars(holder).get("workeroutput"))
    return cast(dict[str, object], candidate) if isinstance(candidate, dict) else None


def _failed_withholding_reasons() -> dict[str, str]:
    """Return closure holds only for tests that actually failed in this session."""
    return {
        nodeid: reason
        for nodeid, reason in _WITHHELD_BY_NODEID.items()
        if nodeid in _FAILED_NODEIDS
    }


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
        if is_nested(config=config):
            return
        _FAILED_NODEIDS.clear()
        _SESSION_WITHHELD.clear()
        _WITHHELD_BY_NODEID.clear()
        withheld = mark_untouched_tests(
            root=Path(str(session.config.rootpath)),
            items=items,
            can_retry=config.pluginmanager.hasplugin("rerunfailures"),
            withheld_by_nodeid=_WITHHELD_BY_NODEID,
        )
        if withheld is not None:
            _SESSION_WITHHELD.append(withheld)


class _ConfigureHook:
    def __call__(self, config: pytest.Config) -> None:
        """Adapt pytest's positional hook call to the keyword-only setup helper."""
        preserve_finalizers(config=config)


class _SessionStartHook:
    def __call__(self, session: pytest.Session) -> None:
        """Flag a session that starts while another is live in this process as nested."""
        enter_session(config=session.config, live=_LIVE_SESSIONS)


class _SessionFinishHook:
    def __call__(self, session: pytest.Session, exitstatus: int) -> None:
        """Send a worker's withholding reason to xdist's controller."""
        del exitstatus
        leave_session(config=session.config, live=_LIVE_SESSIONS)
        if is_nested(config=session.config):
            return
        workeroutput = _workeroutput(holder=session.config)
        if workeroutput is not None and (_SESSION_WITHHELD or _failed_withholding_reasons()):
            workeroutput[_WORKER_WITHHELD_KEY] = {
                "session": _SESSION_WITHHELD[0] if _SESSION_WITHHELD else None,
                "nodes": _failed_withholding_reasons(),
            }


class _NodeDownHook:
    @pytest.hookimpl(optionalhook=True)
    def __call__(self, node: object, error: object | None) -> None:
        """Collect the worker withholding reason before the controller summarizes."""
        del error
        workeroutput = _workeroutput(holder=node)
        payload = None if workeroutput is None else workeroutput.get(_WORKER_WITHHELD_KEY)
        if not isinstance(payload, dict):
            return
        payload_mapping = cast(dict[str, object], payload)
        session_reason = payload_mapping.get("session")
        if not _SESSION_WITHHELD and isinstance(session_reason, str):
            _SESSION_WITHHELD.append(session_reason)
        node_reason_mapping = cast(dict[str, object], payload_mapping.get("nodes", {}))
        _WITHHELD_BY_NODEID.update(
            {
                nodeid: reason
                for nodeid, reason in node_reason_mapping.items()
                if isinstance(reason, str)
            }
        )


class _ReportHook:
    def __call__(self, report: pytest.TestReport) -> None:
        if len(_LIVE_SESSIONS) > 1:
            return
        record_report(report=report)
        if report.when == "call" and report.outcome == "failed":
            _FAILED_NODEIDS.add(report.nodeid)


class _SummaryHook:
    def __call__(
        self, terminalreporter: TerminalReporter, exitstatus: int, config: pytest.Config
    ) -> None:
        del exitstatus
        if is_nested(config=config):
            return
        announce_retries(
            terminalreporter=terminalreporter,
            root=Path(str(config.rootpath)),
            withheld=_SESSION_WITHHELD[0] if _SESSION_WITHHELD else None,
            withheld_by_nodeid=_failed_withholding_reasons(),
        )


pytest_collection_modifyitems = _CollectionHook().__call__
pytest_configure = _ConfigureHook().__call__
pytest_sessionstart = _SessionStartHook().__call__
pytest_sessionfinish = _SessionFinishHook().__call__
pytest_testnodedown = _NodeDownHook().__call__
pytest_runtest_logreport = _ReportHook().__call__
pytest_terminal_summary = _SummaryHook().__call__
