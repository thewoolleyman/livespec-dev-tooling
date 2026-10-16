"""The Docker engine install guard: one dispatch table over one lock.

Governing specification: `SPECIFICATION/non-functional-requirements.md`
section "Docker engine install guard" (this repository). Governing
design: `docs/docker-engine-guard-design.md`, revisions 5 to 8.

Run on the guarded host as `python3 docker_engine_guard.py <op> <run>`,
which is why every module in this set is STDLIB ONLY and why the sibling
imports resolve through `_sibling_module` rather than a package-qualified
`from` — as a script there is no package, and the interpreter puts this
file's own directory on `sys.path` instead.

WHAT THIS MODULE IS FOR. The guard installs the Docker engine on a host
that is already running k3s and is reachable only over Tailscale, so the
cost of a wrong move is an unreachable machine the maintainer cannot
power-cycle. Every operation therefore decides the same way: ensure the
runtime directory, take the one lock within a bounded wait, confirm the
run is the current reservation, read the commit MARKER (never the phase)
to learn whether the run is committed, and then consult exactly one
table. Nothing acts before that table says so.

Child 1a owns the lifecycle: the lock, the records, the deadline, the
table, and `reserve`, `publish`, `arm`, `start` and `recover`. `observe`,
`confirm`, `verify` and `reconfigure` reach their table decision here and
raise `NotImplementedError` past it; child 1b fills them in. `rollback`'s
entry calls `run_rollback` in `_docker_engine_guard_rollback.py`, the
real host lives in `_docker_engine_guard_host.py`, and the package step
lives in `_docker_engine_guard_packages.py` — three stubs each sibling
replaces, so that no sibling ever has to edit this module.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from types import ModuleType
from typing import TYPE_CHECKING, Final, Protocol

from livespec_dev_tooling.fleet._docker_engine_guard_model import (
    INSTALL_PHASES,
    PHASES,
    Decision,
    GuardOutcome,
    Holder,
    Operation,
    Phase,
)
from livespec_dev_tooling.fleet._docker_engine_guard_ops import (
    arm,
    publish,
    recover,
    reserve,
    start,
)
from livespec_dev_tooling.fleet._docker_engine_guard_state import (
    GuardEnv,
    acquire_lock,
    deadline_passed,
    ensure_runtime_dir,
    holder_of,
    read_marker,
    read_reservation,
    release_lock,
)

if TYPE_CHECKING:
    from livespec_dev_tooling.fleet._docker_engine_guard_model import MarkerState, Verdict

__all__: list[str] = [
    "DISPATCH_TABLE",
    "DispatchRow",
    "OperationHandler",
    "decide",
    "row_for",
    "run_operation",
    "sibling_module_name",
]


class OperationHandler(Protocol):
    """What a row runs once its decision is `proceed` or `finish`."""

    def __call__(self, *, run: str, env: GuardEnv, decision: Decision) -> GuardOutcome: ...


@dataclass(frozen=True, kw_only=True)
class DispatchRow:
    """One operation's whole admission rule, in one place.

    `marker_self` is the specification's left column (the marker names
    this run), `allowed_from` and `noop_from` are its middle column (no
    marker), and its right column — a marker naming another run, or one
    that cannot be read — is `refuse` for every operation and so is not a
    field: making it one would invite a row that disagreed with it.
    """

    operation: Operation
    handler: OperationHandler
    marker_self: Verdict
    marker_self_from: tuple[Phase, ...] = ()
    allowed_from: tuple[Phase, ...] = ()
    noop_from: tuple[Phase, ...] = ()
    transition: Phase | None = None
    needs_deadline: bool = False
    allowed_without_reservation: bool = False


def _pending(*, run: str, env: GuardEnv, decision: Decision) -> GuardOutcome:
    """A row whose work a later child owns.

    The table decision above it is real and is reached on every
    invocation; only the work past it is missing, which is why this
    raises rather than returning a refusal — an unimplemented operation
    is a defect in the guard, not a state of the host.
    """
    raise NotImplementedError


def sibling_module_name(*, package: str, name: str) -> str:
    """The import name of a module beside this one, from either side of the split.

    Installed as part of this package, `package` names it and the sibling
    is `<package>.<name>`. Copied onto the guarded host and run as
    `python3 docker_engine_guard.py`, there is no package at all and the
    interpreter has already put this file's own directory on `sys.path`,
    so the bare name is the one that resolves.
    """
    return f"{package}.{name}" if package else name


def _sibling_module(*, name: str) -> ModuleType:
    """Import a sibling guard module, whichever way this module was loaded."""
    return importlib.import_module(sibling_module_name(package=__package__ or "", name=name))


def _rollback_entry(*, run: str, env: GuardEnv, decision: Decision) -> GuardOutcome:
    """Hand a decided rollback to child 2's driver.

    The decision above this call is 1a's and is made under the lock; the
    driver is reached by name so that child 2 implements it in its own
    module rather than in this one.
    """
    rollback = _sibling_module(name="_docker_engine_guard_rollback")
    return rollback.run_rollback(run=run, env=env, decision=decision)


_MARKER_FOREIGN: Final[str] = (
    "the commit marker names another run or cannot be read, so this host's "
    "commitment is unknown and nothing may act on it"
)

# One row per operation. Nothing else in the guard decides admission.
DISPATCH_TABLE: Final[tuple[DispatchRow, ...]] = (
    DispatchRow(
        operation="reserve",
        handler=reserve,
        marker_self="refuse",
        allowed_from=("rolled-back",),
        allowed_without_reservation=True,
        transition="reserved",
    ),
    DispatchRow(
        operation="publish",
        handler=publish,
        marker_self="refuse",
        allowed_from=("reserved", "publishing"),
        transition="published",
    ),
    DispatchRow(
        operation="arm",
        handler=arm,
        marker_self="refuse",
        allowed_from=("published",),
        transition="armed",
    ),
    DispatchRow(
        operation="start",
        handler=start,
        marker_self="refuse",
        allowed_from=("armed",),
        needs_deadline=True,
        transition="started",
    ),
    DispatchRow(
        operation="observe",
        handler=_pending,
        marker_self="refuse",
        allowed_from=("started",),
        needs_deadline=True,
        transition="observing",
    ),
    DispatchRow(
        operation="confirm",
        handler=_pending,
        marker_self="finish",
        allowed_from=("observed",),
        needs_deadline=True,
        transition="confirmed",
    ),
    DispatchRow(
        operation="rollback",
        handler=_rollback_entry,
        marker_self="noop",
        allowed_from=(*INSTALL_PHASES, "rolling-back", "rollback-partial"),
        noop_from=("rolled-back",),
        transition="rolling-back",
    ),
    DispatchRow(
        operation="recover",
        handler=recover,
        marker_self="finish",
        allowed_from=PHASES,
    ),
    DispatchRow(
        operation="verify",
        handler=_pending,
        marker_self="refuse",
        allowed_from=("rollback-partial", "rolled-back"),
    ),
    DispatchRow(
        operation="reconfigure",
        handler=_pending,
        marker_self="proceed",
        marker_self_from=("confirmed",),
    ),
)

_ROW_BY_OPERATION: Final[dict[Operation, DispatchRow]] = {
    row.operation: row for row in DISPATCH_TABLE
}


def row_for(*, operation: Operation) -> DispatchRow:
    """The one table row registering `operation`."""
    return _ROW_BY_OPERATION[operation]


def _committed_decision(*, row: DispatchRow, phase: Phase | None) -> Decision:
    """The marker names this run, so the run is committed whatever the phase reads."""
    if row.marker_self == "refuse":
        return Decision(
            verdict="refuse",
            reason=f"{row.operation} refuses a run the commit marker already names",
        )
    if row.marker_self_from and phase not in row.marker_self_from:
        return Decision(
            verdict="refuse",
            reason=f"{row.operation} is allowed only from {row.marker_self_from}, not {phase}",
        )
    return Decision(
        verdict=row.marker_self,
        reason=f"the commit marker names this run, so {row.operation} takes the committed path",
    )


def _uncommitted_decision(
    *, row: DispatchRow, phase: Phase | None, deadline_passed: bool
) -> Decision:
    """No marker, so the run is uncommitted whatever its phase reads."""
    if phase is None:
        if row.allowed_without_reservation:
            return Decision(verdict="proceed", reason="no run holds this host's reservation")
        return Decision(
            verdict="refuse", reason=f"{row.operation} needs a run with a recorded phase"
        )
    if phase in row.noop_from:
        return Decision(
            verdict="noop", reason=f"{row.operation} has nothing left to do from {phase}"
        )
    if phase not in row.allowed_from:
        return Decision(
            verdict="refuse",
            reason=f"{row.operation} is allowed from {row.allowed_from}, and this run is {phase}",
        )
    if row.needs_deadline and deadline_passed:
        return Decision(
            verdict="refuse",
            reason=f"{row.operation} is out of time: the run's deadline has passed",
        )
    return Decision(verdict="proceed", reason=f"{row.operation} is allowed from {phase}")


def decide(
    *, row: DispatchRow, marker: MarkerState, phase: Phase | None, deadline_passed: bool
) -> Decision:
    """Read the row against the marker and the phase, and say what happens.

    The marker is read FIRST and outranks the phase, because a run whose
    phase record says `committed` after a failed directory fsync and a
    reboot is NOT committed — only the marker says that. Reading them the
    other way round would roll back a committed host, or commit one that
    never reached the commit point.
    """
    if marker in {"other", "unreadable"}:
        return Decision(verdict="refuse", reason=_MARKER_FOREIGN)
    if marker == "self":
        return _committed_decision(row=row, phase=phase)
    return _uncommitted_decision(row=row, phase=phase, deadline_passed=deadline_passed)


def _decided(
    *, operation: Operation, run: str, decision: Decision, holder: Holder | None
) -> GuardOutcome:
    """Carry a refusal or a no-op out, with everything an operator must see."""
    return GuardOutcome(
        operation=operation,
        run=run,
        verdict=decision.verdict,
        reason=decision.reason,
        holder=holder,
    )


def _locked_operation(*, operation: Operation, run: str, env: GuardEnv) -> GuardOutcome:
    """Decide and run one operation, with the lock already held.

    The order is the specification's and is not interchangeable: the
    reservation first (an operation on a run this host does not hold
    changes nothing), then the MARKER, then the phase. Reading the phase
    before the marker would let a run whose phase record says `committed`
    after a failed directory fsync be treated as committed when it is not.
    """
    row = row_for(operation=operation)
    reservation = read_reservation(paths=env.paths)
    holder = holder_of(env=env, run=reservation)
    if not row.allowed_without_reservation and reservation != run:
        return GuardOutcome(
            operation=operation,
            run=run,
            verdict="refuse",
            reason=f"{run} is not this host's current reservation",
            holder=holder,
        )
    decision = decide(
        row=row,
        marker=read_marker(paths=env.paths, run=run),
        phase=None if holder is None else holder.phase,
        deadline_passed=deadline_passed(
            deadline=None if holder is None else holder.deadline, host=env.host
        ),
    )
    if decision.verdict in {"refuse", "noop"}:
        return _decided(operation=operation, run=run, decision=decision, holder=holder)
    return row.handler(run=run, env=env, decision=decision)


def run_operation(*, operation: Operation, run: str, env: GuardEnv) -> GuardOutcome:
    """Run one guard operation end to end: directory, lock, decision, work.

    Every operation takes this path, which is what makes the lock, the
    bounded wait and the reservation check properties of the GUARD rather
    than habits of each operation. A lock wait that expires refuses
    without acting: it has read nothing and written nothing.
    """
    ensure_runtime_dir(paths=env.paths, host=env.host)
    fd = acquire_lock(paths=env.paths, host=env.host)
    if fd is None:
        return GuardOutcome(
            operation=operation,
            run=run,
            verdict="refuse",
            reason="another guard operation holds the lock; waited the full bound and stopped",
        )
    try:
        return _locked_operation(operation=operation, run=run, env=env)
    finally:
        release_lock(fd=fd)
