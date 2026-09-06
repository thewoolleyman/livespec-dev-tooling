"""Tests for `livespec_dev_tooling/fleet/_contract_rows.py`.

Covers the central (GitHub-vantage) obligation-table integrity
invariants the two consuming engines rely on: unique row ids, known
classes, reconcile-or-manual-hint completeness, per-class scoping via
`rows_for`, and the wiring of the individually load-bearing rows.
"""

from __future__ import annotations

from _gh_railway import lift_gh

from livespec_dev_tooling.fleet._context import (
    FleetContext,
    FleetMember,
    GhResult,
    GhRunner,
    RowFinding,
    RowPass,
)
from livespec_dev_tooling.fleet._contract_classes import WORKTREE_PACK_CLASSES
from livespec_dev_tooling.fleet._contract_rows import (
    CENTRAL_APP_VANTAGE,
    OBLIGATION_ROWS,
    REPO_CLASSES,
    rows_for,
)
from livespec_dev_tooling.fleet._lanes import LANE_RECIPES
from livespec_dev_tooling.fleet._reconcile import reconcile_merge_settings
from livespec_dev_tooling.fleet._rows_baseline import assert_baseline_harnesses
from livespec_dev_tooling.fleet._rows_github import assert_merge_settings
from livespec_dev_tooling.fleet._rows_instructions import assert_agent_ai_references_resolve
from livespec_dev_tooling.fleet._rows_public_api_conformance import (
    assert_cross_repo_public_api_declared,
)
from livespec_dev_tooling.fleet._rows_role_key_spellings import (
    assert_role_key_spellings_conformant,
)
from livespec_dev_tooling.fleet._rows_worktree_pack import assert_worktree_pack_wired

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


def test_every_declared_vantage_has_an_owning_context_registered() -> None:
    # An out-of-vantage report is only actionable when it names the owning
    # context; a row whose vantage has no LANE_RECIPES entry would report
    # "(no lane runs this vantage)" — exactly the zero-enforcement hole the
    # vantage split exists to close. Wiring-pinned so adding a vantage to
    # the table without registering its owner fails fast.
    for row in OBLIGATION_ROWS:
        assert row.vantage in LANE_RECIPES, row.row_id


def test_app_installation_row_carries_the_central_app_vantage() -> None:
    # The app-installation read (`GET /installation/repositories`) answers
    # only under the fleet App installation token, which exactly the
    # automated central contexts hold — declared on the row (the same
    # mechanism the two admin rows use) so a local central sweep reports
    # it out-of-vantage naming those contexts instead of blind
    # (livespec-dev-tooling-29qo).
    row = next((r for r in OBLIGATION_ROWS if r.row_id == "app-installation"), None)
    assert row is not None
    assert row.vantage == CENTRAL_APP_VANTAGE
    assert row.reconcile is None
    assert row.manual_hint


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


def test_role_key_spellings_row_is_registered_for_every_class() -> None:
    # REGISTRATION is the whole point of this assertion, not a formality.
    # `_rows_role_key_spellings.py` can be complete, tested and green while
    # scanning nothing at all, because a row absent from OBLIGATION_ROWS is
    # walked by neither engine — which is the defect shape
    # livespec-dev-tooling-8o8e exists to remove, reproduced inside its own
    # fix. It binds to EVERY class because the ambiguous spelling is a
    # property of the config schema, which every config-bearing member shares;
    # a member with no [tool.livespec_dev_tooling] block excludes itself with
    # a stated reason at row-evaluation time rather than by class scoping.
    row = next((r for r in OBLIGATION_ROWS if r.row_id == "role-key-spellings"), None)
    assert row is not None
    assert row.obligation_type == "committed-file"
    assert row.applies_to == frozenset(REPO_CLASSES)
    assert row.assert_member is assert_role_key_spellings_conformant
    assert row.reconcile is None
    assert row.manual_hint


def test_cross_repo_public_api_row_is_registered_for_every_class() -> None:
    """REGISTRATION is the entire deliverable, and this guards a state that existed.

    `_rows_public_api_conformance.py` shipped COMPLETE, TESTED and GREEN while
    being walked by NEITHER engine — the `role-key-spellings` precedent above,
    and the same defect shape `livespec-dev-tooling-8o8e` exists to remove.

    It held that way ON PURPOSE. The pre-registration measurement (all nine
    members' master tarballs, 0 skipped, 0 unparsed) found TWENTY genuine
    undeclared consumptions — nine here, eleven in `livespec-runtime`.
    Registering at error severity then would have fired BOTH blocking modes:
    this repo's own failing row makes `own_failing_rows` non-empty, so the
    registering PR's OWN CI fails and it cannot land; and the sibling's would
    have left this repo green while breaking the scheduled sweep and the
    release fan-out preflight fleet-wide. Both were remediated first (`wdn7`,
    `nkkv`) and the fleet re-measured PASSING before the flip —
    REMEDIATE-THEN-FLIP, this repo's own ratified v034 carve-out 1. The
    severity was never softened to get around the collision.

    EVERY CLASS, because "does a sibling consume a name you did not declare?"
    is a question about the fleet graph and every member is a node in it. A
    member with no first-party Python has no outgoing edges and passes ON THE
    MERITS rather than by class scoping; a member whose tree or config cannot
    be read reports a NAMED skip, never a silent pass.
    """
    row = next((r for r in OBLIGATION_ROWS if r.row_id == "cross-repo-public-api-declared"), None)
    assert row is not None
    assert row.obligation_type == "committed-file"
    assert row.applies_to == frozenset(REPO_CLASSES)
    assert row.assert_member is assert_cross_repo_public_api_declared
    # No reconcile: the fix is a per-entry WRITTEN REASON naming the consuming
    # member, which is a judgement rather than a mechanical edit. A machine that
    # bulk-filled this key would manufacture exactly the unreasoned bulk
    # declaration the key exists to prevent.
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
    # non-functional-requirements.md section "Fleet membership contract", ratified
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


def test_decision_authority_row_is_registered_for_every_governed_class() -> None:
    # ARMING (livespec-dev-tooling-sle7ey.9). The row was authored in
    # sle7ey.8 and shipped DISARMED — present, tested, and deliberately
    # absent from OBLIGATION_ROWS — because a check armed before the repos
    # it judges have adopted the shape writes verdicts into a fleet that
    # cannot satisfy them (46c5dab armed the Railway check early, five
    # repos went red, f4247110 reverted it). All nine adoptions landed
    # first, and the offender count was re-measured at zero on
    # origin/master immediately before this row was registered.
    #
    # Unlike agent-instruction-surface, this row is NOT template-born
    # scoped: every governed member is expected to tell its sessions what
    # they may decide, and all ten were measured carrying the section.
    for repo_class in REPO_CLASSES:
        assert "decision-authority-section" in {
            row.row_id for row in rows_for(repo_class=repo_class)
        }


def test_the_armed_decision_authority_row_is_not_vacuous() -> None:
    # NON-VACUITY, reached THROUGH the table rather than by importing the
    # assert directly — that is the whole point. A row can be registered
    # and still never fire if the table hands it the wrong callable, so
    # this resolves the row by id and calls whatever OBLIGATION_ROWS
    # actually holds.
    #
    # The work-item asked for this proof as "a deliberate local removal of
    # the section from one repo". That exact gesture is not available to
    # this check by construction: it reads AGENTS.md at the member's
    # canonical ref through the contents API, never a working tree, which
    # is its own acceptance criterion. A canned member whose AGENTS.md
    # lacks the section is the same experiment against the surface the
    # check actually reads.
    row = next(row for row in OBLIGATION_ROWS if row.row_id == "decision-authority-section")
    ctx = _decision_authority_context(agents_text="# Agent instructions\n\n## Daily commands\n")
    outcome = row.assert_member(ctx=ctx, member=FleetMember(repo="widget", repo_class="library"))
    assert isinstance(outcome, RowFinding)
    assert "widget" in outcome.message


def test_the_armed_decision_authority_row_passes_an_adopted_member() -> None:
    # The other direction, also through the table: a member carrying the
    # section passes, so the row above is failing on absence rather than
    # failing always.
    row = next(row for row in OBLIGATION_ROWS if row.row_id == "decision-authority-section")
    adopted = (
        "## Decision authority \u2014 when to ask, proceed, or self-resolve\n"
        "\n"
        "- **Drive authorized work to completion; do not over-ask.**\n"
    )
    ctx = _decision_authority_context(agents_text=adopted)
    outcome = row.assert_member(ctx=ctx, member=FleetMember(repo="widget", repo_class="library"))
    assert outcome == RowPass()


def _decision_authority_context(*, agents_text: str) -> FleetContext:
    """A canned `FleetContext` serving `agents_text` as widget's AGENTS.md."""
    table = {
        (
            "api",
            "repos/acme/widget/contents/AGENTS.md?ref=master",
            "-H",
            "Accept: application/vnd.github.raw",
        ): GhResult(returncode=0, stdout=agents_text, stderr="")
    }

    def run(*, args: list[str], stdin: str | None = None) -> GhResult:
        del stdin
        return table.get(tuple(args), GhResult(returncode=1, stdout="", stderr="no canned"))

    runner: GhRunner = run
    return FleetContext(owner="acme", run_gh=lift_gh(runner))


def test_worktree_pack_wired_row_is_scoped_by_class_and_manual_only() -> None:
    # Scoped by the CLASS CONSTANT, never by repo name: the obligation follows
    # from a class running the worktree-pack verifier, and every class does
    # today. Manual-only because the fix is four line-edits in the member's own
    # repo — the hint plus the finding name them.
    row = next(row for row in OBLIGATION_ROWS if row.row_id == "worktree-pack-wired")
    assert row.assert_member is assert_worktree_pack_wired
    assert row.applies_to is WORKTREE_PACK_CLASSES
    assert row.applies_to == frozenset(REPO_CLASSES)
    assert row.obligation_type == "committed-file"
    assert row.reconcile is None
    assert row.manual_hint
