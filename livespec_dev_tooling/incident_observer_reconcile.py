"""Clear an unknown recovery outcome by its exact receipt, or retry it through the principal.

`POST /reconcile` is the observer's authenticated control route for an action a
timed-out principal left `pending`. Such an action refuses every later `/arm`, and
nothing else ever resolves it. The route works from the intent retained in protected
state and takes no receipt from the caller: the receipt comes from the principal's
`lookup`, which settles any open publication attempt from forge facts.

`retry_publish` is the operator's explicit request to go further when no receipt is
available. The retained intent then runs through the same principal under the
repository lock. Exactly one revert per action is the principal's rule, kept by its
durable publication ledger: an open attempt re-sends its one recorded commit, and a
new attempt starts only when no earlier one can have landed.

The reply's receipt is not yet canonical. Recording a revert receipt in the incident's
chain is the orchestrator's `record-revert-receipt` action, which this route does not
call. A journaled rollback-conflict receipt is different: this route replays it onto the
chain through `ConflictChain` until the chain accepts it, so a conflict recorded while the
tenant was unavailable still blocks the incident item once the tenant returns.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, cast

from livespec_dev_tooling._incident_observer_ack import recovery_action_id
from livespec_dev_tooling._incident_observer_store import (
    load_record,
    read_observer_arm,
    read_registration,
    repository_lock,
    save_record,
)
from livespec_dev_tooling._incident_observer_types import ObserverResult, RecoveryIntent
from livespec_dev_tooling._incident_recovery_journal_cause import (
    decode_completion,
    decode_regression,
)
from livespec_dev_tooling.incident_conflict_chain import ConflictChain, is_conflict_receipt
from livespec_dev_tooling.incident_controller_installation import ControllerInstallation
from livespec_dev_tooling.incident_inverse import observer_inverse_callback
from livespec_dev_tooling.incident_inverse_service import ProcessInverseForge
from livespec_dev_tooling.incident_observer import reconcile_action_receipt

__all__: list[str] = ["ObserverReconcile"]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-gho3w4
_FIELDS = frozenset({"repository", "action_id", "retry_publish"})
_ACTION_ID = re.compile(r"[0-9a-f]{64}")
# An operator is waiting and no first failure is racing this call, so it outwaits the
# fifteen seconds the first-failure callback allows a principal call.
_PRINCIPAL_TIMEOUT_SECONDS = 45


@dataclass(frozen=True, kw_only=True)
class ObserverReconcile:
    """Resolve one retained action; every effect goes through the installed principal."""

    installation: ControllerInstallation

    def execute(self, *, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        del path
        action_id, retry = payload.get("action_id"), payload.get("retry_publish")
        if (
            frozenset(payload) != _FIELDS
            or not isinstance(action_id, str)
            or _ACTION_ID.fullmatch(action_id) is None
            or type(retry) is not bool
        ):
            return _refused(reason="exact repository, action_id and retry_publish required")
        settings = self.installation
        with repository_lock(directory=settings.state, repository=settings.repository) as path_:
            action = _actions(record=load_record(path=path_)).get(action_id)
        if action is None:
            return _refused(reason="unknown exact action receipt")
        intent = _retained_intent(action_id=action_id, action=action)
        if intent is None:
            return _refused(reason="missing immutable action authority")
        forge = ProcessInverseForge(
            command=settings.principal, timeout_seconds=_PRINCIPAL_TIMEOUT_SECONDS
        )
        chain = ConflictChain.installed(
            command=settings.reader, release=settings.reader_release, repo=settings.repo
        )
        result = reconcile_action_receipt(
            directory=settings.state,
            repository=settings.repository,
            action_id=action_id,
            read_exact_receipt=lambda _action: _exact_receipt(forge=forge, intent=intent),
            publish_receipt=lambda _authority, _action, receipt: (
                is_conflict_receipt(receipt=receipt)
                and chain.record(intent=intent, receipt=receipt)
            ),
        )
        if result.status == "pending" and retry:
            result = self._retry(intent=intent, forge=forge, chain=chain)
        return asdict(result)

    def _retry(
        self, *, intent: RecoveryIntent, forge: ProcessInverseForge, chain: ConflictChain
    ) -> ObserverResult:
        settings = self.installation
        recover = observer_inverse_callback(
            repo_root=settings.repo, forge=forge, resume_unresolved=True, chain=chain
        )
        with repository_lock(directory=settings.state, repository=settings.repository) as path:
            record = load_record(path=path)
            if read_registration(record=record) != intent.registration:
                return ObserverResult(
                    status="refused",
                    reason="incident registration changed before the retry",
                    action_id=intent.action_id,
                )
            action = _actions(record=record).get(intent.action_id)
            if action is None:
                return ObserverResult(
                    status="refused",
                    reason="retained action missing before the retry",
                    action_id=intent.action_id,
                )
            if action.get("receipt"):
                return ObserverResult(
                    status="completed",
                    reason="retained action already holds its receipt",
                    action_id=intent.action_id,
                    receipt=cast("str", action["receipt"]),
                )
            receipt = recover(intent)
            if receipt:
                action.update(status="completed", receipt=receipt)
                save_record(path=path, record=record)
        return ObserverResult(
            status="completed" if receipt else "pending",
            reason="retained action retried through the principal's one-revert ledger",
            action_id=intent.action_id,
            receipt=receipt,
        )


def _exact_receipt(*, forge: ProcessInverseForge, intent: RecoveryIntent) -> str | None:
    """The principal's receipt; a reserved or unobservable answer is simply no receipt yet."""
    try:
        return forge.read_exact_receipt(intent=intent)
    except OSError:
        return None


def _retained_intent(*, action_id: str, action: dict[str, object]) -> RecoveryIntent | None:
    registration = read_registration(record=action)
    if registration is None or recovery_action_id(registration=registration) != action_id:
        return None
    completion = action.get("completion")
    return RecoveryIntent(
        action_id=action_id,
        registration=registration,
        completion=None if completion is None else decode_completion(raw=completion),
        observer_arm=read_observer_arm(record=action),
        regression=decode_regression(raw=action.get("regression")),
    )


def _actions(*, record: dict[str, object]) -> dict[str, dict[str, object]]:
    return cast("dict[str, dict[str, object]]", record.get("actions", {}))


def _refused(*, reason: str) -> dict[str, Any]:
    return {"status": "refused", "reason": reason}
