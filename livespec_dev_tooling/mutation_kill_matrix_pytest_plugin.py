"""Pytest plugin that records each test's own outcome for the Rule-26 kill matrix.

The engine runs all of one mutant's selected tests in one pytest process and
loads this plugin with ``-p``.  Three environment variables drive it:

- ``KILL_MATRIX_OUTCOMES`` names a file that receives one JSON line per test,
  appended and flushed as soon as the test's teardown ends, so a process that
  dies part-way still leaves every finished test's outcome behind;
- ``KILL_MATRIX_TIMEOUT`` is the per-test timeout in seconds.  When it is
  positive, a real-time timer with the DEFAULT `SIGALRM` action is armed for
  each test, so a test that outlives it ends the whole process.  The engine
  then re-runs that test alone, and its lone run ending by signal kills the
  mutant.  No Python handler is installed, so nothing a test does can swallow
  the timeout;
- ``KILL_MATRIX_SELECT`` names a file of node ids, one per line; collected
  items outside it are deselected, so a long selection never has to fit on a
  command line.

A test FAILED when any of its setup, call or teardown phases failed.  Each line
also carries the test's duration, which the baseline run (armed with no timer)
compares against the timeout instead.

The hooks take positional parameters because pluggy calls them positionally.
"""

from __future__ import annotations

import json
import os
import signal
import time
from collections.abc import Generator
from pathlib import Path

import pytest

__all__: list[str] = [
    "OUTCOMES_VARIABLE",
    "SELECT_VARIABLE",
    "TIMEOUT_VARIABLE",
]


OUTCOMES_VARIABLE = "KILL_MATRIX_OUTCOMES"
TIMEOUT_VARIABLE = "KILL_MATRIX_TIMEOUT"
SELECT_VARIABLE = "KILL_MATRIX_SELECT"

_failed: dict[str, bool] = {}


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Keep only the node ids the engine selected, when it names a selection."""
    select = os.environ.get(SELECT_VARIABLE)
    if not select:
        return
    wanted = set(Path(select).read_text(encoding="utf-8").split())
    deselected = [item for item in items if item.nodeid not in wanted]
    items[:] = [item for item in items if item.nodeid in wanted]
    config.hook.pytest_deselected(items=deselected)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_protocol(item: pytest.Item) -> Generator[None]:
    """Arm the per-test timer around all three phases, then record the outcome."""
    timeout = float(os.environ.get(TIMEOUT_VARIABLE, "0") or "0")
    if timeout > 0:
        _ = signal.signal(signal.SIGALRM, signal.SIG_DFL)
        _ = signal.setitimer(signal.ITIMER_REAL, timeout)
    started = time.monotonic()
    yield
    if timeout > 0:
        _ = signal.setitimer(signal.ITIMER_REAL, 0)
    _record(nodeid=item.nodeid, duration=time.monotonic() - started)


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    """Remember whether any phase of a test failed."""
    _failed[report.nodeid] = _failed.get(report.nodeid, False) or report.failed


def _record(*, nodeid: str, duration: float) -> None:
    """Append and flush one test's outcome line."""
    destination = os.environ.get(OUTCOMES_VARIABLE)
    if not destination:
        return
    line = json.dumps(
        {"test": nodeid, "failed": _failed.get(nodeid, False), "duration": round(duration, 3)}
    )
    with Path(destination).open("a", encoding="utf-8") as handle:
        _ = handle.write(line + "\n")
        handle.flush()
