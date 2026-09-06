"""The central (GitHub-vantage) obligation table for the fleet contract.

ONE definition consumed by BOTH modes (livespec v108 section "Fleet
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

TWO SLICES of this table live in sibling modules and are spliced in below at
the positions their rows already occupied: the github-state slice
(`_contract_github_state_rows.py`, livespec-dev-tooling-oitd: this module had
reached 246 of its 250-LLOC hard ceiling, which silently closed the fleet's
one obligation table to new rows) and the pyproject-declaration slice
(`_contract_declaration_rows.py`, livespec-dev-tooling-lptplj: registering
`worktree-pack-wired` took the module to 262). Both cuts are along a family
the rows already formed, not at a line number. `OBLIGATION_ROWS` remains the
single exported table — a lane still reads exactly one name.
"""

from __future__ import annotations

from livespec_dev_tooling.fleet import _rows_pin_currency as pin_currency
from livespec_dev_tooling.fleet._contract_declaration_rows import DECLARATION_ROWS
from livespec_dev_tooling.fleet._contract_github_state_rows import GITHUB_STATE_ROWS
from livespec_dev_tooling.fleet._contract_model import (
    ADMIN_VANTAGE,
    CENTRAL_APP_VANTAGE,
    CENTRAL_VANTAGE,
    ObligationRow,
    RowFn,
)
from livespec_dev_tooling.fleet._reconcile_shims import reconcile_shim_workflows
from livespec_dev_tooling.fleet._rows_baseline import (
    assert_acceptance_mode_declared,
    assert_baseline_harnesses,
)
from livespec_dev_tooling.fleet._rows_beads import assert_tenant_connection_consistency
from livespec_dev_tooling.fleet._rows_claude_plugin import assert_claude_plugin_currency
from livespec_dev_tooling.fleet._rows_decision_authority import (
    assert_decision_authority_section,
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
from livespec_dev_tooling.fleet._rows_foreman_valve import (
    assert_foreman_valve_declared,
)
from livespec_dev_tooling.fleet._rows_instructions import (
    AGENT_INSTRUCTION_SURFACE_HINT,
    assert_agent_ai_references_resolve,
    assert_agent_instruction_surface,
)
from livespec_dev_tooling.fleet._rows_worktree_pack import assert_worktree_pack_wired

__all__: list[str] = [
    "ADMIN_VANTAGE",
    "CENTRAL_APP_VANTAGE",
    "CENTRAL_VANTAGE",
    "OBLIGATION_ROWS",
    "REPO_CLASSES",
    "ObligationRow",
    "rows_for",
]


from livespec_dev_tooling.fleet._contract_classes import (
    ALL_CLASSES,
    DEV_TOOLING_PIN_CLASSES,
    PIN_WEB_CLASSES,
    RECEIVING_SHIM_CLASSES,
    REPO_CLASSES,
    TEMPLATE_BORN_CLASSES,
    WORKTREE_PACK_CLASSES,
)


def _warning_committed_file_row(*, row_id: str, assert_member: RowFn) -> ObligationRow:
    return ObligationRow(
        row_id=row_id,
        obligation_type="committed-file",
        applies_to=ALL_CLASSES,
        assert_member=assert_member,
        manual_hint="update stale pin records to the latest source release",
    )


def _manual_committed_file_row(
    *,
    row_id: str,
    assert_member: RowFn,
    manual_hint: str,
    applies_to: frozenset[str] = ALL_CLASSES,
) -> ObligationRow:
    return ObligationRow(
        row_id=row_id,
        obligation_type="committed-file",
        applies_to=applies_to,
        assert_member=assert_member,
        manual_hint=manual_hint,
    )


OBLIGATION_ROWS: tuple[ObligationRow, ...] = (
    _manual_committed_file_row(
        row_id="workflow-ci",
        assert_member=assert_ci_workflow,
        manual_hint="author .github/workflows/ci.yml (no fleet-shipped template for this file)",
    ),
    ObligationRow(
        row_id="workflow-bump-pin-from-dispatch",
        obligation_type="committed-file",
        applies_to=RECEIVING_SHIM_CLASSES,
        assert_member=assert_bump_pin_workflow,
        reconcile=reconcile_shim_workflows,
    ),
    ObligationRow(
        row_id="workflow-pin-freshness",
        obligation_type="committed-file",
        applies_to=RECEIVING_SHIM_CLASSES,
        assert_member=assert_pin_freshness_workflow,
        reconcile=reconcile_shim_workflows,
    ),
    ObligationRow(
        row_id="workflow-release-dispatch",
        obligation_type="committed-file",
        applies_to=PIN_WEB_CLASSES,
        assert_member=assert_release_dispatch_workflow,
        reconcile=reconcile_shim_workflows,
    ),
    _manual_committed_file_row(
        row_id="copier-answers",
        applies_to=TEMPLATE_BORN_CLASSES,
        assert_member=assert_copier_answers,
        manual_hint="re-scaffold from the copier template so .copier-answers.yml is committed",
    ),
    _manual_committed_file_row(
        row_id="dev-tooling-pin",
        applies_to=DEV_TOOLING_PIN_CLASSES,
        assert_member=assert_dev_tooling_pin,
        manual_hint=(
            "add a [tool.uv.sources] livespec-dev-tooling tag pin to pyproject.toml; "
            "the bump-pin automation maintains it thereafter"
        ),
    ),
    _manual_committed_file_row(
        row_id="no-tracked-gitlinks",
        assert_member=assert_no_tracked_gitlinks,
        manual_hint="remove the tracked gitlink (mode 160000) in a repo-local commit",
    ),
    # The pyproject-declaration slice, verbatim and in position, from
    # `_contract_declaration_rows.py`.
    *DECLARATION_ROWS,
    _warning_committed_file_row(
        row_id="compat-pin-currency", assert_member=pin_currency.assert_livespec_compat_pin_currency
    ),
    _warning_committed_file_row(
        row_id="uses-pin-currency",
        assert_member=pin_currency.assert_github_workflow_uses_pin_currency,
    ),
    _warning_committed_file_row(
        row_id="fabro-pin-currency",
        assert_member=pin_currency.assert_fabro_sandbox_image_pin_currency,
    ),
    _manual_committed_file_row(
        row_id="claude-plugin-currency",
        assert_member=assert_claude_plugin_currency,
        manual_hint=(
            "wire .claude/settings.json SessionStart to `mise exec -- just ensure-plugins` "
            "and make the justfile ensure-plugins recipe the standard "
            "`mise exec -- uv run --no-sync python -m livespec_dev_tooling.fleet.ensure_plugins` "
            "wrapper, or declare livespecPluginCurrencySuccessor with mechanism + documentedIn"
        ),
    ),
    # The github-state slice, verbatim and in position, from
    # `_contract_github_state_rows.py`.
    *GITHUB_STATE_ROWS,
    _manual_committed_file_row(
        row_id="beads-tenant-connection-consistency",
        assert_member=assert_tenant_connection_consistency,
        manual_hint=(
            "reconcile .beads/config.yaml (dolt.* keys) and .livespec.jsonc's impl-plugin "
            "connection block so the five tenant-connection fields agree, in a repo-local commit"
        ),
    ),
    _manual_committed_file_row(
        row_id="agent-instruction-surface",
        applies_to=TEMPLATE_BORN_CLASSES,
        assert_member=assert_agent_instruction_surface,
        # Homed with the row rather than spelled here: the hint QUOTES the
        # fleet-universal sentence the row demands, so it must be the same
        # string the finding quotes and the row's fixture is built from.
        manual_hint=AGENT_INSTRUCTION_SURFACE_HINT,
    ),
    # ARMED 2026-08-20, after all nine adoptions landed and the offender
    # count was re-measured at ZERO on origin/master across all ten governed
    # members. The row itself shipped DISARMED in the preceding commit for
    # the reason `plan/rop-railway-enforcement/` records as a standing
    # constraint: 46c5dab armed the Railway check ahead of adoption, five
    # repos went red, and f4247110 reverted it.
    #
    # ALL_CLASSES rather than TEMPLATE_BORN_CLASSES, unlike the sibling
    # agent-instruction-surface row above: this obligation is not about how
    # a repo was scaffolded. Every governed member has sessions, and every
    # one of them should be told what it is allowed to decide.
    _manual_committed_file_row(
        row_id="decision-authority-section",
        assert_member=assert_decision_authority_section,
        manual_hint=(
            "add a decision-authority section to AGENTS.md carrying all three markers "
            '("When to ask, proceed, or self-resolve", "do not over-ask", '
            '"Decision authority"), adapted from livespec/AGENTS.md rather than invented, '
            "in a repo-local commit"
        ),
    ),
    # ARMED AT BIRTH, 2026-08-21, and the precondition was measured before the
    # row was registered rather than after: the fleet-wide fan-out landed FIRST
    # and all 14 governed members were re-measured on their own origin/master
    # as declaring the key. The sibling decision-authority row above shipped
    # DISARMED for the reason plan/rop-railway-enforcement/ records; that
    # ordering is respected here, not skipped. Arming at birth is safe ONLY
    # because the offender count was already zero.
    #
    # ALL_CLASSES: every governed member runs foreman seats, and every one of
    # them should have CHOSEN a valve disposition rather than inherited the
    # fail-closed default in silence.
    _manual_committed_file_row(
        row_id="foreman-valve-declared",
        assert_member=assert_foreman_valve_declared,
        manual_hint=(
            "declare livespec-overseer.foreman_valve_disposition in .livespec.jsonc "
            '(either "consensus" or "report-only" — the row asserts that the repo '
            "CHOSE, not which way), in a repo-local commit. An absent key silently "
            "fail-closes to report-only, where the foreman surfaces every human valve "
            "and acts on none"
        ),
    ),
    _manual_committed_file_row(
        row_id="agent-ai-references-resolve",
        assert_member=assert_agent_ai_references_resolve,
        manual_hint=(
            "add the missing .ai/<topic>.md file(s) an AGENTS.md references, or remove the "
            "dangling reference, in a repo-local commit"
        ),
    ),
    _manual_committed_file_row(
        row_id="baseline-harnesses",
        assert_member=assert_baseline_harnesses,
        manual_hint=(
            "declare a non-empty `harnesses` object in .livespec.jsonc (Conformance "
            "Pattern concern #2 cross-harness plugin-resolution; zs22.7.7 M6)"
        ),
    ),
    # The sibling of the row above, and the same kind of obligation: state the
    # decision instead of leaving a default to stand in for one. Silence here is
    # what let five governed repos sit off the fleet acceptance standard
    # un-noticed until 2026-07-29.
    # ARMED AT BIRTH, 2026-09-06, on a measurement taken BEFORE the row was
    # registered rather than after — the ordering `plan/rop-railway-enforcement/`
    # records as a standing constraint (46c5dab armed a check ahead of adoption,
    # five repos went red, f4247110 reverted it). All ten manifest members were
    # read on their own committed master: the four ERROR-severity legs have an
    # offender count of zero, and the one WARNING-severity leg has exactly one
    # (livespec-runtime's root .gitignore omits `/dev-tooling/gate-run.sh`),
    # which reports without gating. The severity split is a judgement about
    # consequence, not a soft-arming device — the module docstring states it.
    #
    # This is the row that makes pack WIRING visible at all: the two repo-local
    # mechanisms assert the pack's BYTES from inside a checkout that already
    # runs them, so a member that never wires the pack never fails a check it
    # does not run.
    _manual_committed_file_row(
        row_id="worktree-pack-wired",
        applies_to=WORKTREE_PACK_CLASSES,
        assert_member=assert_worktree_pack_wired,
        manual_hint=(
            "add the exact wiring lines the finding names to the member's justfile, "
            ".gitignore, lefthook.yml and .livespec.jsonc, in a repo-local commit — "
            "`just install-worktree-pack` materializes the pack itself but edits no "
            "TRACKED file, so the justfile, the root .gitignore, lefthook.yml and the "
            "worktree_discipline declaration are all yours to commit (the installer "
            "prints the declaration line as guidance; livespec-dev-tooling-7ix8)"
        ),
    ),
    _manual_committed_file_row(
        row_id="acceptance-mode-declared",
        assert_member=assert_acceptance_mode_declared,
        manual_hint=(
            "declare `dispatcher.acceptance_mode` explicitly in the .livespec.jsonc "
            "impl-plugin block (one of ai-only / ai-then-human / human-only); the value is "
            "the repo's own call, but omitting it silently inherits the ai-then-human default"
        ),
    ),
)


def rows_for(*, repo_class: str) -> tuple[ObligationRow, ...]:
    """The obligation rows that apply to `repo_class`."""
    return tuple(row for row in OBLIGATION_ROWS if repo_class in row.applies_to)
