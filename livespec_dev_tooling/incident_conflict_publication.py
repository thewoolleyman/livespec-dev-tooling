"""Carry one journaled conflict onto the chain without holding the observer's fence across it.

The observer's repository fence serializes every write to its protected state, and a
first-failure callback waits only a few seconds for it before answering 503, which
GitHub never redelivers. A chain write is up to three authority calls of tens of
seconds each, so it must never run under that fence. This module holds the fence only
for two short local steps around the write:

1. a snapshot: the action still holds this exact receipt, is not yet `reconciled`, has
   no terminal state, and (for the automatic sweep) its back-off has expired;
2. after the write, a revalidation under the fence before anything is recorded: if the
   action changed meanwhile (another receipt, already reconciled) nothing is written.

The chain write is idempotent, so two publishers racing the same action at worst
repeat one write; the orchestrator recovers its one transition.

Each action carries its sweep state under `sweep` in the observer record:
`attempts` (all of them), `streak` (consecutive attempts of the `last` reason),
`next_at` (epoch seconds) and, once set, `terminal`. A `retry` outcome backs off
exponentially from five minutes to an hour by its streak and turns `terminal` once the
streak reaches that reason's bound, so nothing is retried forever. A `terminal` outcome
is journaled with its reason at once and is never written again automatically; it
needs the incident owner or an operator. A `landed` outcome always wins: it marks the
action `reconciled` even over a terminal another publisher recorded meanwhile, keeping
that diagnosis as `superseded_terminal`.
"""

from __future__ import annotations

import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

from livespec_dev_tooling._incident_conflict_generation import HALF_REOPEN, ChainWrite
from livespec_dev_tooling._incident_observer_store import load_record, repository_lock, save_record
from livespec_dev_tooling._incident_observer_types import RecoveryIntent
from livespec_dev_tooling.incident_conflict_chain import ConflictChain

__all__: list[str] = [
    "ConflictPublication",
    "Published",
    "backoff_seconds",
    "is_due",
    "record_outcome",
]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-fdquen
_SWEEP = "sweep"
_BASE_SECONDS = 300.0
_CAP_SECONDS = 3600.0
# Consecutive attempts of one retried reason before it turns terminal. A pre-merge arm's
# merge is recorded by an operator's `record-merge` within hours or not at all; a claim
# move refused as `claim-changed` on three attempts spaced 5 and 10 minutes apart is no
# token race but the orchestrator's half-reopen; a tenant outage gets about two days.
_BOUNDS = {"merge-unrecorded": 12, "claim-changed": 3}
_EXHAUSTED = {"claim-changed": HALF_REOPEN}
_DEFAULT_BOUND = 48
_RECONCILED = "reconciled"
_LANDED = "landed"
_DEFERRED = "deferred"
_TERMINAL = "terminal"
_SKIPPED = "skipped"


@dataclass(frozen=True, kw_only=True)
class Published:
    """Where one publication left the action: reconciled, deferred, terminal or skipped."""

    status: str
    reason: str = ""


def is_due(*, action: dict[str, object], now: float) -> bool:
    """Whether the automatic sweep may try this action now: not terminal, back-off expired."""
    state = _state(action=action)
    return not state.get(_TERMINAL) and cast("float", state.get("next_at", 0.0)) <= now


def backoff_seconds(*, attempts: int) -> float:
    """Five minutes, doubling per attempt, never more than an hour."""
    return min(_BASE_SECONDS * 2 ** max(attempts - 1, 0), _CAP_SECONDS)


@dataclass(frozen=True, kw_only=True)
class ConflictPublication:
    """One action's chain write between two short fenced steps of the observer state."""

    state: Path
    repository: str
    chain: ConflictChain
    clock: Callable[[], float] = field(default=time.time, compare=False, repr=False)

    def publish(self, *, intent: RecoveryIntent, receipt: str, automatic: bool) -> Published:
        """Write the conflict when the snapshot allows it, then record the outcome."""
        gate = self._snapshot(action_id=intent.action_id, receipt=receipt, automatic=automatic)
        if gate is not None:
            return gate
        outcome = self.chain.record(intent=intent, receipt=receipt)
        return record_outcome(
            state=self.state,
            repository=self.repository,
            action_id=intent.action_id,
            receipt=receipt,
            outcome=outcome,
            clock=self.clock,
        )

    def _snapshot(self, *, action_id: str, receipt: str, automatic: bool) -> Published | None:
        with repository_lock(directory=self.state, repository=self.repository) as path:
            action = _actions(record=load_record(path=path)).get(action_id)
        if action is None or action.get("receipt") != receipt:
            return Published(status=_SKIPPED, reason="the action no longer holds this receipt")
        if action.get(_RECONCILED):
            return Published(status=_RECONCILED, reason="already on the chain")
        terminal = _state(action=action).get(_TERMINAL)
        if terminal:
            return Published(status=_TERMINAL, reason=str(terminal))
        if automatic and not is_due(action=action, now=self.clock()):
            return Published(status=_DEFERRED, reason="backing off")
        return None


def record_outcome(
    *,
    state: Path,
    repository: str,
    action_id: str,
    receipt: str | None,
    outcome: ChainWrite,
    clock: Callable[[], float] = time.time,
) -> Published:
    """Record one outcome under the fence, only if the action is still the one written.

    `receipt` is the receipt the outcome was produced for (None for a lookup that found
    none); an action that has since changed it, was reconciled meanwhile, or is already
    terminal is left as it is.
    """
    with repository_lock(directory=state, repository=repository) as path:
        record = load_record(path=path)
        action = _actions(record=record).get(action_id)
        if action is None or action.get("receipt") != receipt:
            return Published(status=_SKIPPED, reason="the action changed during the write")
        if action.get(_RECONCILED):
            return Published(status=_RECONCILED, reason="already on the chain")
        terminal = _state(action=action).get(_TERMINAL)
        if terminal and outcome.status != _LANDED:
            return Published(status=_TERMINAL, reason=str(terminal))
        published = _apply(action=action, outcome=outcome, clock=clock)
        save_record(path=path, record=record)
    if published.status == _TERMINAL:
        _say(words=f"{action_id} terminal: {published.reason}")
    return published


def _apply(
    *, action: dict[str, object], outcome: ChainWrite, clock: Callable[[], float]
) -> Published:
    state = _state(action=action)
    if outcome.status == _LANDED:
        # A landed write is the chain's proof and outranks any diagnosis recorded before
        # it, including a rival publisher's terminal.
        superseded = state.pop(_TERMINAL, None)
        if superseded:
            state["superseded_terminal"] = superseded
            action[_SWEEP] = state
        action[_RECONCILED] = True
        return Published(status=_RECONCILED, reason="conflict recorded on the chain")
    attempts = cast("int", state.get("attempts", 0)) + 1
    streak = cast("int", state.get("streak", 0)) + 1 if state.get("last") == outcome.reason else 1
    state.update(attempts=attempts, streak=streak, last=outcome.reason)
    if outcome.status == "retry" and streak < _BOUNDS.get(outcome.reason, _DEFAULT_BOUND):
        state["next_at"] = clock() + backoff_seconds(attempts=streak)
        action[_SWEEP] = state
        return Published(status=_DEFERRED, reason=outcome.reason)
    reason = (
        outcome.reason
        if outcome.status == _TERMINAL
        else _EXHAUSTED.get(outcome.reason, f"{outcome.reason}: no landing after {streak} attempts")
    )
    state[_TERMINAL] = reason
    action[_SWEEP] = state
    return Published(status=_TERMINAL, reason=reason)


def _state(*, action: dict[str, object]) -> dict[str, object]:
    state = action.get(_SWEEP)
    return dict(cast("dict[str, object]", state)) if isinstance(state, dict) else {}


def _actions(*, record: dict[str, object]) -> dict[str, dict[str, object]]:
    return cast("dict[str, dict[str, object]]", record.get("actions", {}))


def _say(*, words: str) -> None:
    _ = sys.stderr.write(f"incident-conflict-publication: {words}\n")
