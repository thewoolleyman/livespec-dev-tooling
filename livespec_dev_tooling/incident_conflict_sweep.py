"""Write journaled rollback-conflicts onto the chain without an operator's `/reconcile`.

The observer never calls recovery again for a retained action: a repeat delivery is
answered from protected state as "existing immutable action; no duplicate effect". A
conflict journaled while the canonical tenant was unavailable would therefore reach the
incident item's chain only when an operator invoked `POST /reconcile` for that action.

This sweep is the automatic trigger. It runs at service start, whenever a recovery
journals a conflict (the service sets `wake`), and on a timer. Each pass reads the
observer state under the fence just long enough to list the actions that owe the
chain, then settles each through the `/reconcile` route's `settle` with
`automatic=True`. That route holds the fence only for short local steps, so a
first-failure callback is never kept waiting behind a principal lookup or a chain
write, and it honours the publication's back-off and terminal state, so nothing is
retried forever.

An entry the sweep cannot read is quarantined: journaled once under `sweep_quarantine`
in the observer record with what is wrong with it, named on stderr, and never swept.
An action owes the chain when its journaled conflict is not yet `reconciled`, or when
it never settled a receipt (the principal's journal is then asked for it); either way
only while it has no terminal state and its back-off has expired. A failed lookup backs
off like a failed write.

Failures follow the fleet's supervisor discipline (narrow at the seam, one broad catch
per program, in `main()`): an expected failure settling one action (an unreadable or
corrupt state file, a failed process) is named on stderr and the pass moves on, and the
same failure anywhere else in a pass is named and the loop sweeps again on the next
wake or tick. Any other exception is not swallowed: it ends the sweep thread with its
traceback on stderr, and `start`'s `on_crash` then stops the service, which exits
non-zero so systemd restarts it. The sweep therefore never stops silently while the
service keeps answering.

`waking_recover` is the service's recovery callback with the sweep's wake attached: a
recovery that journals a conflict sets it, so the conflict is written at once.
"""

from __future__ import annotations

import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from threading import Event, Thread
from typing import cast

from livespec_dev_tooling._incident_conflict_generation import ChainWrite
from livespec_dev_tooling._incident_observer_store import (
    load_record,
    repository_lock,
    save_record,
)
from livespec_dev_tooling._incident_observer_types import RecoveryIntent
from livespec_dev_tooling.incident_conflict_chain import is_conflict_receipt
from livespec_dev_tooling.incident_conflict_publication import is_due, record_outcome
from livespec_dev_tooling.incident_controller_installation import ControllerInstallation
from livespec_dev_tooling.incident_observer_reconcile import ObserverReconcile

__all__: list[str] = ["ConflictSweep", "waking_recover"]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-fdquen
_INTERVAL_SECONDS = 300
_RECEIPT_UNAVAILABLE = "receipt-unavailable"
# The failures a pass expects and survives; anything else crashes the service loudly.
_EXPECTED = (
    OSError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    subprocess.SubprocessError,
)
_QUARANTINE = "sweep_quarantine"


@dataclass(frozen=True, kw_only=True)
class ConflictSweep:
    """The periodic, wakeable write of journaled, unreconciled rollback-conflicts."""

    installation: ControllerInstallation
    interval_seconds: float = _INTERVAL_SECONDS
    wake: Event = field(default_factory=Event, compare=False, repr=False)
    crashed: Event = field(default_factory=Event, compare=False, repr=False)
    clock: Callable[[], float] = field(default=time.time, compare=False, repr=False)

    def pending(self) -> tuple[str, ...]:
        """Action ids that owe the chain now, quarantining any entry it cannot read.

        Read under the fence. A malformed entry (a hand edit, an older schema) is never
        swept: it is journaled once under `sweep_quarantine` with what is wrong with it,
        named on stderr and skipped, so one bad entry cannot crash every start.
        """
        settings = self.installation
        try:
            with repository_lock(
                directory=settings.state, repository=settings.repository, existing_only=True
            ) as path:
                record = load_record(path=path)
                actions = _quarantined(record=record, path=path)
        except (OSError, ValueError, TypeError) as error:
            _say(words=f"{error}")
            return ()
        now = self.clock()
        return tuple(
            action_id
            for action_id, action in actions.items()
            if _owes_chain(action=action) and is_due(action=action, now=now)
        )

    def sweep(self) -> tuple[str, ...]:
        """Settle each pending action; the ids whose conflict the chain accepted."""
        reconcile = ObserverReconcile(installation=self.installation, clock=self.clock)
        accepted: list[str] = []
        for action_id in self.pending():
            try:
                result = reconcile.settle(action_id=action_id, retry=False, automatic=True)
            except _EXPECTED as error:
                _say(words=f"{action_id}: {type(error).__name__}: {error}")
                continue
            if result.status == "reconciled":
                accepted.append(action_id)
            elif result.status == "pending":
                self._defer_lookup(action_id=action_id)
        return tuple(accepted)

    def run(self, *, stop: Event) -> None:
        """Sweep at once, then on every wake or interval, until `stop` is set."""
        while not stop.is_set():
            try:
                _ = self.sweep()
            except _EXPECTED as error:
                _say(words=f"sweep pass failed: {type(error).__name__}: {error}")
            _ = self.wake.wait(self.interval_seconds)
            self.wake.clear()

    def start(self, *, stop: Event, on_crash: Callable[[], None]) -> Thread:
        """Run the loop in a daemon thread; an unexpected crash calls `on_crash`."""
        thread = Thread(
            target=self._supervised, kwargs={"stop": stop, "on_crash": on_crash}, daemon=True
        )
        thread.start()
        return thread

    def _supervised(self, *, stop: Event, on_crash: Callable[[], None]) -> None:
        """Let an unexpected exception end the loop loudly and bring the service down."""
        try:
            self.run(stop=stop)
        finally:
            if not stop.is_set():
                self.crashed.set()
                on_crash()

    def _defer_lookup(self, *, action_id: str) -> None:
        """Back off an action whose receipt the principal could not yet supply."""
        _ = record_outcome(
            state=self.installation.state,
            repository=self.installation.repository,
            action_id=action_id,
            receipt=None,
            outcome=ChainWrite.retry(reason=_RECEIPT_UNAVAILABLE),
            clock=self.clock,
        )


def waking_recover(
    *, callback: Callable[[RecoveryIntent], str | None], journaled: Event
) -> Callable[[RecoveryIntent], str | None]:
    """The recovery callback, waking the conflict sweep when it journals a conflict."""

    def recover(*, intent: RecoveryIntent) -> str | None:
        receipt = callback(intent)
        if is_conflict_receipt(receipt=receipt):
            journaled.set()
        return receipt

    return lambda intent: recover(intent=intent)


def _say(*, words: str) -> None:
    _ = sys.stderr.write(f"incident-conflict-sweep: {words}\n")


def _quarantined(*, record: dict[str, object], path: Path) -> dict[str, dict[str, object]]:
    """The well-formed actions; newly malformed ones are journaled before they are skipped."""
    raw = record.get("actions", {})
    if not isinstance(raw, dict):
        _say(words="the observer state's actions is not an object; nothing is swept")
        return {}
    actions = cast("dict[str, object]", raw)
    held = record.get(_QUARANTINE)
    quarantine = dict(cast("dict[str, str]", held)) if isinstance(held, dict) else {}
    fresh = {
        action_id: why
        for action_id, action in actions.items()
        if action_id not in quarantine and (why := _malformed(action=action)) is not None
    }
    if fresh:
        quarantine.update(fresh)
        record[_QUARANTINE] = quarantine
        save_record(path=path, record=record)
        for action_id, why in fresh.items():
            _say(words=f"{action_id} quarantined: {why}")
    return {
        action_id: cast("dict[str, object]", action)
        for action_id, action in actions.items()
        if action_id not in quarantine
    }


def _malformed(*, action: object) -> str | None:
    """What is wrong with one action entry, or None when the sweep can read it."""
    if not isinstance(action, dict):
        return "not an object"
    entry = cast("dict[str, object]", action)
    kinds: tuple[tuple[str, tuple[type, ...], str], ...] = (
        ("receipt", (str, type(None)), "receipt is not text"),
        ("status", (str,), "status is not text"),
        ("reconciled", (bool,), "reconciled is not a flag"),
        ("sweep", (dict,), "sweep state is not an object"),
    )
    for key, allowed, why in kinds:
        if key in entry and not isinstance(entry[key], allowed):
            return why
    state = cast("dict[str, object]", entry.get("sweep", {}))
    if "next_at" in state and not _number(value=state["next_at"]):
        return "sweep next_at is not a number"
    for key in ("attempts", "streak"):
        if key in state and not _whole(value=state[key]):
            return f"sweep {key} is not a whole number"
    return None


def _number(*, value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _whole(*, value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _owes_chain(*, action: dict[str, object]) -> bool:
    """A journaled conflict the chain has not accepted, or an action that never settled."""
    receipt = action.get("receipt")
    if isinstance(receipt, str) and receipt:
        return is_conflict_receipt(receipt=receipt) and not action.get("reconciled")
    return action.get("status") == "pending"
