"""Write a journaled rollback-conflict onto the canonical incident chain.

`incident_inverse` hands a genuine overlap to the recovery principal, whose durable
result is the recovery journal. The journal is the controller's own record and
stays available when the tenant is not, but it is not the incident item's
lifecycle: only the orchestrator's `record-rollback-conflict` action writes the
`rollback-conflict` phase and the `blocked` status, and it accepts only the
`reverting` generation. This module is that action's one caller in dev-tooling.
It holds no observer fence: `incident_conflict_publication` calls it between two
short fenced reads of the observer's state, never inside one.

A first master failure has not reached `reverting`: the registration names the merged
attempt. The writer therefore calls `reopen-regression` FIRST, with a `trunk` finding
built from the failing leaf and keyed to the immutable recovery action, and records the
conflict on the `reverting` generation that reply names. A regression reopen is already
at `reverting`, so it is named directly. A pre-merge arm's registration stays at the
`repair` generation it armed at, so the reopen names the `master-observation` generation
the orchestrator's `record-merge` wrote one on, read back from the chain with its landed
commits; a standalone admission after the merge already names that generation.

Both writes go through the manifest's installed canonical reader command by the shared
authority client and take nothing from caller JSON: the orchestrator re-reads the chain
and refuses an identity that is not the generation it acts on. Every payload field is a
function of the journaled receipt and the registration, so a repeat for the same action
and head sends byte-identical bytes and the orchestrator recovers its one recorded
transition. A repeat meets a reopen that is already recorded, which the orchestrator
refuses as a stale observation; the writer then names the `reverting` generation that
reopen produced (the orchestrator's own `recovery-<digest>` identity).

Every call ends in one `ChainWrite`. `landed` means the reply proves the blocked
`rollback-conflict` transition. `terminal` is reserved for the chain's own proof that
this write can never land: another reopen or the owner's resolution moved the chain
past it, or a reply that answers for a different generation. Everything else is
`retry`, classified by the refusal's code so the publication can bound it: the tenant
was unavailable (the client's silence, or the orchestrator's own `*-unavailable`
refusal), `record-merge` has not yet recorded a pre-merge arm's merge, a claim move
lost a race, or a refusal not known to be final. A claim move refused as
`claim-changed` across spaced attempts is the orchestrator's non-atomic
`reopen-regression` (bd-ib-hyho7h): the chain holds the conflict but the item's claim
never moved, and the publication journals it terminal after its bound
(`docs/incident-observer-service.md`, "Known limitation"). From orchestrator v0.313.0
the conflict write refuses such a generation before the chain write, as
`incident-rollback-conflict-claim-not-held`: a first failure retries, which repeats its
own reopen, while a regression reopen or a registration already at `reverting`, which
this writer cannot reopen again, is journaled terminal at once as a half-reopen.

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
    ChainWrite,
    Generation,
    canonical,
    merged_attempt,
    proves_conflict,
    recorded_reopen,
    reopen_reply,
    say,
)
from livespec_dev_tooling._incident_observer_types import (  # noqa: E402
    ObserverRegistration,
    RecoveryIntent,
)
from livespec_dev_tooling.incident_authority_client import (  # noqa: E402
    AuthorityRefusal,
    call_authority,
    report_authority_refusal,
)

__all__: list[str] = ["ChainWrite", "ConflictChain", "is_conflict_receipt"]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-fdquen
_CONFLICT_ACTION = "record-rollback-conflict"
_REOPEN_ACTION = "reopen-regression"
_HISTORY = "read-history"
_STALE_REOPEN = "incident-reopen-stale-observation"
_IDENTITY_MISMATCH = "incident-authority-identity-mismatch"
_GENERATION_STALE = "incident-generation-stale"
_CLAIM_REFUSED = "incident-rollback-conflict-lifecycle-refused"
_CLAIM_NOT_HELD = "incident-rollback-conflict-claim-not-held"
_REVERTING = "reverting"
_REPAIR = "repair"
_MERGED = "master-observation"
_RECEIPT_PREFIX = "rollback-conflict:"
_TRUNK = "trunk"
_TENANT = "tenant-unavailable"
_MERGE_UNRECORDED = "merge-unrecorded"
_CLAIM_CHANGED = "claim-changed"
# The only refusals of the conflict write that are final on sight: the chain itself moved
# past this conflict. Every other refusal is retried, within the publication's bounds.
_CONFLICT_TERMINALS = {
    _GENERATION_STALE: "superseded: the chain moved past this conflict (the owner resolved it)",
    _IDENTITY_MISMATCH: "superseded: a different reopen holds the chain",
}
# Orchestrator v0.313.0 (bd-ib-hyho7h) refuses the conflict write BEFORE the chain write
# when the reverting generation never took the item's claim; its remedy is to retry the
# reopen. Only a writer that made the reopen can do that. For a regression reopen, or a
# registration already at reverting, the refusal is therefore final.
_UNREPEATABLE_REOPEN_TERMINALS = {
    **_CONFLICT_TERMINALS,
    _CLAIM_NOT_HELD: (
        "half-reopen: the reverting generation this conflict is owed to never took the "
        "item's claim, and this writer did not make that reopen, so it cannot repeat it "
        "(incident-rollback-conflict-claim-not-held, orchestrator bd-ib-hyho7h)"
    ),
}


def is_conflict_receipt(*, receipt: str | None) -> bool:
    """Whether a recorded receipt is a journaled conflict rather than a revert merge."""
    return receipt is not None and receipt.startswith(_RECEIPT_PREFIX)


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

    def record(self, *, intent: RecoveryIntent, receipt: str) -> ChainWrite:
        """Write the conflict; `landed` only when the reply proves it blocked the item."""
        if not self.command or not self.installed_reader_approved(self.release, self.command):
            return ChainWrite.retry(reason="reader-unapproved")
        reverting = self._reverting(intent=intent)
        if isinstance(reverting, ChainWrite):
            return reverting
        conflict = {
            "receipt": receipt,
            "release_condition": f"the incident owner resolves the later-work overlap: {receipt}",
        }
        checked = self._call(
            action=_CONFLICT_ACTION,
            flags={**reverting.flags(), "rollback-conflict-json": canonical(value=conflict)},
        )
        if not is_successful(checked):
            terminals = (
                _CONFLICT_TERMINALS if _reopens(intent=intent) else _UNREPEATABLE_REOPEN_TERMINALS
            )
            return _refused(refusal=checked.failure(), terminals=terminals, prefix="conflict")
        if proves_conflict(result=checked.unwrap(), identity=reverting):
            return ChainWrite.landed()
        say(words="the conflict reply does not prove the blocked next generation")
        return ChainWrite.terminal(reason="conflict-reply-unproven")

    def _call(self, *, action: str, flags: dict[str, object]) -> _Checked:
        return call_authority(
            command=self.command,
            action=action,
            flags={"repo": str(self.repo), **flags},
            cwd=self.repo,
        )

    def _reverting(self, *, intent: RecoveryIntent) -> Generation | ChainWrite:
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

    def _reopened(self, *, intent: RecoveryIntent) -> Generation | ChainWrite:
        registration = intent.registration
        completion = intent.completion
        if completion is None:
            say(words="no failing leaf to attribute the conflict to")
            return ChainWrite.terminal(reason="no-failing-leaf")
        merged = self._merged(registration=registration)
        if isinstance(merged, ChainWrite):
            return merged
        current, attributed = merged
        finding = {
            "surface": _TRUNK,
            "subject": intent.action_id,
            "run_id": str(completion.run_id),
            "failed_head": completion.head_sha,
            "attributed_commit": registration.head_sha,
            "master_healthy": False,
        }
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
            reopened = reopen_reply(result=checked.unwrap(), current=current)
            return reopened or ChainWrite.terminal(reason="reopen-reply-unproven")
        refusal = checked.failure()
        if refusal.code == _STALE_REOPEN:
            return recorded_reopen(current=current, finding=finding)
        return _refused(refusal=refusal, terminals={}, prefix="reopen")

    def _merged(self, *, registration: ObserverRegistration) -> tuple[Generation, str] | ChainWrite:
        """The merged attempt a first failure reopens, with its canonical attempt record.

        A standalone admission after the merge binds `master-observation` itself, and
        its retained receipt is that attempt's canonical record. A pre-merge arm keeps
        the `repair` generation it armed at: the chain records the merge one generation
        on, through the orchestrator's `record-merge`, and only that record carries the
        landed commits a `trunk` finding is attributed to. The writer reads that exact
        generation from the chain; until `record-merge` has run, the chain refuses the
        read as an identity mismatch and the write is retried later, within a bound.
        """
        current = Generation.of(registration=registration)
        if registration.phase != _REPAIR:
            try:
                return current, registration.authority_receipt.decode()
            except UnicodeDecodeError:
                say(words="the registered authority receipt is not canonical attempt text")
                return ChainWrite.terminal(reason="receipt-not-canonical")
        merged = replace(
            current,
            phase=_MERGED,
            operation=f"{current.attempt}#{_MERGED}",
            generation=current.generation + 1,
        )
        checked = self._call(action=_HISTORY, flags=merged.flags())
        if not is_successful(checked):
            refusal = checked.failure()
            if refusal.canonical and refusal.code == _IDENTITY_MISMATCH:
                report_authority_refusal(refusal=refusal)
                return ChainWrite.retry(reason=_MERGE_UNRECORDED)
            return _refused(refusal=refusal, terminals={}, prefix="merge-read")
        attempt = merged_attempt(
            result=checked.unwrap(), identity=merged, head=registration.head_sha
        )
        if attempt is None:
            say(words="the chain records no merge of this attempt that landed the failed head")
            return ChainWrite.terminal(reason="merge-record-mismatch")
        return merged, canonical(value=attempt)


_Checked = Result[dict[str, Any], AuthorityRefusal]


def _reopens(*, intent: RecoveryIntent) -> bool:
    """Whether this writer makes the reopen itself, so that a retry repeats it."""
    return intent.regression is None and intent.registration.phase != _REVERTING


def _refused(*, refusal: AuthorityRefusal, terminals: dict[str, str], prefix: str) -> ChainWrite:
    """A refusal named on stderr, classified by its code.

    An outage (`AuthorityRefusal.is_outage`: the client's own silence, or the
    orchestrator's own `*-unavailable` / `*-outcome-unknown` refusal, which arrives as
    exit 78 like a decision) and any refusal not known to be final are retried under the
    publication's back-off and bound.
    Only a refusal in `terminals` is final at once. A refused claim move is retried under
    its own reason: `claim-changed` repeating across spaced attempts is the orchestrator's
    half-reopen (bd-ib-hyho7h), which the publication turns terminal after its bound, while
    every other claim outcome is a transient lease or token race.
    """
    report_authority_refusal(refusal=refusal)
    if refusal.is_outage:
        return ChainWrite.retry(reason=_TENANT)
    terminal = terminals.get(refusal.code)
    if terminal is not None:
        return ChainWrite.terminal(reason=terminal)
    if refusal.code == _CLAIM_REFUSED:
        detail = refusal.detail
        return ChainWrite.retry(
            reason=_CLAIM_CHANGED if detail == _CLAIM_CHANGED else f"claim-unsettled: {detail}"
        )
    return ChainWrite.retry(reason=f"{prefix}-refused: {refusal.code}")
