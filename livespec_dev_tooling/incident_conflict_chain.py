"""Replay a journaled rollback-conflict onto the canonical incident chain.

`incident_inverse` hands a genuine overlap to the recovery principal, whose durable
result is the recovery journal. The journal is the controller's own record and
stays available when the tenant is not, but it is not the incident item's
lifecycle: only the orchestrator's `record-rollback-conflict` action writes the
`rollback-conflict` phase and the `blocked` status, and it accepts only the
`reverting` generation. This module is that action's one caller in dev-tooling.

A first master failure has not reached `reverting`: the registration names the merged
attempt. The writer therefore calls `reopen-regression` FIRST, with a `trunk` finding
built from the failing leaf and keyed to the immutable recovery action, and records the
conflict on the `reverting` generation that reply names. A regression reopen is already
at `reverting`, so it is named directly.

Both writes go through the manifest's installed canonical reader command by the shared
authority client, the same process `CurrentAuthorityReader` uses, and take nothing from
caller JSON: the orchestrator re-reads the chain and refuses an identity that is not
the generation it acts on. Every payload field is a function of the journaled receipt
and the registration, so a repeat for the same action and head (after a timeout or a
restart) sends byte-identical bytes and the orchestrator recovers its one recorded
transition rather than adding a second. A repeat meets a reopen that is already
recorded, which the orchestrator refuses as a stale observation; the writer then
names the `reverting` generation that reopen produced (the orchestrator's own
`recovery-<digest>` identity) and the chain still verifies it. A reply that does not
prove the transition, or no reply at all, returns False after naming the refusal on
stderr: the conflict stays in the journal and the sweep replays it later.

How the owner's resolution continues: nothing here moves a chain out of
`rollback-conflict`. The orchestrator's `resolve-rollback-conflict` action does, by
the exact `release_condition` this module wrote into the conflict record.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.pipeline import is_successful  # noqa: E402 — vendor-path-aware import.
from returns.result import Result  # noqa: E402 — vendor-path-aware import.

from livespec_dev_tooling._incident_conflict_generation import (  # noqa: E402
    Generation,
    canonical,
    proves_conflict,
    recorded_reopen,
    reopen_reply,
    say,
)
from livespec_dev_tooling._incident_inverse_types import (  # noqa: E402
    InverseConflictRequest,
    InverseForge,
    LandedIncident,
    RecoveryOutcome,
)
from livespec_dev_tooling._incident_observer_types import (  # noqa: E402
    RecoveryIntent,
)
from livespec_dev_tooling.incident_authority_client import (  # noqa: E402
    AuthorityRefusal,
    call_authority,
    report_authority_refusal,
)

__all__: list[str] = [
    "ConflictChain",
    "is_conflict_receipt",
    "record_inverse_conflict",
    "replay_conflict",
]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-fdquen
_CONFLICT_ACTION = "record-rollback-conflict"
_REOPEN_ACTION = "reopen-regression"
_STALE_REOPEN = "incident-reopen-stale-observation"
_REVERTING = "reverting"
_CONFLICT_PHASE = "rollback-conflict"
_BLOCKED = "blocked"
_RECEIPT_PREFIX = "rollback-conflict:"
_TRUNK = "trunk"


def is_conflict_receipt(*, receipt: str | None) -> bool:
    """Whether a recorded receipt is a journaled conflict rather than a revert merge."""
    return receipt is not None and receipt.startswith(_RECEIPT_PREFIX)


def replay_conflict(
    *, intent: RecoveryIntent, receipt: str | None, chain: ConflictChain | None
) -> None:
    """Carry a journaled conflict to the canonical chain; a failed write is retried later.

    The write is idempotent on the chain, so replaying an already-recorded conflict
    adds no transition. The result is deliberately unused: the journal alone decides
    the outcome, and an unreachable tenant must not turn a recorded conflict pending.
    """
    if chain is not None and receipt is not None and is_conflict_receipt(receipt=receipt):
        _ = chain.record(intent=intent, receipt=receipt)


def record_inverse_conflict(
    *,
    intent: RecoveryIntent,
    scope: LandedIncident,
    head: str,
    reason: str,
    forge: InverseForge,
    chain: ConflictChain | None,
) -> RecoveryOutcome:
    """Journal one genuine overlap through the principal, then replay it onto the chain."""
    receipt = forge.record_conflict(
        request=InverseConflictRequest(
            intent=intent,
            scope=scope,
            expected_head=head,
            reason=reason,
            receipt=(
                f"{_RECEIPT_PREFIX}{intent.action_id}:owner:{intent.registration.owner}:head:{head}"
            ),
        )
    )
    replay_conflict(intent=intent, receipt=receipt, chain=chain)
    return RecoveryOutcome(
        status="rollback-conflict" if receipt else "pending",
        reason="overlapping later work requires identified owner resolution",
        receipt=receipt,
    )


@dataclass(frozen=True, kw_only=True)
class ConflictChain:
    """The installed canonical reader as the writer of one owned rollback-conflict."""

    command: tuple[str, ...]
    repo: Path
    release: str
    installed_reader_approved: Callable[[str, tuple[str, ...]], bool] = field(
        compare=False, repr=False
    )

    @classmethod
    def installed(cls, *, command: tuple[str, ...], release: str, repo: Path) -> ConflictChain:
        """The manifest's reader, approved only as exactly that release and command."""
        return cls(
            command=command,
            repo=repo,
            release=release,
            installed_reader_approved=lambda candidate_release, candidate: (
                candidate_release,
                candidate,
            )
            == (release, command),
        )

    def record(self, *, intent: RecoveryIntent, receipt: str) -> bool:
        """True only when the reply proves the conflict is on the chain, blocked."""
        if not self.command or not self.installed_reader_approved(self.release, self.command):
            return False
        reverting = self._reverting(intent=intent)
        if reverting is None:
            return False
        conflict = {
            "receipt": receipt,
            "release_condition": f"the incident owner resolves the later-work overlap: {receipt}",
        }
        checked = self._call(
            action=_CONFLICT_ACTION,
            flags={**reverting.flags(), "rollback-conflict-json": canonical(value=conflict)},
        )
        result = _delivered(checked=checked)
        return result is not None and proves_conflict(result=result, identity=reverting)

    def _call(self, *, action: str, flags: dict[str, object]) -> _Checked:
        return call_authority(
            command=self.command,
            action=action,
            flags={"repo": str(self.repo), **flags},
            cwd=self.repo,
        )

    def _reverting(self, *, intent: RecoveryIntent) -> Generation | None:
        """The `reverting` generation a conflict is owed to, reopening a first failure first."""
        registration = intent.registration
        regression = intent.regression
        if regression is not None:
            return replace(
                Generation.of(registration=registration),
                attempt=regression.attempt_id,
                phase=_REVERTING,
                operation=regression.operation_id,
                generation=regression.generation,
                owner=regression.owner,
            )
        if registration.phase == _REVERTING:
            return Generation.of(registration=registration)
        return self._reopened(intent=intent)

    def _reopened(self, *, intent: RecoveryIntent) -> Generation | None:
        registration = intent.registration
        completion = intent.completion
        if completion is None:
            say(words="no failing leaf to attribute the conflict to")
            return None
        try:
            attributed = registration.authority_receipt.decode()
        except UnicodeDecodeError:
            say(words="the registered authority receipt is not canonical attempt text")
            return None
        finding = {
            "surface": _TRUNK,
            "subject": intent.action_id,
            "run_id": str(completion.run_id),
            "failed_head": completion.head_sha,
            "attributed_commit": registration.head_sha,
            "master_healthy": False,
        }
        current = Generation.of(registration=registration)
        checked = self._call(
            action=_REOPEN_ACTION,
            flags={
                **current.flags(),
                "attributed-json": attributed,
                "finding-json": canonical(value=finding),
                "principal": registration.owner,
            },
        )
        if is_successful(checked):
            return reopen_reply(result=checked.unwrap(), current=current)
        refusal = checked.failure()
        if refusal.code == _STALE_REOPEN:
            return recorded_reopen(current=current, finding=finding)
        report_authority_refusal(refusal=refusal)
        return None


_Checked = Result[dict[str, Any], AuthorityRefusal]


def _delivered(*, checked: _Checked) -> dict[str, Any] | None:
    """The verified result of one authority call; a refusal is named, never swallowed."""
    if is_successful(checked):
        return checked.unwrap()
    report_authority_refusal(refusal=checked.failure())
    return None
