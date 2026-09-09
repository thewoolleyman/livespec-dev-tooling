"""The `aggregate-gate-wired` obligation row over a member's committed check aggregate.

FAILURE CLASS 1 of `livespec-dev-tooling-739o`, and the only one of that
item's three that survived re-measurement on 2026-09-09. Nothing asserted,
from the FLEET vantage, that a member's committed `just check` aggregate
actually wires the two canonical meta-gates. `aggregate_completeness` and
`ci_matrix_completeness` are per-repo SELF-reads: they fire only in a repo
that already wires them, so a member that omits them omits its own detector
too, and a newly-shipped canonical check reaches that member silently never
— the shape the item names "silence and success must not look identical".

WHERE A MEMBER'S AGGREGATE LIVES — the resolution order mirrors
`ci_matrix_completeness`'s in-repo order EXACTLY (committed
`check-targets.txt` inventory FIRST, else the justfile `check:` recipe's
`targets=(...)` array), because the fleet-vantage row and the per-repo gate
must agree about what a member's aggregate IS. Measured 2026-09-09 across
all ten manifest fleet members: four carry the inventory and six carry the
justfile array. Reading only the justfile would misreport every inventory
member — `livespec-runtime`'s aggregate is the parameterized recipe
`check *skip_targets:` delegating to a shell script, so its justfile holds
no targets array at all.

The inventory reader is a MECHANICAL extractor carrying no spec citation, so
it is a permitted duplicate under the bounded parser-duplication convention
stated in `checks/_ci_matrix_parse.py`'s docstring; the two rule-bearing
justfile parsers are IMPORTED from that shared home rather than copied.

Every read distinguishes definitive absence from can't-read, the discipline
the sibling committed-file rows in `_rows_files.py` hold to. An aggregate
this row cannot ENUMERATE is a skip, never a finding: a member whose
aggregate is unreadable, or whose shape neither reader understands, has not
been shown to omit anything.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from livespec_dev_tooling.checks._ci_matrix_parse import (
    extract_check_recipe_body,
    extract_targets_array_tokens,
)
from livespec_dev_tooling.fleet._context import (
    FleetContext,
    FleetMember,
    RowFinding,
    RowOutcome,
    RowPass,
    RowSkip,
    TreeState,
)

# Declared here regardless of which sibling import currently drags `_vendor/`
# onto the path first, for the reason `_context.py`'s own preamble states: the
# hazard is an ordering dependency no reader can see.
_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.result import Failure  # noqa: E402  — vendor-path-aware import.

__all__: list[str] = [
    "AGGREGATE_GATE_HINT",
    "AGGREGATE_GATE_SLUGS",
    "CHECK_TARGETS_INVENTORY",
    "JUSTFILE_PATH",
    "assert_aggregate_gate_wired",
]


JUSTFILE_PATH = "justfile"
CHECK_TARGETS_INVENTORY = "check-targets.txt"
_CHECK_PREFIX = "check-"

# The two CANONICAL META-GATES, and the reason this row exists at all. Every
# other canonical slug is enforced by being IN the aggregate; these two are
# what enforce that the aggregate is complete (`check-aggregate-completeness`:
# the justfile aggregate runs every canonical slug) and that CI mirrors it
# (`check-ci-matrix-completeness`: the aggregate's targets are actually run by
# `.github/workflows/ci.yml`). A member missing them can merge a green pin
# bump that adopts a new canonical check without ever running it.
AGGREGATE_GATE_SLUGS: tuple[str, ...] = (
    "check-aggregate-completeness",
    "check-ci-matrix-completeness",
)

AGGREGATE_GATE_HINT = (
    "wire check-aggregate-completeness and check-ci-matrix-completeness into the "
    "member's `just check` aggregate — its committed check-targets.txt inventory when "
    "it carries one, else the justfile `check:` recipe's targets=(...) array — and add "
    "matching entries to the .github/workflows/ci.yml matrix that mirrors the aggregate, "
    "in a repo-local commit"
)


@dataclass(frozen=True, kw_only=True)
class _ResolvedTargets:
    """A member's committed aggregate target list and the file it was read from.

    The source path travels WITH the targets because the finding has to send
    an operator to the right file: the fleet's members split between the two
    aggregate shapes, and "your aggregate omits X" is unactionable without
    saying which committed file holds the aggregate.
    """

    source: str
    targets: tuple[str, ...]


def _inventory_targets(*, inventory_text: str) -> tuple[str, ...]:
    """The `check-*` slugs listed in a committed `check-targets.txt`.

    A permitted duplicate of `ci_matrix_completeness`'s reader of the same
    file under the bounded parser-duplication convention — a mechanical
    extractor, no spec citation. One slug per line, `#` starts a comment.
    """
    targets: list[str] = []
    for raw in inventory_text.splitlines():
        token = raw.split("#", 1)[0].strip()
        if token.startswith(_CHECK_PREFIX):
            targets.append(token)
    return tuple(targets)


def _justfile_targets(*, ctx: FleetContext, member: FleetMember) -> _ResolvedTargets | RowOutcome:
    """The `targets=(...)` slugs of the member's bare `check:` recipe.

    Both parsers come from the shared `_ci_matrix_parse` home so this row and
    the per-repo gate cannot drift about what a justfile aggregate is. Neither
    failure is a violation: an aggregate whose shape this reader does not
    understand has not been shown to OMIT anything, so both skip, naming the
    shape so the reason is actionable rather than a bare "unreadable".
    """
    text = ctx.file_text(repo=member.repo, path=JUSTFILE_PATH)
    if text is None:
        return RowSkip(reason=f"{member.repo}: {JUSTFILE_PATH} unreadable")
    recipe_body = extract_check_recipe_body(justfile_text=text)
    if isinstance(recipe_body, Failure):
        return RowSkip(
            reason=(
                f"{member.repo}: no bare `check:` recipe in {JUSTFILE_PATH} and no "
                f"{CHECK_TARGETS_INVENTORY} — aggregate targets not enumerable"
            )
        )
    targets = extract_targets_array_tokens(recipe_body=recipe_body.unwrap())
    if isinstance(targets, Failure):
        return RowSkip(
            reason=(
                f"{member.repo}: `check:` recipe in {JUSTFILE_PATH} carries no readable "
                "targets=(...) array — aggregate targets not enumerable"
            )
        )
    return _ResolvedTargets(source=JUSTFILE_PATH, targets=tuple(targets.unwrap()))


def _inventory_resolved(*, ctx: FleetContext, member: FleetMember) -> _ResolvedTargets | RowOutcome:
    """The member's aggregate read from its committed `check-targets.txt`."""
    text = ctx.file_text(repo=member.repo, path=CHECK_TARGETS_INVENTORY)
    if text is None:
        return RowSkip(reason=f"{member.repo}: {CHECK_TARGETS_INVENTORY} unreadable")
    return _ResolvedTargets(
        source=CHECK_TARGETS_INVENTORY, targets=_inventory_targets(inventory_text=text)
    )


def _resolve_targets(
    *, ctx: FleetContext, member: FleetMember, tree: TreeState
) -> _ResolvedTargets | RowOutcome:
    """The member's committed aggregate, or the outcome that ends the row.

    Inventory FIRST, justfile second — `ci_matrix_completeness`'s order. A
    member carrying NEITHER file has no aggregate this row can read, which is
    a skip naming the absent files rather than an unhandled error or a
    conviction: whether a member owes a justfile at all is the sibling
    `worktree-pack-wired` row's obligation, not this one's.
    """
    if CHECK_TARGETS_INVENTORY in tree.paths:
        return _inventory_resolved(ctx=ctx, member=member)
    if JUSTFILE_PATH in tree.paths:
        return _justfile_targets(ctx=ctx, member=member)
    if tree.truncated:
        return RowSkip(
            reason=(f"{member.repo}: tree truncated; absence of {JUSTFILE_PATH} not definitive")
        )
    return RowSkip(
        reason=(
            f"{member.repo}: no committed {JUSTFILE_PATH} and no {CHECK_TARGETS_INVENTORY} "
            "— check aggregate not evaluable"
        )
    )


def assert_aggregate_gate_wired(*, ctx: FleetContext, member: FleetMember) -> RowOutcome:
    """The member's committed check aggregate wires both canonical meta-gates.

    WARNING severity, and the choice is a judgement about CONSEQUENCE rather
    than a soft-arming device. Measured on origin/master 2026-09-09 across all
    ten manifest fleet members, the offender count is ONE —
    `livespec-console-beads-fabro`, which wires neither slug — and its
    remediation is owned by the console tenant, not by this repo. Error
    severity here would do two things this repo forbids: red every unrelated
    dev-tooling PR on a sibling's unrepaired state, and, in the
    filter-consuming fan-out preflight, EXCLUDE the console from release
    dispatch entirely — which would freeze the very pin currency the item
    documents as already twelve releases behind, making the outage worse
    rather than visible. Arming at error is a one-word change the moment the
    console wires the two slugs; arming it before that adoption is exactly
    what `plan/rop-railway-enforcement/` records as the standing constraint
    (46c5dab armed ahead of adoption, five repos went red, f4247110 reverted).
    """
    tree = ctx.tree(repo=member.repo)
    if not tree.readable:
        return RowSkip(reason=f"{member.repo}: master tree unreadable")
    resolved = _resolve_targets(ctx=ctx, member=member, tree=tree)
    if not isinstance(resolved, _ResolvedTargets):
        return resolved
    missing = tuple(slug for slug in AGGREGATE_GATE_SLUGS if slug not in resolved.targets)
    if not missing:
        return RowPass()
    return RowFinding(
        message=(
            f"{member.repo}: committed check aggregate ({resolved.source}) omits "
            f"{', '.join(missing)} — a canonical check shipped to this member is never "
            "run by its `just check`, and the release fan-out reports success anyway"
        ),
        severity="warning",
    )
