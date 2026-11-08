"""Retain release attribution and fence affected consumer adoption."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

from livespec_dev_tooling._incident_observer_store import (
    load_record,
    read_registration,
    repository_lock,
    save_record,
)
from livespec_dev_tooling._incident_observer_types import ObserverRegistration, RecoveryIntent
from livespec_dev_tooling._incident_release_adoption import QueuedAdoption
from livespec_dev_tooling._incident_release_effects import (
    call_effect,
    publish_receipt,
    recover_attribution,
    release_result,
)
from livespec_dev_tooling._incident_release_types import (
    ReleaseAttribution,
    ReleaseLookup,
    ReleaseResult,
    _attributions,
    _digest,
    _fenced,
    _mapping,
    _object,
    _receipt,
    _registration,
    _valid,
)

__all__: list[str] = [
    "IncidentReleaseRecovery",
    "ReleaseAttribution",
    "ReleaseLookup",
    "ReleaseResult",
]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-vg36aq


@dataclass(frozen=True, kw_only=True)
class IncidentReleaseRecovery:
    """Use the observer's existing independent record and canonical writer seams.

    authorize_current is the existing CurrentAuthorityReader. The provisioned
    verify_attribution authenticates source membership in the COMPLETE retained
    canonical landed chain, tag/image digest, pin carrier and installed receipt;
    callers must not equate the source with only the terminal landed SHA.
    Canonical effect adapters authenticate operation+payload, durably deduplicate
    by the supplied identity, and return only a VERIFIED exact effect receipt.
    A service's arbitrary nonempty reply is never this adapter contract. Lookup
    similarly authenticates operation and identity before constructing its value.
    """

    directory: Path
    authorize_current: Callable[[ObserverRegistration], bool]
    verify_attribution: Callable[[ObserverRegistration, ReleaseAttribution], bool]
    record_canonical: Callable[[ObserverRegistration, ReleaseAttribution, str], str]
    recover_canonical: Callable[[RecoveryIntent, tuple[ReleaseAttribution, ...], str], str]
    reopen_canonical: Callable[[ObserverRegistration, str, str, str], str]
    lookup_effect: Callable[[str, str], ReleaseLookup] | None = None
    verify_queued: Callable[[ObserverRegistration, ReleaseAttribution], bool] | None = None
    verify_compensation: Callable[[ObserverRegistration, ReleaseAttribution], bool] | None = None

    def run_queued_adoption(
        self,
        *,
        registration: ObserverRegistration,
        attribution: ReleaseAttribution,
        publish: Callable[[ReleaseAttribution, str], str],
    ) -> ReleaseResult:
        """The release/pin dispatch entrance, immediately before adoption effects.

        Publish is an independently provisioned idempotent effect capability:
        repeated identity recovers its exact result after timeout. It must not
        invoke this controller recursively while the repository lock is held.
        """
        if not self._compensation_verified(registration=registration, attribution=attribution):
            return ReleaseResult(status="refused")
        return release_result(
            function=lambda: QueuedAdoption(
                directory=self.directory,
                authorize_current=self.authorize_current,
                verify_attribution=self.verify_attribution,
                verify_queued=self.verify_queued,
                lookup_effect=self.lookup_effect,
            ).run(registration=registration, attribution=attribution, publish=publish)
        )

    def acknowledge_adoption(
        self, *, registration: ObserverRegistration, attribution: ReleaseAttribution
    ) -> ReleaseResult:
        """Retain verified source/artifact/consumer identity before canonical ack.

        The release dispatcher supplies authenticated artifact/install receipts,
        not labels or incident JSON. Canonical verification and publication are
        host-provisioned capabilities. Unknown outcomes stay retained for retry.
        """
        return release_result(
            function=lambda: self._acknowledge(registration=registration, attribution=attribution)
        )

    def _acknowledge(
        self, *, registration: ObserverRegistration, attribution: ReleaseAttribution
    ) -> ReleaseResult:
        if (
            not self._compensation_verified(registration=registration, attribution=attribution)
            or not _valid(registration=registration, attribution=attribution)
            or not self.verify_attribution(registration, attribution)
        ):
            return ReleaseResult(status="refused")
        current = self.authorize_current(registration)
        identity = _digest(value=(_registration(registration=registration), asdict(attribution)))
        with repository_lock(directory=self.directory, repository=registration.repository) as path:
            record = load_record(path=path)
            fenced = (
                not current
                or read_registration(record=record) != registration
                or _fenced(record=record, registration=registration)
            )
            entries = _mapping(record=record, field="release_attribution")
            fresh = identity not in entries
            entry = entries.setdefault(
                identity,
                {
                    "registration": _registration(registration=registration),
                    "attribution": asdict(attribution),
                    "receipt": "",
                },
            )
            save_record(path=path, record=record)
            prior = _receipt(value=entry)
        if prior:
            return ReleaseResult(status="fenced" if fenced else "acknowledged", receipt=prior)
        receipt = call_effect(
            operation="acknowledge",
            identity=identity,
            fresh=fresh,
            lookup_effect=self.lookup_effect,
            perform=lambda: self.record_canonical(registration, attribution, identity),
        )
        if not isinstance(receipt, str) or not receipt:
            return ReleaseResult(status="pending")
        # The callback must perform its own canonical CAS. Rechecking the local
        # independent fence prevents its old result acknowledging a later revert.
        with repository_lock(directory=self.directory, repository=registration.repository) as path:
            record = load_record(path=path)
            fenced = (
                fenced
                or read_registration(record=record) != registration
                or _fenced(record=record, registration=registration)
            )
            entry = _mapping(record=record, field="release_attribution")[identity]
            _object(value=entry)["receipt"] = receipt
            save_record(path=path, record=record)
        return ReleaseResult(status="fenced" if fenced else "acknowledged", receipt=receipt)

    def _compensation_verified(
        self, *, registration: ObserverRegistration, attribution: ReleaseAttribution
    ) -> bool:
        """Require a provisioned verifier for irreversible release compensation."""
        return not attribution.irreversible or (
            self.verify_compensation is not None
            and self.verify_compensation(registration, attribution)
        )

    def recover(self, *, intent: RecoveryIntent) -> ReleaseResult:
        """Reconcile consumers after observer's exact inverse receipt, outside its lock.

        The observer's persisted recovery intent fences adoption immediately,
        including while tenant publication is unavailable. This method runs after
        the observer callback has returned, not recursively inside its lock.
        """
        return release_result(function=lambda: self._recover(intent=intent))

    def _recover(self, *, intent: RecoveryIntent) -> ReleaseResult:
        registration = intent.registration
        with repository_lock(directory=self.directory, repository=registration.repository) as path:
            record = load_record(path=path)
            action = _object(value=_mapping(record=record, field="actions").get(intent.action_id))
            if action.get("registration") != _registration(registration=registration):
                return ReleaseResult(status="refused")
            inverse_receipt = _receipt(value=action)
            if action.get("status") != "completed" or not inverse_receipt:
                return ReleaseResult(status="pending")
            attributed = _attributions(record=record, registration=registration)
        if not attributed:
            return ReleaseResult(status="refused")
        receipts: list[str] = []
        for attribution in attributed:
            result = recover_attribution(
                directory=self.directory,
                intent=intent,
                attribution=attribution,
                inverse_receipt=inverse_receipt,
                recover_canonical=self.recover_canonical,
                lookup_effect=self.lookup_effect,
            )
            if result.status != "reconciled":
                return result
            receipts.append(result.receipt)
        return ReleaseResult(status="reconciled", receipt=json.dumps(receipts))

    def reopen(
        self, *, registration: ObserverRegistration, regression_id: str, evidence: str
    ) -> ReleaseResult:
        """Fence cleanup and ask canonical lifecycle to reopen the SAME incident.

        Canonical CAS authenticates the actual attribution and permits closed
        history; this controller never changes phase or invents a generation.
        """
        return release_result(
            function=lambda: self._reopen(
                registration=registration, regression_id=regression_id, evidence=evidence
            )
        )

    def _reopen(
        self, *, registration: ObserverRegistration, regression_id: str, evidence: str
    ) -> ReleaseResult:
        if not regression_id or not evidence:
            return ReleaseResult(status="refused")
        with repository_lock(directory=self.directory, repository=registration.repository) as path:
            record = load_record(path=path)
            if not _attributions(record=record, registration=registration):
                return ReleaseResult(status="refused")
            identity = _digest(
                value=(_registration(registration=registration), regression_id, evidence)
            )
            entries = _mapping(record=record, field="release_regressions")
            fresh = identity not in entries
            entry = entries.setdefault(
                identity,
                {
                    "registration": _registration(registration=registration),
                    "regression_id": regression_id,
                    "evidence": evidence,
                    "receipt": "",
                },
            )
            save_record(path=path, record=record)
            prior = _receipt(value=entry)
        if prior:
            return ReleaseResult(status="reopened", receipt=prior)
        receipt = call_effect(
            operation="reopen",
            identity=identity,
            fresh=fresh,
            lookup_effect=self.lookup_effect,
            perform=lambda: self.reopen_canonical(registration, regression_id, evidence, identity),
        )
        return publish_receipt(
            directory=self.directory,
            registration=registration,
            field="release_regressions",
            identity=identity,
            receipt=receipt,
            status="reopened",
        )
