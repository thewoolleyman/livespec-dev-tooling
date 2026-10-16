"""Tests for `livespec_dev_tooling/fleet/docker_engine_guard.py`.

The guard's ONE dispatch table and the decision it yields. Governing
specification: `SPECIFICATION/non-functional-requirements.md` section
"Docker engine install guard", table under "Dispatch table"; governing
design: `docs/docker-engine-guard-design.md`, I2.

The table is asserted EXHAUSTIVELY — every operation against every phase,
in each of the three commit-marker columns — because the whole safety
argument of the guard is that no operation runs from a phase its row does
not list. A row-by-row spot check would leave the combinations that
matter (a `start` from `rolling-back`, a `publish` on a committed host)
unexercised, and those are the ones that would hurt.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

__all__: list[str] = []

_GUARD_MODULE = "livespec_dev_tooling.fleet.docker_engine_guard"
_GUARD_PATH = Path("livespec_dev_tooling/fleet/docker_engine_guard.py")
_MODEL_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_model"
_DISPATCH_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_dispatch"
_DISPATCH_PATH = Path("livespec_dev_tooling/fleet/_docker_engine_guard_dispatch.py")

_INSTALL_PHASES = (
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
_ALL_PHASES = (*_INSTALL_PHASES, "rolling-back", "rolled-back", "rollback-partial")

# The specification's "marker absent" column, read as the set of phases
# each operation may proceed from. Anything outside it refuses.
_PROCEEDS_FROM = {
    "reserve": ("rolled-back",),
    "publish": ("reserved", "publishing"),
    "arm": ("published",),
    "start": ("armed",),
    "observe": ("started",),
    "confirm": ("observed",),
    "rollback": (*_INSTALL_PHASES, "rolling-back", "rollback-partial"),
    "recover": _ALL_PHASES,
    "verify": ("rollback-partial", "rolled-back"),
    "reconfigure": (),
}

# `rollback` on an already rolled-back run exits 0 having done nothing;
# it is the one cell of the table that is neither a refusal nor work.
_NOOPS_FROM = {"rollback": ("rolled-back",)}

# The specification's "marker names the run" column, read at phase
# `committed` — the phase a run is in between the commit rename and the
# post-commit steps. `reconfigure` refuses there because its own cell
# restricts it to `confirmed`, the phase those steps end in.
_MARKER_SELF_VERDICT_FROM_COMMITTED = {
    "reserve": "refuse",
    "publish": "refuse",
    "arm": "refuse",
    "start": "refuse",
    "observe": "refuse",
    "confirm": "finish",
    "rollback": "noop",
    "recover": "finish",
    "verify": "refuse",
    "reconfigure": "refuse",
}

_CHECKS_THE_DEADLINE = {"start", "observe", "confirm"}


def _guard() -> Any:
    return importlib.import_module(_GUARD_MODULE)


def _dispatch() -> Any:
    """The admission rule: the row type and the decision it yields."""
    assert _DISPATCH_PATH.is_file()
    return importlib.import_module(_DISPATCH_MODULE)


def _verdict(*, operation: str, marker: str, phase: str | None, expired: bool = False) -> str:
    row = _guard().row_for(operation=operation)
    decide = _dispatch().decide
    return decide(row=row, marker=marker, phase=phase, deadline_passed=expired).verdict


def test_the_dispatch_table_registers_every_operation_exactly_once() -> None:
    """One table, one row per operation, each carrying its own phase transition."""
    assert _GUARD_PATH.is_file()
    guard = _guard()
    model = importlib.import_module(_MODEL_MODULE)

    registered = tuple(row.operation for row in guard.DISPATCH_TABLE)
    assert sorted(registered) == sorted(model.OPERATIONS)
    assert len(set(registered)) == len(registered)

    transitions = {row.operation: row.transition for row in guard.DISPATCH_TABLE}
    assert transitions["reserve"] == "reserved"
    assert transitions["publish"] == "published"
    assert transitions["arm"] == "armed"
    assert transitions["start"] == "started"
    assert transitions["observe"] == "observing"
    assert transitions["confirm"] == "confirmed"
    assert transitions["rollback"] == "rolling-back"
    assert transitions["recover"] is None
    assert transitions["verify"] is None
    assert transitions["reconfigure"] is None


def test_with_the_marker_absent_each_operation_is_allowed_only_from_its_own_phases() -> None:
    """Specification "Dispatch table", middle column, over every combination.

    This is the guard's central safety property: an operation reaching a
    host in a phase its row does not list changes nothing and says so.
    """
    assert _GUARD_PATH.is_file()
    model = importlib.import_module(_MODEL_MODULE)

    for operation in model.OPERATIONS:
        for phase in _ALL_PHASES:
            expected = "refuse"
            if phase in _NOOPS_FROM.get(operation, ()):
                expected = "noop"
            elif phase in _PROCEEDS_FROM[operation]:
                expected = "proceed"
            assert (
                _verdict(operation=operation, marker="absent", phase=phase) == expected
            ), f"{operation} from {phase}"


def test_with_the_marker_absent_a_run_with_no_phase_at_all_admits_only_reserve() -> None:
    """A host that has never held a reservation is exactly where `reserve` belongs.

    Every other operation is an operation ON a run, so with no run recorded
    there is nothing for it to act on and it refuses rather than inventing
    a starting phase.
    """
    assert _GUARD_PATH.is_file()
    model = importlib.import_module(_MODEL_MODULE)

    for operation in model.OPERATIONS:
        expected = "proceed" if operation == "reserve" else "refuse"
        assert _verdict(operation=operation, marker="absent", phase=None) == expected, operation


def test_with_the_marker_naming_the_run_the_table_finishes_or_refuses_per_row() -> None:
    """Specification "Dispatch table", left column, and design H3.

    A committed run is finished, never rolled back: `rollback` exits 0
    without acting, `confirm` and `recover` finish idempotently, the
    forward operations refuse, and `reconfigure` is the only post-commit
    way to change anything.
    """
    assert _GUARD_PATH.is_file()
    model = importlib.import_module(_MODEL_MODULE)

    for operation in model.OPERATIONS:
        assert (
            _verdict(operation=operation, marker="self", phase="committed")
            == _MARKER_SELF_VERDICT_FROM_COMMITTED[operation]
        ), operation

    assert _verdict(operation="reconfigure", marker="self", phase="confirmed") == "proceed"
    for phase in _ALL_PHASES:
        if phase != "confirmed":
            assert _verdict(operation="reconfigure", marker="self", phase=phase) == "refuse"


def test_a_marker_naming_another_run_or_unreadable_refuses_every_operation() -> None:
    """Specification "Dispatch table", right column, fail-closed on both.

    An unreadable marker joins "names another run" rather than "absent":
    a marker that cannot be parsed is not evidence that no run committed,
    and reading it as absent would roll back a committed host.
    """
    assert _GUARD_PATH.is_file()
    model = importlib.import_module(_MODEL_MODULE)

    for operation in model.OPERATIONS:
        for marker in ("other", "unreadable"):
            for phase in (*_ALL_PHASES, None):
                assert (
                    _verdict(operation=operation, marker=marker, phase=phase) == "refuse"
                ), f"{operation} with a {marker} marker from {phase}"


def test_a_passed_deadline_refuses_exactly_the_operations_whose_row_checks_it() -> None:
    """Design H4: `start`, `observe` and `confirm` are the deadline-bounded three.

    `confirm` re-reads the deadline under the lock, which is what makes the
    dead-man's rollback win a race against a `confirm` already waiting for
    that lock.
    """
    assert _GUARD_PATH.is_file()
    guard = _guard()
    model = importlib.import_module(_MODEL_MODULE)

    checked = {row.operation for row in guard.DISPATCH_TABLE if row.needs_deadline}
    assert checked == _CHECKS_THE_DEADLINE

    for operation in model.OPERATIONS:
        for phase in _PROCEEDS_FROM[operation]:
            expired = _verdict(operation=operation, marker="absent", phase=phase, expired=True)
            live = _verdict(operation=operation, marker="absent", phase=phase)
            assert live == "proceed", f"{operation} from {phase}"
            assert expired == ("refuse" if operation in _CHECKS_THE_DEADLINE else "proceed")


def test_every_decision_carries_a_reason_an_operator_can_act_on() -> None:
    """A refusal that does not say why is a refusal an operator has to guess at."""
    assert _GUARD_PATH.is_file()
    model = importlib.import_module(_MODEL_MODULE)
    guard = _guard()

    decide = _dispatch().decide
    for operation in model.OPERATIONS:
        row = guard.row_for(operation=operation)
        for marker in ("absent", "self", "other", "unreadable"):
            for phase in (*_ALL_PHASES, None):
                decision = decide(row=row, marker=marker, phase=phase, deadline_passed=False)
                assert decision.reason.strip() != ""


def test_the_admission_rule_lives_in_its_own_module_beside_the_table() -> None:
    """The rule and the registry are two concerns, and the rule moved out.

    `docker_engine_guard.py` keeps the one TABLE -- the registry of
    operations, their phase transitions and their handlers -- and the
    entry that runs an operation through it. The row TYPE and the
    `decide` that reads a row are the rule itself, and they are what
    `observe`, `confirm`, `verify` and `reconfigure` will be read
    against as later children fill them in, so they get a module of
    their own rather than more lines in the entry point.
    """
    dispatch = _dispatch()
    guard = _guard()

    assert "decide" in dispatch.__all__
    assert "DispatchRow" in dispatch.__all__
    assert "OperationHandler" in dispatch.__all__
    assert "decide" not in guard.__all__
    assert "DispatchRow" not in guard.__all__
    assert "DISPATCH_TABLE" in guard.__all__
    assert "row_for" in guard.__all__
    assert all(isinstance(row, dispatch.DispatchRow) for row in guard.DISPATCH_TABLE)
