"""Tests for `livespec_dev_tooling/fleet/docker_engine_guard_budgets.py`.

Governing specification: `SPECIFICATION/non-functional-requirements.md`
section "Docker engine install guard" -- "Dispatch table", "Deadline" and
"Arm and the dead-man". Governing design:
`docs/docker-engine-guard-design.md`, G1 and H6.

The role sizes each guard operation's transient-unit `TimeoutStartSec`
from the guard's own budget table rather than restating the numbers in
YAML, so this reader runs on the CONTROL node against the same checkout
the role installs from. Every assertion here compares what it prints
with what the guard's model computes -- never with a number written out
again here, which would be the second copy the reader exists to prevent.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import pytest

__all__: list[str] = []

_BUDGETS_MODULE = "livespec_dev_tooling.fleet.docker_engine_guard_budgets"
_BUDGETS_PATH = Path("livespec_dev_tooling/fleet/docker_engine_guard_budgets.py")
_MODEL_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_model"

# An observation window that is NOT the guard's default, so a reader
# that ignored its argument and answered the default would be caught.
_WINDOW_SECONDS = 540


def _budgets() -> Any:
    """The reader module, asserted to be on disk before it is imported.

    The file check comes first on purpose: at Red the module does not
    exist, and a bare top-level import would make the Red a collection
    error that proves only unimportability.
    """
    assert _BUDGETS_PATH.is_file()
    return importlib.import_module(_BUDGETS_MODULE)


def test_the_budget_reader_prints_every_operations_budget_and_the_deadline_as_json(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Design G1 and H6: every bound stated once, in the guard's own model.

    A budget restated in the role is a second place the number can move,
    and the two ways it goes wrong are both silent. Too small and systemd
    kills the operation mid-flight -- a rollback killed before its final
    postcondition check leaves a host nobody has verified. Too large and
    the dead-man can fire inside an operation that is still running. So
    the role reads them from here, on the control node, against the same
    checkout it installs the guard from.

    The window rides in because `observe`'s budget and the dead-man
    deadline are the two numbers that depend on it, and the deadline is
    reported beside the budgets rather than left to the role to add up:
    it is derived from three of them plus a margin, and an arithmetic
    copy in YAML is exactly the restatement this reader removes.

    Asserted against what the model COMPUTES rather than against numbers
    written out again here. A test carrying its own copy of the table
    would pass while the reader and the guard disagreed, which is the one
    failure that matters.
    """
    budgets = _budgets()
    model = importlib.import_module(_MODEL_MODULE)
    assert "budget_report" in budgets.__all__

    report = budgets.budget_report(window_seconds=_WINDOW_SECONDS)

    assert report == {
        "window_seconds": _WINDOW_SECONDS,
        "budgets": {
            operation: model.operation_budget_seconds(
                operation=operation, window_seconds=_WINDOW_SECONDS
            )
            for operation in model.OPERATIONS
        },
        "deadman_deadline_seconds": model.deadline_seconds(window_seconds=_WINDOW_SECONDS),
    }
    assert sorted(report["budgets"]) == sorted(model.OPERATIONS)

    with caplog.at_level("INFO"):
        code = budgets.main(argv=["--window-seconds", str(_WINDOW_SECONDS)])

    assert code == 0
    printed = json.loads("\n".join(record.getMessage() for record in caplog.records))
    assert printed == report

    # The window defaults to the one a guard invoked without one assumes,
    # so a role whose preflight has not derived a window still reads a
    # consistent table rather than nothing at all.
    caplog.clear()
    with caplog.at_level("INFO"):
        assert budgets.main(argv=[]) == 0
    default = json.loads("\n".join(record.getMessage() for record in caplog.records))
    assert default == budgets.budget_report(window_seconds=model.DEFAULT_WINDOW_SECONDS)
