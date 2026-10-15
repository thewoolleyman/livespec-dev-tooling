"""Tests for the Docker engine install guard's lifecycle half (child 1a).

Governing specification: `SPECIFICATION/non-functional-requirements.md`
section "Docker engine install guard". Governing design:
`docs/docker-engine-guard-design.md` (revisions 5 to 8 govern).

The guard is six factory-safe children sharing one module set; this file
covers 1a — the lock, the run directory and its phase records, the
deadline, the dispatch table, and the `reserve`, `publish`, `arm`,
`start` and `recover` operations. The host is reached only through the
`HostOps` protocol, so every assertion here runs against `FakeHost` with
an injected clock, boot id and state roots, and no real host action ever
fires.
"""

from __future__ import annotations

import importlib
from pathlib import Path

__all__: list[str] = []

_MODEL_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_model"
_MODEL_PATH = Path("livespec_dev_tooling/fleet/_docker_engine_guard_model.py")

# The observation window the design derives at preflight from the effective
# k3s resync periods (420 s at the measured defaults). Only `observe`'s
# budget reads it; every other operation's budget is a flat number.
_WINDOW_SECONDS = 420


def test_the_operation_budget_table_gives_each_operation_its_timeout_start_sec() -> None:
    """Design H6: every bound stated, and `observe` alone adds the window.

    These are the `TimeoutStartSec` values the role passes to each
    operation's transient oneshot unit, so a wrong number here is a guard
    that systemd kills mid-rollback rather than a test that merely
    disagrees with a table.
    """
    assert _MODEL_PATH.is_file()
    model = importlib.import_module(_MODEL_MODULE)

    budgets = {
        operation: model.operation_budget_seconds(
            operation=operation, window_seconds=_WINDOW_SECONDS
        )
        for operation in model.OPERATIONS
    }

    assert budgets == {
        "reserve": 60,
        "publish": 1800,
        "arm": 60,
        "start": 180,
        "observe": _WINDOW_SECONDS + 300,
        "confirm": 120,
        "rollback": 900,
        "recover": 1800,
        "verify": 120,
        "reconfigure": 120,
    }


def test_the_phase_vocabulary_names_both_paths_and_keeps_them_disjoint() -> None:
    """Specification section "Phases": nine install phases, three rollback phases.

    `observing` is the phase 1b's `observe` claims from `started` before its
    first sample, so it belongs to the install path even though nothing in
    1a transitions into it.
    """
    assert _MODEL_PATH.is_file()
    model = importlib.import_module(_MODEL_MODULE)

    assert model.INSTALL_PHASES == (
        "reserved",
        "publishing",
        "published",
        "armed",
        "started",
        "observing",
        "observed",
        "committed",
        "confirmed",
    )
    assert model.ROLLBACK_PHASES == ("rolling-back", "rolled-back", "rollback-partial")
    assert set(model.INSTALL_PHASES).isdisjoint(model.ROLLBACK_PHASES)
    assert model.PHASES == model.INSTALL_PHASES + model.ROLLBACK_PHASES
