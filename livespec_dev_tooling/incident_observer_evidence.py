"""Refuse an expedited arm whose exact head tree lacks complete, disposed focused evidence.

`/arm` is the last point before an expedited merge: the expedited PR policy
applies only while an arm stands, so this is where the ratified pre-merge
obligation is enforced (SPECIFICATION `contracts.md`, the expedited incident
execution contract: focused verification, one manual reproduction, and an
operator disposition for incomplete evidence; "a failing assertion requires
repair").

The gate reads only through the host-provisioned canonical reader's
`read-local-gates` and the observer's own read-only forge credential. The head
commit's tree comes from the forge, never from the request. Every evidence slot
for that identity, head and tree is read, so a caller cannot pick which record
is judged. Anything the gate cannot read refuses: there is no fallback to
admission.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.pipeline import is_successful  # noqa: E402 — vendor-path-aware import.

from livespec_dev_tooling._incident_observer_types import ObserverArm  # noqa: E402
from livespec_dev_tooling.incident_authority_client import call_authority  # noqa: E402
from livespec_dev_tooling.incident_focused_admission import (  # noqa: E402
    MAX_EVIDENCE_SLOTS,
    EvidenceReview,
    EvidenceSubject,
    disposition_matches,
    disposition_receipt_id,
    evidence_receipt_id,
    review_record,
)
from livespec_dev_tooling.incident_forge_reads import ForgeRead  # noqa: E402

__all__: list[str] = ["FocusedEvidenceGate"]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-4aksht
_ABSENT = "incident-focused-evidence-absent"
_UNAVAILABLE = "incident-focused-evidence-unavailable"
_MISSING = "incident-focused-evidence-member-missing"
_FAILED = "incident-focused-evidence-failed"
_UNDISPOSED = "incident-focused-evidence-undisposed"
_SHA = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})")
_CHECKSUM = re.compile(r"sha256:[0-9a-f]{64}")

# One `read-local-gates` answer: (receipt, checksum) when recorded, None when absent.
_Lookup = tuple[dict[str, Any], str] | None


class _UnreadableError(Exception):
    """A read the gate cannot establish; it refuses rather than admits."""


@dataclass(frozen=True, kw_only=True)
class FocusedEvidenceGate:
    """`None` admits the arm; any other answer is the named refusal."""

    command: tuple[str, ...]
    repo: Path
    release: str
    installed_reader_approved: Callable[[str, tuple[str, ...]], bool]
    read: ForgeRead

    def __call__(self, arm: ObserverArm) -> str | None:
        if not self.command or not self.installed_reader_approved(self.release, self.command):
            return f"{_UNAVAILABLE}: the canonical reader is not the approved installation"
        tree = self._head_tree(arm=arm)
        if tree is None:
            return f"{_UNAVAILABLE}: the forge does not answer the tree of head {arm.head_sha}"
        subject = EvidenceSubject(
            repository=arm.repository,
            item=arm.incident_item_id,
            attempt=arm.attempt_id,
            operation=arm.operation_id,
            generation=arm.generation,
            head=arm.head_sha,
            tree=tree,
        )
        try:
            return self._judge(arm=arm, subject=subject)
        except _UnreadableError as unreadable:
            return f"{_UNAVAILABLE}: {unreadable}"

    def _head_tree(self, *, arm: ObserverArm) -> str | None:
        commit = self.read(f"repos/{arm.repository}/git/commits/{arm.head_sha}")
        value = cast("dict[str, Any]", commit) if isinstance(commit, dict) else {}
        tree = value.get("tree")
        sha = cast("dict[str, Any]", tree).get("sha") if isinstance(tree, dict) else None
        if value.get("sha") != arm.head_sha or not isinstance(sha, str) or not _SHA.fullmatch(sha):
            return None
        return sha

    def _judge(self, *, arm: ObserverArm, subject: EvidenceSubject) -> str | None:
        records: list[tuple[str, dict[str, Any], str]] = []
        for slot in range(MAX_EVIDENCE_SLOTS):
            receipt_id = evidence_receipt_id(subject=subject, slot=slot)
            found = self._lookup(arm=arm, receipt_id=receipt_id)
            if found is None:
                break
            records.append((receipt_id, *found))
        if not records:
            return (
                f"{_ABSENT}: incident {arm.incident_item_id} carries no focused-evidence record"
                f" for head tree {subject.tree} (PR #{arm.pr_number} head {arm.head_sha})"
            )
        reviews: list[EvidenceReview] = []
        for receipt_id, receipt, _ in records:
            review = review_record(receipt=receipt, subject=subject)
            if review is None:
                message = f"record {receipt_id} does not bind head tree {subject.tree}"
                raise _UnreadableError(message)
            reviews.append(review)
        for (receipt_id, _, _), review in zip(records, reviews, strict=True):
            if review.failed:
                return (
                    f"{_FAILED}: {', '.join(review.failed)} failed in record {receipt_id} for"
                    f" head tree {subject.tree}; a failing assertion requires repair, whatever"
                    " disposition is recorded"
                )
        receipt_id, _, checksum = records[-1]
        latest = reviews[-1]
        if latest.missing:
            return (
                f"{_MISSING}: record {receipt_id} for head tree {subject.tree} lacks"
                f" {'; '.join(latest.missing)}"
            )
        undisposed = [
            member
            for member in latest.members
            if not self._disposed(
                arm=arm, subject=subject, receipt_id=receipt_id, checksum=checksum, member=member
            )
        ]
        if undisposed:
            return (
                f"{_UNDISPOSED}: record {receipt_id} for head tree {subject.tree} has no operator"
                f" risk disposition for: {'; '.join(undisposed)}"
            )
        return None

    def _disposed(
        self,
        *,
        arm: ObserverArm,
        subject: EvidenceSubject,
        receipt_id: str,
        checksum: str,
        member: str,
    ) -> bool:
        disposition_id = disposition_receipt_id(evidence_receipt_id=receipt_id, member=member)
        found = self._lookup(arm=arm, receipt_id=disposition_id)
        if found is None:
            return False
        if not disposition_matches(
            receipt=found[0],
            evidence_receipt_id=receipt_id,
            evidence_checksum=checksum,
            member=member,
            tree=subject.tree,
        ):
            message = f"disposition {disposition_id} does not bind record {receipt_id}"
            raise _UnreadableError(message)
        return True

    def _lookup(self, *, arm: ObserverArm, receipt_id: str) -> _Lookup:
        flags = {
            "repo": str(self.repo),
            "repository": arm.repository,
            "item": arm.incident_item_id,
            "attempt": arm.attempt_id,
            "phase": arm.phase,
            "operation": arm.operation_id,
            "generation": str(arm.generation),
            "owner": arm.owner,
            "receipt-id": receipt_id,
        }
        checked = call_authority(
            command=self.command, action="read-local-gates", flags=flags, cwd=self.repo
        )
        if not is_successful(checked):
            refusal = checked.failure()
            message = f"read-local-gates {receipt_id} refused {refusal.code}: {refusal.detail}"
            raise _UnreadableError(message)
        result = checked.unwrap()
        receipt, checksum = result.get("receipt"), result.get("checksum")
        if result.get("receipt_id") == receipt_id and result.get("status") == "absent":
            if receipt is None and checksum is None:
                return None
        elif (
            result.get("receipt_id") == receipt_id
            and result.get("status") == "recorded"
            and isinstance(receipt, dict)
            and cast("dict[str, Any]", receipt).get("receipt_id") == receipt_id
            and isinstance(checksum, str)
            and _CHECKSUM.fullmatch(checksum)
        ):
            return cast("dict[str, Any]", receipt), checksum
        message = f"read-local-gates {receipt_id} answered a malformed lookup"
        raise _UnreadableError(message)
