"""The fleet row requiring every governed aggregate to contain every canonical slug.

The dynamic check package inventory is the canonical source of truth. A member
can omit a check from its own aggregate and consequently omit the self-check
that would have noticed, so this compares the committed aggregate from the
central fleet vantage. The fleet contract invokes rows only for manifest
`fleet` members; adopters have no repository class and are never swept.

A member may waive a canonical slug, with a reason, under `[tool.livespec_dev_tooling]`
`canonical_check_waivers` in its master-tree `pyproject.toml` (the one surface this
row reads a waiver from). The shared reader and judge live in
`checks/_canonical_waivers`, which `check-aggregate-completeness` uses too. A waived
omission is satisfied and handed back on the outcome so the lane logs it with the
member, the slug and the reason; a stale or malformed waiver is an error. A
`pyproject.toml` the tree lists but this run cannot read or parse SKIPS the member:
taking an unreadable file for an absent key would read an undeclared waiver as none
and convict the member of omissions it may have been excused from. A file the tree
definitively does not list declares no waiver.
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
from returns.result import Failure  # noqa: E402  — vendor-path-aware import.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware import.

from livespec_dev_tooling.canonical_checks import canonical_check_slugs  # noqa: E402
from livespec_dev_tooling.checks._canonical_waivers import (  # noqa: E402
    DeclaredWaivers,
    declared_waivers,
    judge_waivers,
)
from livespec_dev_tooling.fleet._context import (  # noqa: E402
    FleetContext,
    FleetMember,
    RowFinding,
    RowOutcome,
    RowPass,
    RowSkip,
    TreeState,
)
from livespec_dev_tooling.fleet._rows_aggregate_gate import (  # noqa: E402
    ResolvedCheckAggregate,
    resolve_check_aggregate_targets,
)

__all__: list[str] = [
    "CANONICAL_CHECK_SLUGS_HINT",
    "PYPROJECT_PATH",
    "assert_canonical_check_slugs_wired",
]

PYPROJECT_PATH = "pyproject.toml"
_MUST_RUN_ALL = "fleet members must run every canonical check"


CANONICAL_CHECK_SLUGS_HINT = (
    "add every slug from livespec-dev-tooling's canonical check inventory to the member's "
    "committed `just check` aggregate — check-targets.txt when it carries one, otherwise "
    "the justfile `check:` recipe's targets=(...) array — in a repo-local commit, or waive a "
    "slug with a reason under `[tool.livespec_dev_tooling]` `canonical_check_waivers` in the "
    "member's pyproject.toml"
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


def _member_waivers(
    *, ctx: FleetContext, member: FleetMember, tree: TreeState
) -> DeclaredWaivers | RowSkip:
    """The waivers the member's master-tree `pyproject.toml` declares, or the skip."""
    if PYPROJECT_PATH not in tree.paths:
        if tree.truncated:
            return RowSkip(
                reason=f"{member.repo}: tree truncated; absence of {PYPROJECT_PATH} not definitive"
            )
        return DeclaredWaivers(value=[])
    text = ctx.file_text(repo=member.repo, path=PYPROJECT_PATH)
    if text is None:
        unevaluable = "canonical-check waivers not evaluable"
        return RowSkip(reason=f"{member.repo}: {PYPROJECT_PATH} unreadable — {unevaluable}")
    parsed = declared_waivers(pyproject_text=text)
    if isinstance(parsed, Failure):
        return RowSkip(
            reason=(
                f"{member.repo}: {PYPROJECT_PATH} unparseable "
                f"({parsed.failure().detail}) — canonical-check waivers not evaluable"
            )
        )
    return parsed.unwrap()


def assert_canonical_check_slugs_wired(*, ctx: FleetContext, member: FleetMember) -> RowOutcome:
    """Fail a fleet member whose committed aggregate omits an unwaived canonical slug."""
    tree = ctx.tree(repo=member.repo)
    if not tree.readable:
        return RowSkip(reason=f"{member.repo}: master tree unreadable")
    resolved = resolve_check_aggregate_targets(ctx=ctx, member=member, tree=tree)
    if not isinstance(resolved, ResolvedCheckAggregate):
        return resolved
    canonical = _canonical_slugs()
    if isinstance(canonical, RowFinding):
        return canonical
    declared = _member_waivers(ctx=ctx, member=member, tree=tree)
    if isinstance(declared, RowSkip):
        return declared
    verdict = judge_waivers(declared=declared.value, canonical=canonical, selected=resolved.targets)
    waived = {waiver.slug for waiver in verdict.honoured}
    missing = tuple(s for s in canonical if s not in resolved.targets and s not in waived)
    honoured = tuple((waiver.slug, waiver.reason) for waiver in verdict.honoured)
    findings = [problem.render() for problem in verdict.problems]
    if missing:
        omitted = ", ".join(missing)
        findings.insert(
            0, f"committed check aggregate ({resolved.source}) omits {omitted} — {_MUST_RUN_ALL}"
        )
    if not findings:
        return RowPass(waivers=honoured)
    return RowFinding(
        message=f"{member.repo}: {'; '.join(findings)}", severity="error", waivers=honoured
    )
