"""Shared-lock entrance for queued release and pin adoption effects."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

from livespec_dev_tooling._incident_observer_store import (
    load_record,
    read_registration,
    repository_lock,
    save_record,
)
from livespec_dev_tooling._incident_observer_types import ObserverRegistration
from livespec_dev_tooling._incident_release_effects import call_effect
from livespec_dev_tooling._incident_release_types import (
    ReleaseAttribution,
    ReleaseLookup,
    ReleaseResult,
    _digest,
    _fenced,
    _mapping,
    _object,
    _receipt,
    _registration,
    _valid,
)

__all__: list[str] = ["QueuedAdoption"]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-vg36aq


@dataclass(frozen=True, kw_only=True)
class QueuedAdoption:
    """Provisioned effect capabilities; no candidate JSON or mutable defaults."""

    directory: Path
    authorize_current: Callable[[ObserverRegistration], bool]
    verify_attribution: Callable[[ObserverRegistration, ReleaseAttribution], bool]
    verify_queued: Callable[[ObserverRegistration, ReleaseAttribution], bool] | None
    lookup_effect: Callable[[str, str], ReleaseLookup] | None

    def run(
        self,
        *,
        registration: ObserverRegistration,
        attribution: ReleaseAttribution,
        publish: Callable[[ReleaseAttribution, str], str],
    ) -> ReleaseResult:
        """Fence actual publication under the observer lock and retain exact intent."""
        if (
            not _valid(registration=registration, attribution=attribution, allow_uninstalled=True)
            or not self.authorize_current(registration)
            or not self._queued_verified(registration=registration, attribution=attribution)
        ):
            return ReleaseResult(status="refused")
        identity = _digest(value=(_registration(registration=registration), asdict(attribution)))
        with repository_lock(directory=self.directory, repository=registration.repository) as path:
            record = load_record(path=path)
            if not self._current(path=path, registration=registration):
                return ReleaseResult(status="fenced")
            entries = _mapping(record=record, field="release_adoption_intents")
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
                return ReleaseResult(status="published", receipt=prior)

            def publish_current() -> str:
                if not self._current(path=path, registration=registration):
                    return ""
                return publish(attribution, identity)

            receipt = call_effect(
                operation="adopt",
                identity=identity,
                fresh=fresh,
                lookup_effect=self.lookup_effect,
                perform=publish_current,
            )
            if not isinstance(receipt, str) or not receipt:
                return ReleaseResult(
                    status="pending"
                    if self._current(path=path, registration=registration)
                    else "fenced"
                )
            # Lookup may have observed an old completed effect. Keep its exact
            # receipt even if its current generation can no longer acknowledge it.
            record = load_record(path=path)
            entry = _mapping(record=record, field="release_adoption_intents")[identity]
            _object(value=entry)["receipt"] = receipt
            save_record(path=path, record=record)
            current = self._current(path=path, registration=registration)
            return ReleaseResult(status="published" if current else "fenced", receipt=receipt)

    def _queued_verified(
        self, *, registration: ObserverRegistration, attribution: ReleaseAttribution
    ) -> bool:
        if self.verify_queued is not None:
            return self.verify_queued(registration, attribution)
        # A retained installed identity can be replayed by the existing verifier.
        # FIRST publication requires its distinct pre-effect capability and does
        # not invent a future installation receipt to satisfy that verifier.
        return bool(attribution.installation_receipt) and self.verify_attribution(
            registration, attribution
        )

    def _current(self, *, path: Path, registration: ObserverRegistration) -> bool:
        if not self.authorize_current(registration):
            return False
        record = load_record(path=path)
        return read_registration(record=record) == registration and not _fenced(
            record=record, registration=registration
        )
