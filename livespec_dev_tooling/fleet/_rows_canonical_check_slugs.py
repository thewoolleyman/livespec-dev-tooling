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
from typing import cast

# `returns` is vendored, so this row must establish the import path itself
# instead of depending on another fleet module having run first.
_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import tomli  # noqa: E402  — vendor-path-aware import.
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
from livespec_dev_tooling.fleet._row_finding import pin_staleness_finding  # noqa: E402
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
_DEV_TOOLING_REPO = "livespec-dev-tooling"
_CHECKS_PREFIX = "livespec_dev_tooling/checks/"


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


def pinned_dev_tooling_tag(*, pyproject_text: str) -> str | None:
    """The member's direct, tag-pinned livespec-dev-tooling release, if declared."""
    try:
        data: dict[str, object] = tomli.loads(pyproject_text)
    except tomli.TOMLDecodeError:
        return None
    tool = data.get("tool")
    if not isinstance(tool, dict):
        return None
    uv = cast("dict[str, object]", tool).get("uv")
    if not isinstance(uv, dict):
        return None
    sources = cast("dict[str, object]", uv).get("sources")
    if not isinstance(sources, dict):
        return None
    source = cast("dict[str, object]", sources).get(_DEV_TOOLING_REPO)
    if not isinstance(source, dict):
        return None
    tag = cast("dict[str, object]", source).get("tag")
    return tag if isinstance(tag, str) else None


def pinned_release_check_slugs(*, ctx: FleetContext, tag: str) -> frozenset[str] | None:
    """Canonical check slugs in the pinned release tree, or None when unreadable."""
    payload = ctx.api_object(
        path=f"repos/{ctx.owner}/{_DEV_TOOLING_REPO}/git/trees/{tag}?recursive=1",
        operation="pinned_dev_tooling_canonical_inventory",
    )
    if not isinstance(payload, dict):
        return None
    mapping = cast("dict[str, object]", payload)
    if bool(mapping.get("truncated")):
        return None
    entries = mapping.get("tree")
    if not isinstance(entries, list):
        return None
    return frozenset(
        f"check-{path.removeprefix(_CHECKS_PREFIX).removesuffix('.py').replace('_', '-')}"
        for entry in cast("list[object]", entries)
        if isinstance(entry, dict)
        and isinstance((path := cast("dict[str, object]", entry).get("path")), str)
        and path.startswith(_CHECKS_PREFIX)
        and path.endswith(".py")
        and not path.removeprefix(_CHECKS_PREFIX).startswith("_")
    )


def _pinned_release_missing_slugs(
    *, ctx: FleetContext, member: FleetMember, missing: tuple[str, ...]
) -> tuple[str, tuple[str, ...]] | None:
    """The pin and missing slugs its release cannot ship, if both are readable."""
    text = ctx.file_text(repo=member.repo, path=PYPROJECT_PATH)
    if text is None:
        return None
    tag = pinned_dev_tooling_tag(pyproject_text=text)
    if tag is None:
        return None
    pinned = pinned_release_check_slugs(ctx=ctx, tag=tag)
    if pinned is None:
        return None
    absent = tuple(slug for slug in missing if slug not in pinned)
    return tag, absent


def _findings_outcome(
    *,
    ctx: FleetContext,
    member: FleetMember,
    findings: list[str],
    missing: tuple[str, ...],
    honoured: tuple[tuple[str, str], ...],
) -> RowFinding:
    """Render canonical findings, retaining only slugs the pinned release lacks."""
    pinned_missing = _pinned_release_missing_slugs(ctx=ctx, member=member, missing=missing)
    if pinned_missing is not None and pinned_missing[1] == missing:
        tag, absent = pinned_missing
        detail = ", ".join(absent)
        return pin_staleness_finding(
            message=(
                f"{member.repo}: {'; '.join(findings)} — missing canonical slug(s) {detail} "
                f"are absent from pinned livespec-dev-tooling release {tag}"
            ),
            severity="error",
        )
    return RowFinding(
        message=f"{member.repo}: {'; '.join(findings)}",
        severity="error",
        waivers=honoured,
    )


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
    return _findings_outcome(
        ctx=ctx,
        member=member,
        findings=findings,
        missing=missing,
        honoured=honoured,
    )
