"""The live incident recovery principal: six scoped operations as the recovery App.

This is the independently provisioned principal `incident_inverse.recover_incident_inverse`
was written against (`docs/incident-inverse.md`), replacing the journal-only
service in the released-installation manifest. It answers `landed`, `authorize`,
`head`, `lookup`, `publish` and `conflict` for one retained observer action, and
it is the only component that moves master: as the dedicated recovery App, whose
installation token the master ruleset alone lets bypass required checks. No local
test, factory run or pre-merge CI is part of the path.

THE PRINCIPAL TRUSTS NO CALLER BYTES. Every operation re-authenticates the exact
retained action through the protected journal. `landed` derives the complete scope
from the forge and the reference clone. `publish` recomputes the inverse itself
against the forge's current head and refuses a request that is not exactly that
inverse; a moved head answers `head-moved` with no effect, so the caller
recomputes with the same immutable action. `conflict` proves the overlap is
genuine before the journal records the owned rollback-conflict.

EXACTLY ONE REVERT PER ACTION. A publication attempt is reserved durably before
any forge call and its commit is recorded before master is asked to move, so a
repeated `publish` after a timeout or restart resolves the recorded commit rather
than minting another, and returns the original merge receipt once it landed.
`lookup` answers `absent` only when no effect is possible, and `reserved` (a
refusal the client raises on) while an earlier attempt may still have landed.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from typing import Any, cast

from livespec_dev_tooling._incident_inverse_types import (
    InverseConflictRequest,
    InversePublishRequest,
)
from livespec_dev_tooling._incident_observer_store import save_record
from livespec_dev_tooling._incident_observer_types import RecoveryIntent
from livespec_dev_tooling._incident_recovery_effects import RecoveryEffects
from livespec_dev_tooling._incident_recovery_journal_identity import JournalCodec
from livespec_dev_tooling._incident_recovery_journal_values import JournalValues
from livespec_dev_tooling._incident_recovery_publication import (
    Publication,
    PublicationAttempt,
    PublicationLedger,
)
from livespec_dev_tooling._incident_recovery_publisher import Publisher, Replies
from livespec_dev_tooling.incident_controller_installation import ControllerInstallation
from livespec_dev_tooling.incident_recovery_app import AppRefusal, RecoveryForge
from livespec_dev_tooling.incident_recovery_journal import JournalResult, RecoveryJournal

__all__: list[str] = ["RecoveryPrincipal"]

_BRANCH = "master"
Reply = dict[str, Any]
_refused = Replies.refused


@dataclass(frozen=True, kw_only=True)
class RecoveryPrincipal:
    """The protected installation, and the recovery App identity resolved on first use."""

    installation: ControllerInstallation
    connect: Callable[[], RecoveryForge | AppRefusal]

    @staticmethod
    def refusal(*, reason: str, code: str = "recovery-principal-refused") -> Reply:
        """A named refusal; every principal reply keeps current-effect authority false."""
        return _refused(reason=reason, code=code)

    def effects(self) -> RecoveryEffects | Reply:
        forge = self.connect()
        if isinstance(forge, AppRefusal):
            return _refused(reason=forge.detail, code=forge.code)
        return RecoveryEffects(forge=forge, root=self.installation.repo, branch=_BRANCH)

    def landed(self, *, payload: Reply) -> Reply:
        intent = JournalCodec.intent(raw=payload["intent"])
        if self._journal(intent=intent).status in {"refused", "unavailable"}:
            return _refused(reason="exact retained recovery action required")
        effects = self.effects()
        if isinstance(effects, dict):
            return effects
        scope = effects.landed(intent=intent)
        if scope is None:
            return _refused(reason="authenticated complete landed pull scope unavailable")
        return {"status": "observed", "scope": JournalCodec.wire(value=asdict(scope))}

    def authorize(self, *, payload: Reply) -> Reply:
        intent = JournalCodec.intent(raw=payload["intent"])
        scope = JournalValues.scope(raw=payload["scope"])
        if self._journal(intent=intent).status != "absent":
            return _refused(reason="only a pending action with no recorded effect is authorized")
        if not JournalValues.scope_matches(scope=scope, intent=intent):
            return _refused(reason="scope is not bound to the retained grant")
        effects = self.effects()
        if isinstance(effects, dict):
            return effects
        return {"authorized": effects.landed(intent=intent) == scope}

    def head(self, *, payload: Reply) -> Reply:
        if (payload["repository"], payload["branch"]) != (self.installation.repository, _BRANCH):
            return _refused(reason="only the observed repository's master is readable")
        effects = self.effects()
        if isinstance(effects, dict):
            return effects
        head = effects.head()
        return _refused(reason="master head unavailable") if head is None else {"head": head}

    def lookup(self, *, payload: Reply) -> Reply:
        intent = JournalCodec.intent(raw=payload["intent"])
        journal = self._journal(intent=intent)
        if journal.status in {"refused", "recorded", "reserved"}:
            return asdict(journal)
        ledger = self._ledger()
        with ledger.hold(action_id=intent.action_id):
            publication = ledger.load(action_id=intent.action_id)
            if publication.receipt is None and publication.open_attempt is not None:
                publication = self._settled(publication=publication)
                ledger.save(publication=publication)
        if publication.receipt is not None:
            return Replies.recorded(receipt=publication.receipt)
        if publication.open_attempt is not None:
            return Replies.reserved()
        return asdict(journal)

    def publish(self, *, payload: Reply) -> Reply:
        request = cast(
            "InversePublishRequest",
            JournalCodec.request(operation="reserve", raw=payload["request"]),
        )
        intent = request.intent
        if f"Incident-Action: {intent.action_id}" not in request.message.splitlines():
            return _refused(reason="the revert message must name its exact action")
        effects = self.effects()
        if isinstance(effects, dict):
            return effects
        digest = hashlib.sha256(JournalCodec.canonical(value=payload["request"])).hexdigest()
        ledger = self._ledger()
        with ledger.hold(action_id=intent.action_id):
            publication = ledger.load(action_id=intent.action_id)
            if publication.receipt is None and publication.open_attempt is not None:
                publication = self._settled(publication=publication, effects=effects)
                ledger.save(publication=publication)
            publisher = Publisher(journal=self._recovery_journal(), effects=effects, ledger=ledger)
            return publisher.resume(publication=publication, request=request, digest=digest)

    def conflict(self, *, payload: Reply) -> Reply:
        request = cast(
            "InverseConflictRequest",
            JournalCodec.request(operation="conflict", raw=payload["request"]),
        )
        effects = self.effects()
        if isinstance(effects, dict):
            return effects
        ledger = self._ledger()
        with ledger.hold(action_id=request.intent.action_id):
            publication = ledger.load(action_id=request.intent.action_id)
            if publication.receipt is not None or publication.open_attempt is not None:
                return _refused(reason="a publication for this action exists or is unresolved")
            if effects.landed(intent=request.intent) != request.scope:
                return _refused(reason="conflict scope is not the forge's landed scope")
            if not effects.overlaps(scope=request.scope, head=request.expected_head):
                return _refused(reason="no genuine overlap with later work at that head")
            context = self.installation.state / "recovery-journal-contexts"
            path = context / f"{request.intent.action_id}.json"
            if not path.exists():
                wire = JournalCodec.wire(value=asdict(request))
                save_record(path=path, record={"schema": 1, "request": wire})
            return asdict(self._recovery_journal().record_conflict(request=request))

    def _recovery_journal(self) -> RecoveryJournal:
        return RecoveryJournal(installation=self.installation)

    def _journal(self, *, intent: RecoveryIntent) -> JournalResult:
        return self._recovery_journal().lookup(intent=intent)

    def _ledger(self) -> PublicationLedger:
        return PublicationLedger(directory=self.installation.state / "recovery-journal")

    def _settled(
        self, *, publication: Publication, effects: RecoveryEffects | Reply | None = None
    ) -> Publication:
        """Resolve an open attempt: a commitless one never moved master; else ask the forge."""
        attempt = cast("PublicationAttempt", publication.open_attempt)
        if attempt.commit is None:
            return publication.with_attempt(attempt=replace(attempt, status="abandoned"))
        resolved = self.effects() if effects is None else effects
        return (
            publication if isinstance(resolved, dict) else resolved.settle(publication=publication)
        )
