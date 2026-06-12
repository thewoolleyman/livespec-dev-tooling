"""Committed-file obligation rows for the fleet-membership contract.

Each row asserts one committed-file fact about a member's `master`
tree from the central vantage point (livespec v108 §"Fleet membership
contract", obligation type "committed files"): the CI workflow, the
three pin-and-bump shim workflows, copier-answers for template-born
classes, the dev-tooling pin, and the no-tracked-gitlinks row. Every
assert distinguishes definitive absence (finding) from can't-read
(skip) so a permission-limited token never produces a false red.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import cast

from livespec_dev_tooling.fleet._context import (
    FleetContext,
    FleetMember,
    RowFinding,
    RowOutcome,
    RowPass,
    RowSkip,
)

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import tomli  # noqa: E402  — vendor-path-aware import after sys.path insert.

__all__: list[str] = [
    "BUMP_PIN_WORKFLOW",
    "CI_WORKFLOW",
    "COPIER_ANSWERS",
    "PIN_FRESHNESS_WORKFLOW",
    "RELEASE_DISPATCH_WORKFLOW",
    "assert_bump_pin_workflow",
    "assert_ci_workflow",
    "assert_copier_answers",
    "assert_dev_tooling_pin",
    "assert_no_tracked_gitlinks",
    "assert_pin_freshness_workflow",
    "assert_release_dispatch_workflow",
]


CI_WORKFLOW = ".github/workflows/ci.yml"
BUMP_PIN_WORKFLOW = ".github/workflows/bump-pin-from-dispatch.yml"
PIN_FRESHNESS_WORKFLOW = ".github/workflows/pin-freshness.yml"
RELEASE_DISPATCH_WORKFLOW = ".github/workflows/release-dispatch.yml"
COPIER_ANSWERS = ".copier-answers.yml"

_DEV_TOOLING_REPO = "livespec-dev-tooling"


def _tree_path_outcome(*, ctx: FleetContext, member: FleetMember, path: str) -> RowOutcome:
    """Pass when `path` exists in the member's master tree; finding when absent."""
    tree = ctx.tree(repo=member.repo)
    if not tree.readable:
        return RowSkip(reason=f"{member.repo}: master tree unreadable")
    if path in tree.paths:
        return RowPass()
    if tree.truncated:
        # A truncated recursive tree cannot prove absence; can't-read
        # (here: can't-read-completely) never produces a false red.
        return RowSkip(reason=f"{member.repo}: tree truncated; absence of {path} not definitive")
    return RowFinding(message=f"{member.repo}: required file {path} missing from master")


def assert_ci_workflow(*, ctx: FleetContext, member: FleetMember) -> RowOutcome:
    """`ci.yml` present on master."""
    return _tree_path_outcome(ctx=ctx, member=member, path=CI_WORKFLOW)


def assert_bump_pin_workflow(*, ctx: FleetContext, member: FleetMember) -> RowOutcome:
    """`bump-pin-from-dispatch.yml` shim present on master."""
    return _tree_path_outcome(ctx=ctx, member=member, path=BUMP_PIN_WORKFLOW)


def assert_pin_freshness_workflow(*, ctx: FleetContext, member: FleetMember) -> RowOutcome:
    """`pin-freshness.yml` shim present on master."""
    return _tree_path_outcome(ctx=ctx, member=member, path=PIN_FRESHNESS_WORKFLOW)


def assert_release_dispatch_workflow(*, ctx: FleetContext, member: FleetMember) -> RowOutcome:
    """`release-dispatch.yml` shim present on master."""
    return _tree_path_outcome(ctx=ctx, member=member, path=RELEASE_DISPATCH_WORKFLOW)


def assert_copier_answers(*, ctx: FleetContext, member: FleetMember) -> RowOutcome:
    """`.copier-answers.yml` present on master (template-born classes)."""
    return _tree_path_outcome(ctx=ctx, member=member, path=COPIER_ANSWERS)


def assert_no_tracked_gitlinks(*, ctx: FleetContext, member: FleetMember) -> RowOutcome:
    """No mode-160000 (gitlink) entries on master — the family uses no submodules."""
    tree = ctx.tree(repo=member.repo)
    if not tree.readable:
        return RowSkip(reason=f"{member.repo}: master tree unreadable")
    if tree.gitlink_paths:
        joined = ", ".join(tree.gitlink_paths)
        return RowFinding(message=f"{member.repo}: tracked gitlink(s) on master: {joined}")
    if tree.truncated:
        return RowSkip(reason=f"{member.repo}: tree truncated; gitlink absence not definitive")
    return RowPass()


def _pinned_tag(*, pyproject_text: str) -> str | None:
    """The `[tool.uv.sources].livespec-dev-tooling.tag` value, or None."""
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
    entry = cast("dict[str, object]", sources).get(_DEV_TOOLING_REPO)
    if not isinstance(entry, dict):
        return None
    tag = cast("dict[str, object]", entry).get("tag")
    return tag if isinstance(tag, str) else None


def _latest_dev_tooling_tag(*, ctx: FleetContext) -> str | None:
    """`livespec-dev-tooling`'s latest release tag, or None when unreadable."""
    payload = ctx.api_object(path=f"repos/{ctx.owner}/{_DEV_TOOLING_REPO}/releases/latest")
    if not isinstance(payload, dict):
        return None
    tag = cast("dict[str, object]", payload).get("tag_name")
    return tag if isinstance(tag, str) else None


def _freshness_outcome(*, ctx: FleetContext, member: FleetMember, tag: str) -> RowOutcome:
    """Staleness leg of the pin row — WARNING severity only.

    Freshness has its own dedicated repo-local mechanism
    (`pin-freshness.yml` + bump-PR automation); failing the fleet on a
    not-yet-merged bump PR would gate the release fan-out on its own
    downstream effect, so a stale pin warns rather than reds the fleet.
    """
    latest = _latest_dev_tooling_tag(ctx=ctx)
    if latest is None:
        return RowPass(note="pin present; freshness unverified (latest release unreadable)")
    if tag != latest:
        return RowFinding(
            message=f"{member.repo}: dev-tooling pin {tag} is stale (latest release {latest})",
            severity="warning",
        )
    return RowPass()


def assert_dev_tooling_pin(*, ctx: FleetContext, member: FleetMember) -> RowOutcome:
    """A `[tool.uv.sources]` pin on livespec-dev-tooling exists; staleness warns.

    Presence is the hard obligation (error severity); the staleness leg
    is delegated to `_freshness_outcome` (warning severity).
    """
    tree = ctx.tree(repo=member.repo)
    if not tree.readable:
        return RowSkip(reason=f"{member.repo}: master tree unreadable")
    if "pyproject.toml" not in tree.paths:
        if tree.truncated:
            return RowSkip(reason=f"{member.repo}: tree truncated; pyproject.toml not definitive")
        return RowFinding(message=f"{member.repo}: no pyproject.toml — dev-tooling pin missing")
    text = ctx.file_text(repo=member.repo, path="pyproject.toml")
    if text is None:
        return RowSkip(reason=f"{member.repo}: pyproject.toml unreadable")
    tag = _pinned_tag(pyproject_text=text)
    if tag is None:
        return RowFinding(
            message=(
                f"{member.repo}: no [tool.uv.sources] {_DEV_TOOLING_REPO} tag pin in pyproject.toml"
            )
        )
    return _freshness_outcome(ctx=ctx, member=member, tag=tag)
