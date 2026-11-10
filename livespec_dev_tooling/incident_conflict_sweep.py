"""Replay journaled rollback-conflicts onto the chain without an operator's `/reconcile`.

The observer never calls recovery again for a retained action: a repeat delivery is
answered from protected state as "existing immutable action; no duplicate effect". A
conflict journaled while the canonical tenant was unavailable would therefore reach the
incident item's chain only when an operator invoked `POST /reconcile` for that action.

This sweep is the automatic trigger. At service start and then on a timer it finds every
retained action whose receipt is a rollback-conflict and that `/reconcile` has not yet
marked `reconciled`, and runs that same route for it. The route owns the write and the
`reconciled` mark, so nothing here writes the chain or the state itself; a refused or
failed replay (the tenant is still down) leaves the action pending for the next pass,
and each failed write names its refusal on stderr.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from threading import Event, Thread
from typing import cast

from livespec_dev_tooling._incident_observer_store import load_record, repository_lock
from livespec_dev_tooling.incident_conflict_chain import is_conflict_receipt
from livespec_dev_tooling.incident_controller_installation import ControllerInstallation
from livespec_dev_tooling.incident_observer_reconcile import ObserverReconcile

__all__: list[str] = ["ConflictSweep"]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-fdquen
_ROUTE = "/reconcile"
_INTERVAL_SECONDS = 300


@dataclass(frozen=True, kw_only=True)
class ConflictSweep:
    """The periodic replay of journaled, unreconciled rollback-conflicts."""

    installation: ControllerInstallation
    interval_seconds: float = _INTERVAL_SECONDS

    def pending(self) -> tuple[str, ...]:
        """Action ids whose journaled conflict the chain has not yet accepted."""
        settings = self.installation
        try:
            with repository_lock(
                directory=settings.state, repository=settings.repository, existing_only=True
            ) as path:
                record = load_record(path=path)
        except (OSError, ValueError, TypeError) as error:
            _say(words=f"{error}")
            return ()
        actions = cast("dict[str, dict[str, object]]", record.get("actions", {}))
        return tuple(
            action_id for action_id, action in actions.items() if _owes_chain(action=action)
        )

    def sweep(self) -> tuple[str, ...]:
        """Run `/reconcile` for each pending action; the ids the chain accepted."""
        reconcile = ObserverReconcile(installation=self.installation)
        accepted: list[str] = []
        for action_id in self.pending():
            try:
                result = reconcile.execute(
                    path=_ROUTE,
                    payload={
                        "repository": self.installation.repository,
                        "action_id": action_id,
                        "retry_publish": False,
                    },
                )
            except (OSError, ValueError, TypeError, KeyError) as error:
                _say(words=f"{error} ({action_id})")
                continue
            if result.get("status") == "reconciled":
                accepted.append(action_id)
        return tuple(accepted)

    def run(self, *, stop: Event) -> None:
        """Sweep at once, then after every interval, until `stop` is set."""
        while True:
            _ = self.sweep()
            if stop.wait(self.interval_seconds):
                return

    def start(self, *, stop: Event) -> Thread:
        """Run the loop in a daemon thread, so the server's exit never waits on it."""
        thread = Thread(target=self.run, kwargs={"stop": stop}, daemon=True)
        thread.start()
        return thread


def _text(*, value: object) -> str | None:
    return value if isinstance(value, str) else None


def _say(*, words: str) -> None:
    _ = sys.stderr.write(f"incident-conflict-sweep: {words}\n")


def _owes_chain(*, action: dict[str, object]) -> bool:
    """A journaled conflict the chain has not accepted, or an action that never settled."""
    receipt = _text(value=action.get("receipt"))
    if receipt:
        return is_conflict_receipt(receipt=receipt) and not action.get("reconciled")
    return action.get("status") == "pending"
