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

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Protocol

from livespec_dev_tooling.fleet._docker_engine_guard_model import (
    INSTALL_PHASES,
    PHASES,
    Decision,
    GuardOutcome,
    Operation,
    Phase,
)

if TYPE_CHECKING:
    from livespec_dev_tooling.fleet._docker_engine_guard_model import MarkerState, Verdict
    from livespec_dev_tooling.fleet._docker_engine_guard_state import GuardEnv

__all__: list[str] = [
    "DISPATCH_TABLE",
    "DispatchRow",
    "OperationHandler",
    "decide",
    "row_for",
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


_MARKER_FOREIGN: Final[str] = (
    "the commit marker names another run or cannot be read, so this host's "
    "commitment is unknown and nothing may act on it"
)

# One row per operation. Nothing else in the guard decides admission.
DISPATCH_TABLE: Final[tuple[DispatchRow, ...]] = (
    DispatchRow(
        operation="reserve",
        handler=_pending,
        marker_self="refuse",
        allowed_from=("rolled-back",),
        allowed_without_reservation=True,
        transition="reserved",
    ),
    DispatchRow(
        operation="publish",
        handler=_pending,
        marker_self="refuse",
        allowed_from=("reserved", "publishing"),
        transition="published",
    ),
    DispatchRow(
        operation="arm",
        handler=_pending,
        marker_self="refuse",
        allowed_from=("published",),
        transition="armed",
    ),
    DispatchRow(
        operation="start",
        handler=_pending,
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
        handler=_pending,
        marker_self="noop",
        allowed_from=(*INSTALL_PHASES, "rolling-back", "rollback-partial"),
        noop_from=("rolled-back",),
        transition="rolling-back",
    ),
    DispatchRow(
        operation="recover",
        handler=_pending,
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
