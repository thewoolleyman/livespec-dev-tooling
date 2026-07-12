"""The central (GitHub-vantage) obligation table for the fleet contract.

ONE definition consumed by BOTH modes (livespec v108 §"Fleet
membership contract": "assert mode is CI; reconcile mode is wiring"):
`fleet_conformance` walks `OBLIGATION_ROWS` calling each row's
`assert_member`; `wire_fleet_member` walks the SAME rows calling
`reconcile` where the fix is machine-applicable (and surfacing
`manual_hint` where it is not — App installation, ci.yml authoring,
gitlink removal). The table is statically enumerated with explicit
typed imports so the type checker sees every dispatch target.

`REPO_CLASSES` is HOMED here (the class partition the obligation
`applies_to` frozensets are derived from) and re-imported by
`contract.py` for the manifest parser; the LOCAL-vantage table lives in
`_contract_local_rows.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from livespec_dev_tooling.fleet._context import FleetContext, FleetMember, RowOutcome
from livespec_dev_tooling.fleet._reconcile import (
    reconcile_branch_protection,
    reconcile_delete_branch_on_merge,
    reconcile_merge_settings,
    reconcile_secret_names,
    reconcile_shim_workflows,
    reconcile_topic,
)
from livespec_dev_tooling.fleet._rows_baseline import assert_baseline_harnesses
from livespec_dev_tooling.fleet._rows_beads import assert_tenant_connection_consistency
from livespec_dev_tooling.fleet._rows_claude_plugin import assert_claude_plugin_currency
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
    assert_delete_branch_on_merge,
    assert_merge_settings,
    assert_secret_names,
    assert_topic,
)
from livespec_dev_tooling.fleet._rows_instructions import (
    assert_agent_ai_references_resolve,
    assert_agent_instruction_surface,
)

__all__: list[str] = [
    "OBLIGATION_ROWS",
    "REPO_CLASSES",
    "ObligationRow",
    "rows_for",
]


REPO_CLASSES = ("core", "enforcement-suite", "impl-plugin", "driver-plugin", "library", "console")

_ALL_CLASSES: frozenset[str] = frozenset(REPO_CLASSES)
# The classes participating in the pin-and-bump web — i.e. carrying the
# three shim workflows (bump-pin-from-dispatch / pin-freshness /
# release-dispatch). Every class EXCEPT the Control-Plane console: the
# console (livespec-console-beads-fabro) is a non-pin-consuming fleet
# member that carries the dev-tooling pin (see _DEV_TOOLING_PIN_CLASSES)
# but ships none of the shims, so its pin freshness is monitored centrally
# by the dev-tooling-pin row's warning-severity staleness leg rather than
# auto-bumped (livespec-dev-tooling contracts.md §"Bump-pin policy").
_PIN_WEB_CLASSES = _ALL_CLASSES - {"console"}
_TEMPLATE_BORN_CLASSES = frozenset({"impl-plugin"})
# The dev-tooling-pin row excludes only the enforcement-suite class —
# dev-tooling cannot pin itself; every other class, the console included,
# carries a [tool.uv.sources] livespec-dev-tooling tag pin.
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
        applies_to=_PIN_WEB_CLASSES,
        assert_member=assert_bump_pin_workflow,
        reconcile=reconcile_shim_workflows,
    ),
    ObligationRow(
        row_id="workflow-pin-freshness",
        obligation_type="committed-file",
        applies_to=_PIN_WEB_CLASSES,
        assert_member=assert_pin_freshness_workflow,
        reconcile=reconcile_shim_workflows,
    ),
    ObligationRow(
        row_id="workflow-release-dispatch",
        obligation_type="committed-file",
        applies_to=_PIN_WEB_CLASSES,
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
        row_id="claude-plugin-currency",
        obligation_type="committed-file",
        applies_to=_ALL_CLASSES,
        assert_member=assert_claude_plugin_currency,
        manual_hint=(
            "wire .claude/settings.json SessionStart to `mise exec -- just ensure-plugins` "
            "and make the justfile ensure-plugins recipe the standard "
            "`mise exec -- uv run --no-sync python -m livespec_dev_tooling.fleet.ensure_plugins` "
            "wrapper, or declare livespecPluginCurrencySuccessor with mechanism + documentedIn"
        ),
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
        manual_hint="install the fleet GitHub App on the repo (owner settings → GitHub Apps)",
    ),
    ObligationRow(
        row_id="branch-protection",
        obligation_type="github-state",
        applies_to=_ALL_CLASSES,
        assert_member=assert_branch_protection,
        reconcile=reconcile_branch_protection,
    ),
    ObligationRow(
        row_id="merge-settings",
        obligation_type="github-state",
        applies_to=_ALL_CLASSES,
        assert_member=assert_merge_settings,
        reconcile=reconcile_merge_settings,
    ),
    ObligationRow(
        row_id="delete-branch-on-merge",
        obligation_type="github-state",
        applies_to=_ALL_CLASSES,
        assert_member=assert_delete_branch_on_merge,
        reconcile=reconcile_delete_branch_on_merge,
    ),
    ObligationRow(
        row_id="topic-livespec-sibling",
        obligation_type="github-state",
        applies_to=_ALL_CLASSES,
        assert_member=assert_topic,
        reconcile=reconcile_topic,
    ),
    ObligationRow(
        row_id="beads-tenant-connection-consistency",
        obligation_type="committed-file",
        applies_to=_ALL_CLASSES,
        assert_member=assert_tenant_connection_consistency,
        manual_hint=(
            "reconcile .beads/config.yaml (dolt.* keys) and .livespec.jsonc's impl-plugin "
            "connection block so the five tenant-connection fields agree, in a repo-local commit"
        ),
    ),
    ObligationRow(
        row_id="agent-instruction-surface",
        obligation_type="committed-file",
        applies_to=_TEMPLATE_BORN_CLASSES,
        assert_member=assert_agent_instruction_surface,
        manual_hint=(
            "bring AGENTS.md up to the fleet-universal agent-instruction core and register the "
            "beads-access guard hook (.claude/hooks/beads-access-guard.sh) in "
            ".claude/settings.json, in a repo-local commit"
        ),
    ),
    ObligationRow(
        row_id="agent-ai-references-resolve",
        obligation_type="committed-file",
        applies_to=_ALL_CLASSES,
        assert_member=assert_agent_ai_references_resolve,
        manual_hint=(
            "add the missing .ai/<topic>.md file(s) an AGENTS.md references, or remove the "
            "dangling reference, in a repo-local commit"
        ),
    ),
    ObligationRow(
        row_id="baseline-harnesses",
        obligation_type="committed-file",
        applies_to=_ALL_CLASSES,
        assert_member=assert_baseline_harnesses,
        manual_hint=(
            "declare a non-empty `harnesses` object in .livespec.jsonc (Conformance "
            "Pattern concern #2 cross-harness plugin-resolution; zs22.7.7 M6)"
        ),
    ),
)


def rows_for(*, repo_class: str) -> tuple[ObligationRow, ...]:
    """The obligation rows that apply to `repo_class`."""
    return tuple(row for row in OBLIGATION_ROWS if repo_class in row.applies_to)
