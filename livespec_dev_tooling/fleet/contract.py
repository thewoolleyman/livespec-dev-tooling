"""The shared fleet-membership contract definition (manifest + obligation table).

ONE definition consumed by BOTH modes (livespec v108 §"Fleet
membership contract": "assert mode is CI; reconcile mode is wiring"):
`fleet_conformance` walks `OBLIGATION_ROWS` calling each row's
`assert_member`; `wire_fleet_member` walks the SAME rows calling
`reconcile` where the fix is machine-applicable (and surfacing
`manual_hint` where it is not — App installation, ci.yml authoring,
gitlink removal). The table is statically enumerated with explicit
typed imports so the type checker sees every dispatch target.

`parse_manifest` parses livespec core's `fleet-manifest.jsonc` (the
committed member list, fetched from livespec master at run time).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

from livespec_dev_tooling.fleet._context import FleetContext, FleetMember, RowOutcome
from livespec_dev_tooling.fleet._reconcile import (
    reconcile_branch_protection,
    reconcile_secret_names,
    reconcile_shim_workflows,
    reconcile_topic,
)
from livespec_dev_tooling.fleet._rows_files import (
    assert_bump_pin_workflow,
    assert_ci_workflow,
    assert_copier_answers,
    assert_dev_tooling_pin,
    assert_no_tracked_gitlinks,
    assert_pin_freshness_workflow,
    assert_release_dispatch_workflow,
)
from livespec_dev_tooling.fleet._rows_github import (
    assert_app_installation,
    assert_branch_protection,
    assert_secret_names,
    assert_topic,
)

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import jsoncomment  # noqa: E402  — vendor-path-aware import after sys.path insert.

__all__: list[str] = [
    "OBLIGATION_ROWS",
    "REPO_CLASSES",
    "Manifest",
    "ObligationRow",
    "parse_manifest",
    "rows_for",
]


REPO_CLASSES = ("core", "enforcement-suite", "impl-plugin", "driver-plugin", "library")

_ALL_CLASSES: frozenset[str] = frozenset(REPO_CLASSES)
# Every current class participates in the pin-and-bump web (verified
# 2026-06-12: all six members carry all three shim workflows), so the
# shim rows apply fleet-wide. The dev-tooling-pin row excludes only the
# enforcement-suite class — dev-tooling cannot pin itself.
_PIN_CONSUMING_CLASSES = _ALL_CLASSES
_TEMPLATE_BORN_CLASSES = frozenset({"impl-plugin"})
_DEV_TOOLING_PIN_CLASSES = _ALL_CLASSES - {"enforcement-suite"}


class RowFn(Protocol):
    """One obligation-row operation (assert or reconcile) over a member."""

    def __call__(self, *, ctx: FleetContext, member: FleetMember) -> RowOutcome: ...


@dataclass(frozen=True, kw_only=True)
class ObligationRow:
    """One per-class obligation: assert logic plus its reconcile reference.

    `reconcile` is None where the fix is not machine-applicable from
    this vantage point; `manual_hint` then tells the operator what to
    do (the hint never gates anything the check itself gates — the
    no-circular-gating rule).
    """

    row_id: str
    obligation_type: str
    applies_to: frozenset[str]
    assert_member: RowFn
    reconcile: RowFn | None = None
    manual_hint: str = ""


OBLIGATION_ROWS: tuple[ObligationRow, ...] = (
    ObligationRow(
        row_id="workflow-ci",
        obligation_type="committed-file",
        applies_to=_ALL_CLASSES,
        assert_member=assert_ci_workflow,
        manual_hint="author .github/workflows/ci.yml (no fleet-shipped template for this file)",
    ),
    ObligationRow(
        row_id="workflow-bump-pin-from-dispatch",
        obligation_type="committed-file",
        applies_to=_PIN_CONSUMING_CLASSES,
        assert_member=assert_bump_pin_workflow,
        reconcile=reconcile_shim_workflows,
    ),
    ObligationRow(
        row_id="workflow-pin-freshness",
        obligation_type="committed-file",
        applies_to=_PIN_CONSUMING_CLASSES,
        assert_member=assert_pin_freshness_workflow,
        reconcile=reconcile_shim_workflows,
    ),
    ObligationRow(
        row_id="workflow-release-dispatch",
        obligation_type="committed-file",
        applies_to=_PIN_CONSUMING_CLASSES,
        assert_member=assert_release_dispatch_workflow,
        reconcile=reconcile_shim_workflows,
    ),
    ObligationRow(
        row_id="copier-answers",
        obligation_type="committed-file",
        applies_to=_TEMPLATE_BORN_CLASSES,
        assert_member=assert_copier_answers,
        manual_hint="re-scaffold from the copier template so .copier-answers.yml is committed",
    ),
    ObligationRow(
        row_id="dev-tooling-pin",
        obligation_type="committed-file",
        applies_to=_DEV_TOOLING_PIN_CLASSES,
        assert_member=assert_dev_tooling_pin,
        manual_hint=(
            "add a [tool.uv.sources] livespec-dev-tooling tag pin to pyproject.toml; "
            "the bump-pin automation maintains it thereafter"
        ),
    ),
    ObligationRow(
        row_id="no-tracked-gitlinks",
        obligation_type="committed-file",
        applies_to=_ALL_CLASSES,
        assert_member=assert_no_tracked_gitlinks,
        manual_hint="remove the tracked gitlink (mode 160000) in a repo-local commit",
    ),
    ObligationRow(
        row_id="secret-names",
        obligation_type="github-state",
        applies_to=_ALL_CLASSES,
        assert_member=assert_secret_names,
        reconcile=reconcile_secret_names,
    ),
    ObligationRow(
        row_id="app-installation",
        obligation_type="github-state",
        applies_to=_ALL_CLASSES,
        assert_member=assert_app_installation,
        manual_hint="install the family GitHub App on the repo (owner settings → GitHub Apps)",
    ),
    ObligationRow(
        row_id="branch-protection",
        obligation_type="github-state",
        applies_to=_ALL_CLASSES,
        assert_member=assert_branch_protection,
        reconcile=reconcile_branch_protection,
    ),
    ObligationRow(
        row_id="topic-livespec-sibling",
        obligation_type="github-state",
        applies_to=_ALL_CLASSES,
        assert_member=assert_topic,
        reconcile=reconcile_topic,
    ),
)


def rows_for(*, repo_class: str) -> tuple[ObligationRow, ...]:
    """The obligation rows that apply to `repo_class`."""
    return tuple(row for row in OBLIGATION_ROWS if repo_class in row.applies_to)


@dataclass(frozen=True, kw_only=True)
class Manifest:
    """The parsed fleet manifest: owner + the member list."""

    owner: str
    members: tuple[FleetMember, ...]

    def member_names(self) -> frozenset[str]:
        """The set of member repo names (for the discovery sweep)."""
        return frozenset(member.repo for member in self.members)


def _parse_member(*, entry: object) -> FleetMember | None:
    """One manifest member entry, or None when malformed."""
    if not isinstance(entry, dict):
        return None
    record = cast("dict[str, object]", entry)
    repo = record.get("repo")
    repo_class = record.get("class")
    if not isinstance(repo, str) or repo_class not in REPO_CLASSES:
        return None
    return FleetMember(repo=repo, repo_class=cast("str", repo_class))


def parse_manifest(*, source: str) -> Manifest | None:
    """Parse `fleet-manifest.jsonc` text; None when malformed.

    Malformed means: invalid JSONC, a non-object root, a non-string
    `owner`, a non-list `members`, any malformed member entry (missing
    `repo`, unknown `class`), or duplicate member repos.
    """
    parser = jsoncomment.JsonComment()
    try:
        data = cast("object", parser.loads(source))
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    mapping = cast("dict[str, object]", data)
    owner = mapping.get("owner")
    members_raw = mapping.get("members")
    if not isinstance(owner, str) or not isinstance(members_raw, list):
        return None
    members: list[FleetMember] = []
    for entry in cast("list[object]", members_raw):
        member = _parse_member(entry=entry)
        if member is None:
            return None
        members.append(member)
    if len({member.repo for member in members}) != len(members):
        return None
    return Manifest(owner=owner, members=tuple(members))
