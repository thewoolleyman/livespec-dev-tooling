"""The recovery principal's publication flow: one verified revert per action.

`RecoveryPrincipal.publish` resolves any open attempt from forge facts under the
per-action lock, then hands the exact request here. This module returns the
original receipt when the action already merged, re-sends the one recorded
commit when an attempt is still open, or starts a new attempt: it re-reads the
forge head (a moved head is `head-moved`, no effect), recomputes the complete
inverse itself and refuses any request that is not exactly that inverse,
reserves the attempt durably, creates the verified commit, records it, and only
then asks master to move.
"""

from __future__ import annotations

import sys
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, cast

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.pipeline import is_successful  # noqa: E402 — vendor-path-aware import.
from returns.unsafe import unsafe_perform_io  # noqa: E402

from livespec_dev_tooling._incident_inverse_types import InversePublishRequest  # noqa: E402
from livespec_dev_tooling._incident_recovery_effects import RecoveryEffects  # noqa: E402
from livespec_dev_tooling._incident_recovery_publication import (  # noqa: E402
    Publication,
    PublicationAttempt,
    PublicationLedger,
    PublicationReceipt,
)
from livespec_dev_tooling.incident_inverse import plan_incident_inverse  # noqa: E402
from livespec_dev_tooling.incident_recovery_journal import RecoveryJournal  # noqa: E402

__all__: list[str] = ["Publisher", "Replies"]

Reply = dict[str, Any]


class Replies:
    """The principal's reply shapes; none ever authorizes a current effect."""

    @staticmethod
    def refused(*, reason: str, code: str = "recovery-principal-refused") -> Reply:
        return {
            "status": "refused",
            "code": code,
            "reason": reason,
            "authorizes_current_effects": False,
        }

    @staticmethod
    def committed(*, receipt: PublicationReceipt) -> Reply:
        return {"status": "committed", **asdict(receipt)}

    @staticmethod
    def recorded(*, receipt: PublicationReceipt) -> Reply:
        return {"status": "recorded", "reason": "exact merged recovery inverse", **asdict(receipt)}

    @staticmethod
    def reserved() -> Reply:
        return {
            "status": "reserved",
            "reason": "an earlier publication attempt may have landed; its outcome is unresolved",
        }


@dataclass(frozen=True, kw_only=True)
class Publisher:
    """One publish request, under the per-action lock the caller already holds."""

    journal: RecoveryJournal
    effects: RecoveryEffects
    ledger: PublicationLedger

    def resume(
        self, *, publication: Publication, request: InversePublishRequest, digest: str
    ) -> Reply:
        """Return the original receipt, re-send the recorded commit, or start an attempt."""
        attempt = publication.open_attempt
        if publication.receipt is not None:
            return Replies.committed(receipt=publication.receipt)
        if attempt is not None and attempt.request_sha256 != digest:
            return Replies.refused(reason="an earlier attempt for this action is unresolved")
        if attempt is not None:
            return self._advance(publication=publication)
        if self.journal.lookup(intent=request.intent).status != "absent":
            return Replies.refused(reason="the retained action already has another effect")
        return self._attempt(publication=publication, request=request, digest=digest)

    def _attempt(
        self, *, publication: Publication, request: InversePublishRequest, digest: str
    ) -> Reply:
        head, expected = self.effects.head(), request.plan.expected_head
        if head != expected:
            return {"status": "head-moved", "head": head}
        if self.effects.landed(intent=request.intent) != request.plan.scope:
            return Replies.refused(reason="request scope is not the forge's landed scope")
        planned = plan_incident_inverse(
            repo_root=self.effects.root, scope=request.plan.scope, expected_head=expected
        )
        if not is_successful(planned) or unsafe_perform_io(planned.unwrap()) != request.plan:
            return Replies.refused(
                reason="request is not the exact complete inverse against master"
            )
        attempt = PublicationAttempt(
            request_sha256=digest,
            expected_head=expected,
            tree_sha=request.plan.tree_sha,
            status="reserved",
        )
        publication = publication.with_attempt(attempt=attempt)
        self.ledger.save(publication=publication)
        commit = self.effects.prepare(plan=request.plan, message=request.message)
        status = "abandoned" if commit is None else "prepared"
        publication = publication.with_attempt(
            attempt=replace(attempt, status=status, commit=commit)
        )
        self.ledger.save(publication=publication)
        if commit is None:
            return Replies.refused(reason="the forge did not reproduce the exact inverse tree")
        return self._advance(publication=publication)

    def _advance(self, *, publication: Publication) -> Reply:
        attempt = cast("PublicationAttempt", publication.open_attempt)
        commit = cast("str", attempt.commit)
        outcome = self.effects.advance(commit=commit)
        if outcome == "moved":
            publication = publication.committed(merge_sha=commit, tree_sha=attempt.tree_sha)
        elif outcome == "rejected":
            publication = self.effects.settle(publication=publication)
        self.ledger.save(publication=publication)
        if publication.receipt is not None:
            return Replies.committed(receipt=publication.receipt)
        if publication.open_attempt is None:
            return {"status": "head-moved"}
        return {"status": "unknown", "reason": "master update unobserved; commit retained"}
