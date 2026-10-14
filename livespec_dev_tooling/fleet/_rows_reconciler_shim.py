"""_rows_reconciler_shim — the master-health reconciler shim obligation row.

Child D of plan `red-master-self-healing` (epic `livespec-dev-tooling-zcp5vb`,
work-item `livespec-dev-tooling-dw7dzd`). The charter's design item 6 requires
that "a conformance row fails a repo whose shim is missing or drifted", and the
DRIFTED half is why this row is not a fourth copy of the sibling
presence-only shim rows in `_rows_files`: a shim edited by hand — a dropped
trigger, a coarsened cron, a redirected `uses:` — still satisfies a presence
check while reconciling nothing at all.

⛔ THE PINNED REF IS NORMALISED AWAY, AND THAT IS NOT A WEAKENING. The shim is
installed at the bootstrap `@master` ref and the bump-pin automation rewrites
that ref to a release tag — by design, under the ratified pin-and-bump
contract this repository's `SPECIFICATION/contracts.md` records. A byte-identity
comparison would therefore report EVERY correctly-wired member as drifted from
the moment the first pin bump landed: red fleet-wide, for conformance to a
mechanism the fleet is supposed to have. Normalising the one field another
ratified mechanism owns, and comparing every other byte exactly, is
conformance — the shape this repository's instructions call "an unratified
filter inside a check is conformance, not ratification".
"""

from __future__ import annotations

import re

from livespec_dev_tooling.fleet._context import (
    FleetContext,
    FleetMember,
    RowFinding,
    RowOutcome,
    RowPass,
    RowSkip,
)
from livespec_dev_tooling.fleet._reconciler_shim import (
    RECONCILER_WORKFLOW,
    reconciler_shim_content,
)

__all__: list[str] = [
    "RECONCILER_SHIM_HINT",
    "assert_reconciler_shim",
    "reconciler_shim_drifted",
]


# What an operator does about a finding this row raises. `wire-fleet-member`
# provisions a MISSING shim; a DRIFTED one it leaves alone, because its
# reconcile writes only paths absent from the member's tree. Saying so is the
# difference between a hint that resolves the finding and one that sends the
# operator round a loop that cannot.
RECONCILER_SHIM_HINT = (
    "wire-fleet-member provisions a MISSING reconciler shim but leaves a "
    "DRIFTED one alone, so replace the member's "
    f"{RECONCILER_WORKFLOW} with the canonical body — or delete it and rerun "
    "wire-fleet-member. The canonical bytes are livespec-dev-tooling's "
    "livespec_dev_tooling/fleet/_reconciler_shim.py."
)

# The `uses:` line's pinned ref, which the bump-pin automation owns. Anchored
# to a whole line under MULTILINE so it can only ever rewrite the ref of a
# reusable-workflow call, never an `@` appearing anywhere else in the body.
_PINNED_CALL = re.compile(r"^(?P<call>\s*uses: \S+)@\S+$", re.MULTILINE)
_NORMALISED_REF = r"\g<call>@<pinned-ref>"


def reconciler_shim_drifted(*, text: str, canonical: str) -> bool:
    """Whether `text` differs from `canonical` other than in its pinned ref."""
    return _PINNED_CALL.sub(_NORMALISED_REF, text) != _PINNED_CALL.sub(_NORMALISED_REF, canonical)


def assert_reconciler_shim(*, ctx: FleetContext, member: FleetMember) -> RowOutcome:
    """The member's master carries the canonical master-health reconciler shim.

    Every can't-read shape SKIPS rather than reporting absence or drift, per
    the sibling rows' standing rule that a permission-limited or transiently
    failing read must never produce a false red. The listed-but-unreadable case
    matters most: calling it drift would put a member's conformance at the mercy
    of one contents-API failure, and the remedy the finding would print —
    rewrite the shim — is not the remedy for a failed read.
    """
    tree = ctx.tree(repo=member.repo)
    if not tree.readable:
        return RowSkip(reason=f"{member.repo}: master tree unreadable")
    if RECONCILER_WORKFLOW not in tree.paths:
        if tree.truncated:
            return RowSkip(
                reason=(
                    f"{member.repo}: tree truncated; absence of "
                    f"{RECONCILER_WORKFLOW} not definitive"
                )
            )
        return RowFinding(
            message=(
                f"{member.repo}: master-health reconciler shim "
                f"{RECONCILER_WORKFLOW} missing from master"
            )
        )
    text = ctx.file_text(repo=member.repo, path=RECONCILER_WORKFLOW)
    if text is None:
        return RowSkip(reason=f"{member.repo}: {RECONCILER_WORKFLOW} unreadable")
    if reconciler_shim_drifted(text=text, canonical=reconciler_shim_content(owner=ctx.owner)):
        return RowFinding(
            message=(
                f"{member.repo}: {RECONCILER_WORKFLOW} differs from the canonical "
                "reconciler shim (the pinned ref the bump-pin automation owns is "
                "not counted)"
            )
        )
    return RowPass()
