"""The fleet row requiring every governed aggregate to contain every canonical slug.

The dynamic check package inventory is the canonical source of truth. A member
can omit a check from its own aggregate and consequently omit the self-check
that would have noticed, so this compares the committed aggregate from the
central fleet vantage. The fleet contract invokes rows only for manifest
`fleet` members; adopters have no repository class and are never swept.
"""

from __future__ import annotations

import sys
from pathlib import Path

# `returns` is vendored, so this row must establish the import path itself
# instead of depending on another fleet module having run first.
_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.io import IOFailure  # noqa: E402  — vendor-path-aware import.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware import.

from livespec_dev_tooling.canonical_checks import canonical_check_slugs  # noqa: E402
from livespec_dev_tooling.fleet._context import (  # noqa: E402
    FleetContext,
    FleetMember,
    RowFinding,
    RowOutcome,
    RowPass,
    RowSkip,
)
from livespec_dev_tooling.fleet._rows_aggregate_gate import (  # noqa: E402
    ResolvedCheckAggregate,
    resolve_check_aggregate_targets,
)

__all__: list[str] = [
    "CANONICAL_CHECK_SLUGS_HINT",
    "assert_canonical_check_slugs_wired",
]


CANONICAL_CHECK_SLUGS_HINT = (
    "add every slug from livespec-dev-tooling's canonical check inventory to the member's "
    "committed `just check` aggregate — check-targets.txt when it carries one, otherwise "
    "the justfile `check:` recipe's targets=(...) array — in a repo-local commit"
)


def _canonical_slugs() -> tuple[str, ...] | RowFinding:
    """The authoritative canonical set, or an error when it cannot be discovered."""
    discovered = canonical_check_slugs()
    if isinstance(discovered, IOFailure):
        unreadable = unsafe_perform_io(discovered.failure())
        return RowFinding(
            message=f"canonical check inventory unreadable: {unreadable}", severity="error"
        )
    return unsafe_perform_io(discovered.unwrap())


def assert_canonical_check_slugs_wired(*, ctx: FleetContext, member: FleetMember) -> RowOutcome:
    """Fail a fleet member whose committed aggregate omits a canonical check slug."""
    tree = ctx.tree(repo=member.repo)
    if not tree.readable:
        return RowSkip(reason=f"{member.repo}: master tree unreadable")
    resolved = resolve_check_aggregate_targets(ctx=ctx, member=member, tree=tree)
    if not isinstance(resolved, ResolvedCheckAggregate):
        return resolved
    canonical = _canonical_slugs()
    if isinstance(canonical, RowFinding):
        return canonical
    missing = tuple(slug for slug in canonical if slug not in resolved.targets)
    if not missing:
        return RowPass()
    return RowFinding(
        message=(
            f"{member.repo}: committed check aggregate ({resolved.source}) omits "
            f"{', '.join(missing)} — fleet members must run every canonical check"
        ),
        severity="error",
    )
