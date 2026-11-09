"""Per-test record of one suite-green pytest run, and its readable summary.

Under `-q` pytest names no passing test and prints nothing until the first test
completes, so a run ended at its stall window cannot be attributed from its
output stream. The suite-green runner therefore loads this module into the
pytest run it supervises (`PYTEST_PLUGINS`, never a `pytest11` entry point,
which would register the same module twice), and these hooks append one JSON
line per event to a record file the runner reads when it ends the run.
pytest-xdist workers load it too, so each line carries the worker that ran the
test. A pytest run started from another directory, such as one a test launches,
does not write to the record.
"""

from __future__ import annotations

import datetime
import json
import os
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    import pytest

__all__: list[str] = [
    "PLUGIN_MODULE",
    "RECORD_PATH_ENV",
    "RECORD_ROOT_ENV",
    "RunningTest",
    "SuiteRecord",
    "describe_record",
    "pytest_collection_finish",
    "pytest_runtest_logfinish",
    "pytest_runtest_logstart",
    "read_record",
    "record_environment",
]

PLUGIN_MODULE: str = "livespec_dev_tooling.suite_run_record"
RECORD_PATH_ENV: str = "LIVESPEC_SUITE_GREEN_RECORD_PATH"
RECORD_ROOT_ENV: str = "LIVESPEC_SUITE_GREEN_RECORD_ROOT"
_WORKER_ENV: str = "PYTEST_XDIST_WORKER"


@dataclass(frozen=True, kw_only=True)
class RunningTest:
    """A test that had started and not finished."""

    nodeid: str
    worker: str
    started_at: float


@dataclass(frozen=True, kw_only=True)
class SuiteRecord:
    """What the per-test record says about one run."""

    collected: int | None
    completed: int
    last_nodeid: str | None
    last_completed_at: float | None
    running: tuple[RunningTest, ...] = ()


def record_environment(
    *, environ: Mapping[str, str], record_path: Path, root: Path
) -> dict[str, str]:
    """Return the child environment that makes pytest keep the per-test record."""
    existing = environ.get("PYTEST_PLUGINS", "")
    return {
        "PYTEST_PLUGINS": f"{existing},{PLUGIN_MODULE}" if existing else PLUGIN_MODULE,
        RECORD_PATH_ENV: str(record_path),
        RECORD_ROOT_ENV: str(root),
    }


def _append(*, event: Mapping[str, str | int | float]) -> None:
    """Append one event to the record, when this pytest run is the supervised one."""
    path = os.environ.get(RECORD_PATH_ENV)
    if path is None or Path.cwd() != Path(os.environ[RECORD_ROOT_ENV]):
        return
    descriptor = os.open(path, os.O_WRONLY | os.O_APPEND)
    try:
        _ = os.write(descriptor, (json.dumps(dict(event)) + "\n").encode("utf-8"))
    finally:
        os.close(descriptor)


def read_record(*, path: Path) -> SuiteRecord:
    """Fold the run's record file into one `SuiteRecord`."""
    collected: int | None = None
    finished: dict[str, float] = {}
    running: dict[str, RunningTest] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        event: dict[str, str | int | float] = json.loads(line)
        if event["event"] == "collected":
            collected = max(collected or 0, int(event["count"]))
        elif event["event"] == "start":
            running[str(event["nodeid"])] = RunningTest(
                nodeid=str(event["nodeid"]),
                worker=str(event["worker"]),
                started_at=float(event["at"]),
            )
        else:
            _ = running.pop(str(event["nodeid"]), None)
            finished[str(event["nodeid"])] = float(event["at"])
    last = max(finished.items(), key=lambda item: item[1], default=(None, None))
    return SuiteRecord(
        collected=collected,
        completed=len(finished),
        last_nodeid=last[0],
        last_completed_at=last[1],
        running=tuple(running.values()),
    )


def _instant(*, at: float) -> str:
    return datetime.datetime.fromtimestamp(at, tz=datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def _where(*, test: RunningTest) -> str:
    return f"worker {test.worker}" if test.worker else "the main process"


def _running_clause(*, record: SuiteRecord, now: float) -> str:
    if not record.running:
        return "no test was running"
    return "still running: " + "; ".join(
        f"{test.nodeid} on {_where(test=test)} for {round(now - test.started_at)} seconds"
        for test in record.running
    )


def describe_record(*, record: SuiteRecord, elapsed_seconds: float, now: float, kind: str) -> str:
    """Describe how far the run had got when it was ended."""
    verb = "stalled" if kind == "stalled" else "was ended at its ceiling"
    progress = (
        "collection had not finished"
        if record.collected is None
        else f"{record.completed} of {record.collected} collected tests had completed"
    )
    if record.last_nodeid is None or record.last_completed_at is None:
        last = "no test had completed" + (
            "" if record.running else ", so the run was ended during collection or worker start-up"
        )
        position = f"the run {verb} before any test completed"
    else:
        last = (
            f"the last test reported complete was {record.last_nodeid} "
            f"at {_instant(at=record.last_completed_at)}"
        )
        position = (
            f"the run {verb} after its last test rather than mid-suite"
            if record.collected is not None and record.completed >= record.collected
            else f"the run {verb} mid-suite"
        )
    return (
        f"after {round(elapsed_seconds)} seconds, {progress}; {last}; "
        f"{_running_clause(record=record, now=now)}; {position}"
    )


class _CollectionFinishHook:
    def __call__(self, session: pytest.Session) -> None:
        _append(event={"event": "collected", "count": len(session.items)})


class _LogStartHook:
    def __call__(self, nodeid: str, location: object) -> None:
        del location
        _append(
            event={
                "event": "start",
                "nodeid": nodeid,
                "worker": os.environ.get(_WORKER_ENV, ""),
                "at": time.time(),
            }
        )


class _LogFinishHook:
    def __call__(self, nodeid: str, location: object) -> None:
        del location
        _append(event={"event": "finish", "nodeid": nodeid, "at": time.time()})


pytest_collection_finish = _CollectionFinishHook().__call__
pytest_runtest_logstart = _LogStartHook().__call__
pytest_runtest_logfinish = _LogFinishHook().__call__
