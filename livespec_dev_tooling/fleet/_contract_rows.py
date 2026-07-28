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

The github-state SLICE of this table lives in
`_contract_github_state_rows.py` and is spliced in below at the position
those rows already occupied (livespec-dev-tooling-oitd: this module had
reached 246 of its 250-LLOC hard ceiling, which silently closed the fleet's
one obligation table to new rows). `OBLIGATION_ROWS` remains the single
exported table — a lane still reads exactly one name.
"""

from __future__ import annotations

from livespec_dev_tooling.fleet import _rows_pin_currency as pin_currency
from livespec_dev_tooling.fleet._contract_github_state_rows import GITHUB_STATE_ROWS
from livespec_dev_tooling.fleet._contract_model import (
    ADMIN_VANTAGE,
    CENTRAL_APP_VANTAGE,
    CENTRAL_VANTAGE,
    ObligationRow,
    RowFn,
)
from livespec_dev_tooling.fleet._reconcile import reconcile_shim_workflows
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
from livespec_dev_tooling.fleet._rows_instructions import (
    assert_agent_ai_references_resolve,
    assert_agent_instruction_surface,
)
from livespec_dev_tooling.fleet._rows_required_role_keys import (
    assert_required_role_keys_declared,
)
from livespec_dev_tooling.fleet._rows_role_key_spellings import (
    assert_role_key_spellings_conformant,
)

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
    _manual_committed_file_row(
        row_id="required-role-keys-declared",
        assert_member=assert_required_role_keys_declared,
        manual_hint=(
            "declare every REQUIRED_ROLE_KEYS entry in [tool.livespec_dev_tooling], or "
            "declare sanctioned-empty values with comments explaining the absent role"
        ),
    ),
    # The sibling of the row above: that one asserts the required keys are
    # DECLARED, this one asserts the declaration uses a blessed SPELLING. A key
    # declared `[]` satisfies the first and is exactly the ambiguity the second
    # exists to reject (livespec-dev-tooling-8o8e.1 Phase 3).
    _manual_committed_file_row(
        row_id="role-key-spellings",
        assert_member=assert_role_key_spellings_conformant,
        manual_hint=(
            "replace the retired ambiguous empty spelling on the named union role key(s) "
            "with a populated value, or with one blessed declared-absent spelling carrying "
            "a non-empty payload"
        ),
    ),
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
        manual_hint=(
            "bring AGENTS.md up to the fleet-universal agent-instruction core and register the "
            "beads-access guard hook (.claude/hooks/beads-access-guard.sh) in "
            ".claude/settings.json, in a repo-local commit"
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
)


def rows_for(*, repo_class: str) -> tuple[ObligationRow, ...]:
    """The obligation rows that apply to `repo_class`."""
    return tuple(row for row in OBLIGATION_ROWS if repo_class in row.applies_to)
