"""Retain evidence in the independent controller; canonical writers own lifecycle."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import cast

from livespec_dev_tooling._incident_observer_store import (
    load_record,
    repository_lock,
    save_record,
)
from livespec_dev_tooling._incident_run_types import (
    CorrectedAttempt,
    EvidenceRefusal,
    OriginalRun,
    RunEvidence,
    RunSnapshot,
)
from livespec_dev_tooling.incident_run_evidence import (
    build_run_evidence,
    evidence_digest,
    validate_correction,
)

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))
from returns.io import impure_safe  # noqa: E402
from returns.pipeline import is_successful  # noqa: E402
from returns.unsafe import unsafe_perform_io  # noqa: E402

__all__: list[str] = ["CanonicalRunAdapter", "OriginalRunCollector"]
_INVALID_RECEIPTS = "invalid controller evidence receipts"
_CONFLICTING_EVIDENCE = "conflicting immutable original-run evidence"

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-kobmka


@dataclass(frozen=True, kw_only=True)
class CanonicalRunAdapter:
    """Host-provisioned canonical capability, never a mutable JSON authority.

    authorize authenticates the retained original identity and expected graph.
    record is idempotent by evidence digest. correct MUST authenticate actual
    repair/resolution evidence, CAS the current generation, preserve history and
    refuse closed/foreign items. The collector cannot emulate those operations.
    """

    authorize: Callable[[OriginalRun], bool]
    record: Callable[[RunEvidence, str], str]
    correct: Callable[[CorrectedAttempt, str], str]


def _refuse(*, detail: str) -> EvidenceRefusal:
    return EvidenceRefusal(code="incident-original-run-refused", detail=detail)


@impure_safe
def _call(*, function: Callable[[], object]) -> object:
    return function()


@dataclass(frozen=True, kw_only=True)
class OriginalRunCollector:
    """Controller-side evidence retention, not a second attempt/phase store.

    Network collection happens OUTSIDE the repository action lock, so a slow
    provider cannot delay the first-failure inverse. This uses the observer's
    existing independent controller record and preserves every foreign field.
    """

    directory: Path
    read: Callable[[OriginalRun], RunSnapshot | EvidenceRefusal]
    canonical: CanonicalRunAdapter

    def collect(
        self, *, original: OriginalRun, continuation_id: str
    ) -> RunEvidence | EvidenceRefusal:
        authorized = _call(function=lambda: self.canonical.authorize(original))
        if not is_successful(authorized) or unsafe_perform_io(authorized.unwrap()) is not True:
            return _refuse(detail="retained original-run authority unavailable")
        read = _call(function=lambda: self.read(original))
        if not is_successful(read):
            return _refuse(detail="original-run provider unavailable; original receipts retained")
        snapshot = unsafe_perform_io(read.unwrap())
        if isinstance(snapshot, EvidenceRefusal):
            return snapshot
        return self._collect_snapshot(
            original=original,
            snapshot=cast("RunSnapshot", snapshot),
            continuation_id=continuation_id,
        )

    def _collect_snapshot(
        self, *, original: OriginalRun, snapshot: RunSnapshot, continuation_id: str
    ) -> RunEvidence | EvidenceRefusal:
        evidence = build_run_evidence(
            original=original, snapshot=snapshot, continuation_id=continuation_id
        )
        if isinstance(evidence, EvidenceRefusal):
            return evidence
        retained = self._retain(evidence=evidence)
        if not is_successful(retained):
            return _refuse(detail="independent original-run evidence persistence failed")
        digest = evidence_digest(evidence=evidence)
        published = _call(function=lambda: self.canonical.record(evidence, digest))
        if not is_successful(published):
            return _refuse(detail="evidence retained; canonical reconciliation remains owed")
        receipt = unsafe_perform_io(published.unwrap())
        if not isinstance(receipt, str) or not receipt:
            return _refuse(detail="evidence retained; canonical reconciliation remains owed")
        return evidence

    @impure_safe
    def _retain(self, *, evidence: RunEvidence) -> None:
        original = evidence.original
        with repository_lock(directory=self.directory, repository=original.repository) as path:
            record = load_record(path=path)
            existing = record.get("original_run_evidence", {})
            if not isinstance(existing, dict):
                raise TypeError(_INVALID_RECEIPTS)
            observations = cast("dict[str, object]", existing).copy()
            key = evidence_digest(evidence=evidence)
            value: object = json.loads(json.dumps(asdict(evidence)))
            if key in observations and observations[key] != value:
                raise ValueError(_CONFLICTING_EVIDENCE)
            observations[key] = value
            record["original_run_evidence"] = observations
            save_record(path=path, record=record)

    def propose_correction(
        self, *, evidence: RunEvidence, proposal: CorrectedAttempt
    ) -> str | EvidenceRefusal:
        validated = validate_correction(evidence=evidence, proposal=proposal)
        if isinstance(validated, EvidenceRefusal):
            return validated
        # The canonical call authenticates actual diff/resolution receipts and
        # commits its own generation CAS. A timestamp or caller digest cannot.
        published = _call(
            function=lambda: self.canonical.correct(validated, proposal.evidence_digest)
        )
        if not is_successful(published):
            return _refuse(detail="canonical correction unavailable; no local attempt created")
        receipt = unsafe_perform_io(published.unwrap())
        if not isinstance(receipt, str) or not receipt:
            return _refuse(detail="canonical writer supplied no correction receipt")
        return receipt
