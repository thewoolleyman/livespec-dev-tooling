"""Tests for `livespec_dev_tooling/fleet/_contract_rows.py`.

Covers the central (GitHub-vantage) obligation-table integrity
invariants the two consuming engines rely on: unique row ids, known
classes, reconcile-or-manual-hint completeness, per-class scoping via
`rows_for`, and the wiring of the individually load-bearing rows.
"""

from __future__ import annotations

from livespec_dev_tooling.fleet._contract_rows import OBLIGATION_ROWS, REPO_CLASSES, rows_for
from livespec_dev_tooling.fleet._reconcile import reconcile_merge_settings
from livespec_dev_tooling.fleet._rows_baseline import assert_baseline_harnesses
from livespec_dev_tooling.fleet._rows_github import assert_merge_settings
from livespec_dev_tooling.fleet._rows_instructions import assert_agent_ai_references_resolve

__all__: list[str] = []


def test_obligation_row_ids_are_unique_and_classes_known() -> None:
    row_ids = [row.row_id for row in OBLIGATION_ROWS]
    assert len(set(row_ids)) == len(row_ids)
    for row in OBLIGATION_ROWS:
        assert row.applies_to <= frozenset(REPO_CLASSES), row.row_id
        assert row.obligation_type in {"committed-file", "github-state"}, row.row_id


def test_every_row_is_reconcilable_or_carries_a_manual_hint() -> None:
    for row in OBLIGATION_ROWS:
        assert row.reconcile is not None or row.manual_hint, row.row_id


def test_rows_for_filters_by_class() -> None:
    impl_rows = {row.row_id for row in rows_for(repo_class="impl-plugin")}
    assert "copier-answers" in impl_rows
    assert "dev-tooling-pin" in impl_rows
    enforcement_rows = {row.row_id for row in rows_for(repo_class="enforcement-suite")}
    assert "copier-answers" not in enforcement_rows
    assert "dev-tooling-pin" not in enforcement_rows
    assert "workflow-bump-pin-from-dispatch" in enforcement_rows
    core_rows = {row.row_id for row in rows_for(repo_class="core")}
    assert "copier-answers" not in core_rows
    assert "dev-tooling-pin" in core_rows


def test_universal_rows_apply_to_every_class() -> None:
    universal = {
        "workflow-ci",
        "no-tracked-gitlinks",
        "secret-names",
        "app-installation",
        "branch-protection",
        "merge-settings",
        "topic-livespec-sibling",
    }
    for repo_class in REPO_CLASSES:
        row_ids = {row.row_id for row in rows_for(repo_class=repo_class)}
        assert universal <= row_ids, repo_class


def test_merge_settings_row_is_wired_with_assert_and_reconcile() -> None:
    # The merge-settings row must be registered with BOTH its assert
    # (fleet_conformance, CI mode) and its reconcile (wire-fleet-member),
    # exactly like branch-protection — so a freshly-scaffolded fleet
    # repo's default allow_merge_commit=true is both caught and fixed.
    row = next((r for r in OBLIGATION_ROWS if r.row_id == "merge-settings"), None)
    assert row is not None
    assert row.obligation_type == "github-state"
    assert row.applies_to == frozenset(REPO_CLASSES)
    assert row.assert_member is assert_merge_settings
    assert row.reconcile is reconcile_merge_settings


def test_agent_ai_references_resolve_row_is_wired_for_every_class() -> None:
    # The .ai/-reference resolvability obligation applies to EVERY member
    # (livespec core itself carries a concrete .ai/ reference), is a
    # committed-file fact, and is not machine-reconcilable from the central
    # vantage point — so it carries a manual hint instead of a reconcile.
    row = next((r for r in OBLIGATION_ROWS if r.row_id == "agent-ai-references-resolve"), None)
    assert row is not None
    assert row.obligation_type == "committed-file"
    assert row.applies_to == frozenset(REPO_CLASSES)
    assert row.assert_member is assert_agent_ai_references_resolve
    assert row.reconcile is None
    assert row.manual_hint


def test_baseline_harnesses_row_is_wired_for_every_class() -> None:
    # The baseline-harnesses obligation (Conformance Pattern concern #2,
    # cross-harness plugin-resolution) applies to EVERY governed member, is
    # a committed-file fact (the .livespec.jsonc `harnesses` declaration),
    # and is not machine-reconcilable from the central vantage point — so it
    # carries a manual hint instead of a reconcile.
    row = next((r for r in OBLIGATION_ROWS if r.row_id == "baseline-harnesses"), None)
    assert row is not None
    assert row.obligation_type == "committed-file"
    assert row.applies_to == frozenset(REPO_CLASSES)
    assert row.assert_member is assert_baseline_harnesses
    assert row.reconcile is None
    assert row.manual_hint


def test_console_class_scopes_pin_web_rows() -> None:
    # The Control-Plane console (livespec-console-beads-fabro) is a pin
    # CONSUMER: its toolchain gates come from livespec-dev-tooling, so it
    # carries the dev-tooling pin AND ships the two RECEIVING shims
    # (bump-pin-from-dispatch + pin-freshness) that keep that pin fresh. It
    # does NOT ship the release-dispatch PRODUCER shim, because it produces
    # no consumable release for downstream repos to pin. So the console class
    # is IN the two receiving-shim rows, the dev-tooling-pin row, and every
    # universal row, but EXCLUDED from the release-dispatch row; it is also
    # outside the template-born rows (no copier-answers /
    # agent-instruction-surface), per the per-class applies_to scoping
    # (livespec-oq9w Option B).
    assert "console" in REPO_CLASSES
    console_rows = {row.row_id for row in rows_for(repo_class="console")}
    assert "dev-tooling-pin" in console_rows
    assert "workflow-bump-pin-from-dispatch" in console_rows
    assert "workflow-pin-freshness" in console_rows
    assert "workflow-release-dispatch" not in console_rows
    assert "copier-answers" not in console_rows
    assert "agent-instruction-surface" not in console_rows
    assert "workflow-ci" in console_rows
    assert "no-tracked-gitlinks" in console_rows
    assert "beads-tenant-connection-consistency" in console_rows
    assert "baseline-harnesses" in console_rows


def test_control_plane_tool_class_is_pin_consuming_unlike_console() -> None:
    # `control-plane-tool` is the second Control-Plane class: a member that
    # ships an operator TOOL rather than the cockpit APPLICATION `console`
    # carries, a PEER of `console` and never a component of it (livespec
    # non-functional-requirements.md §"Fleet membership contract", ratified
    # v171). The distinguishing property — and the whole reason `console`
    # could not simply be reused — is that this class IS a pin-and-bump
    # consumer: its ruff / pyright-strict / coverage / Result-railway gates
    # come from livespec-dev-tooling, so a dev-tooling release directly
    # determines whether such a member stays green. `_PIN_WEB_CLASSES` is the
    # subtraction set `_ALL_CLASSES - {"console"}`, so the three shim rows
    # attach automatically; asserting them here is what pins that the new
    # class did NOT inherit the console's pin-web exemption.
    assert "control-plane-tool" in REPO_CLASSES
    tool_rows = {row.row_id for row in rows_for(repo_class="control-plane-tool")}
    assert "workflow-bump-pin-from-dispatch" in tool_rows
    assert "workflow-pin-freshness" in tool_rows
    assert "workflow-release-dispatch" in tool_rows
    assert "dev-tooling-pin" in tool_rows
    # Not template-born: only `impl-plugin` is, so the copier-scaffold rows
    # stay off this class (`_TEMPLATE_BORN_CLASSES` is the one ADDITIVE set,
    # which is why a newly-added class is excluded from it for free).
    assert "copier-answers" not in tool_rows
    assert "agent-instruction-surface" not in tool_rows
    # The universal rows still bind.
    assert "workflow-ci" in tool_rows
    assert "no-tracked-gitlinks" in tool_rows
    assert "beads-tenant-connection-consistency" in tool_rows
    assert "baseline-harnesses" in tool_rows
