"""Authenticated durable recovery effects without granting forge authority."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from livespec_dev_tooling._incident_inverse_types import (
    InverseConflictRequest,
    InversePublishRequest,
)
from livespec_dev_tooling._incident_observer_types import RecoveryIntent
from livespec_dev_tooling._incident_recovery_journal_identity import JournalCodec
from livespec_dev_tooling._incident_recovery_journal_io import JournalStore
from livespec_dev_tooling._incident_recovery_journal_types import JournalResult
from livespec_dev_tooling.incident_controller_installation import ControllerInstallation

__all__: list[str] = ["JournalResult", "RecoveryJournal"]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-dln3ac


@dataclass(frozen=True, kw_only=True)
class RecoveryJournal:
    """Use only settings loaded by the independent protected installation.

    Reservation is library-only and records unknown effect ownership, not an
    effect or mutation grant. The executable exposes only lookup and conflict.
    """

    installation: ControllerInstallation

    def _bound(self, *, intent: RecoveryIntent) -> None:
        """Refuse an action registered for any branch but the configured target branch."""
        if intent.registration.branch != self.installation.target_branch:
            message = "action is not registered for the configured target branch"
            raise ValueError(message)

    def lookup(self, *, intent: RecoveryIntent) -> JournalResult:
        """Observe an exact retained action; corruption never becomes absence."""
        try:
            exact = JournalCodec.intent(raw=JournalCodec.wire(value=asdict(intent)))
            self._bound(intent=exact)
        except (ValueError, TypeError, KeyError, RecursionError):
            return JournalResult(status="refused", reason="invalid exact recovery intent")
        return JournalStore(installation=self.installation).perform(
            operation="lookup", intent=exact
        )

    def reserve(self, *, request: InversePublishRequest) -> JournalResult:
        """Durably reserve exact bytes for a future independently authorized publisher."""
        return self._write(operation="reserve", request=request)

    def record_conflict(self, *, request: InverseConflictRequest) -> JournalResult:
        """Persist only the independently pre-authenticated complete conflict context."""
        return self._write(operation="conflict", request=request)

    def _write(
        self, *, operation: str, request: InversePublishRequest | InverseConflictRequest
    ) -> JournalResult:
        try:
            raw = JournalCodec.wire(value=asdict(request))
            exact = JournalCodec.request(operation=operation, raw=raw)
            self._bound(intent=exact.intent)
        except (ValueError, TypeError, KeyError, RecursionError):
            return JournalResult(status="refused", reason="invalid exact recovery effect request")
        return JournalStore(installation=self.installation).perform(
            operation=operation, intent=exact.intent, request=raw
        )
