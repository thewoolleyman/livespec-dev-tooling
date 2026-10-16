"""The Docker engine install guard's admission rule: one row, one decision.

Governing specification: `SPECIFICATION/non-functional-requirements.md`
section "Docker engine install guard", the table under "Dispatch table";
governing design: `docs/docker-engine-guard-design.md`, I2.

This module is the RULE. `docker_engine_guard.py` holds the REGISTRY —
the one table giving each operation its row, its phase transition and
its handler — and the entry that runs an operation through it. They are
separated because they change for different reasons: a later child
filling in `observe`, `confirm`, `verify` or `reconfigure` edits the
registry's handlers and never touches this rule, while a change to the
rule would be a change for all ten operations at once.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Protocol

from livespec_dev_tooling.fleet._docker_engine_guard_model import (
    Decision,
    GuardOutcome,
    Operation,
    Phase,
)

if TYPE_CHECKING:
    from livespec_dev_tooling.fleet._docker_engine_guard_model import MarkerState, Verdict
    from livespec_dev_tooling.fleet._docker_engine_guard_state import GuardEnv

__all__: list[str] = [
    "DispatchRow",
    "OperationHandler",
    "decide",
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


_MARKER_FOREIGN: Final[str] = (
    "the commit marker names another run or cannot be read, so this host's "
    "commitment is unknown and nothing may act on it"
)

# One row per operation. Nothing else in the guard decides admission.


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
