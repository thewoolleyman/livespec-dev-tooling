"""The github-state slice of the central (GitHub-vantage) obligation table.

Extracted VERBATIM from `_contract_rows.py` (livespec-dev-tooling-oitd):
that module sat 4 LLOC under this repo's 250-LLOC hard ceiling, so
`OBLIGATION_ROWS` — the single table every fleet lane reads — had become
structurally closed to extension, and an obligation that cannot be
registered is a check that does not run.

These are the rows whose subject is REPO STATE ON GITHUB (secret names,
App installation, branch protection, merge settings, the
delete-branch-on-merge toggle, the `livespec-sibling` topic) rather than a
committed file — the same partition `obligation_type="github-state"`
already names, and the one group whose reconcile side is machine-applicable
from the central vantage. `_contract_rows.py` splices `GITHUB_STATE_ROWS`
into `OBLIGATION_ROWS` at the position these rows already occupied, so the
exported table's content AND ordering are unchanged by the move.

The row FUNCTIONS these entries reference live in `_rows_github.py`
(asserts) and `_reconcile.py` (reconciles); this module holds only their
TABLE REGISTRATION.
"""

from __future__ import annotations

from livespec_dev_tooling.fleet._contract_classes import ALL_CLASSES
from livespec_dev_tooling.fleet._contract_model import (
    ADMIN_VANTAGE,
    CENTRAL_APP_VANTAGE,
    CENTRAL_VANTAGE,
    ObligationRow,
    RowFn,
)
from livespec_dev_tooling.fleet._reconcile import (
    reconcile_branch_protection,
    reconcile_delete_branch_on_merge,
    reconcile_merge_settings,
    reconcile_secret_names,
    reconcile_topic,
)
from livespec_dev_tooling.fleet._rows_github import (
    assert_app_installation,
    assert_branch_protection,
    assert_delete_branch_on_merge,
    assert_merge_settings,
    assert_secret_names,
    assert_topic,
)

__all__: list[str] = [
    "GITHUB_STATE_ROWS",
]


def _github_state_row(
    *,
    row_id: str,
    assert_member: RowFn,
    reconcile: RowFn | None = None,
    manual_hint: str = "",
    vantage: str = CENTRAL_VANTAGE,
) -> ObligationRow:
    return ObligationRow(
        row_id=row_id,
        obligation_type="github-state",
        applies_to=ALL_CLASSES,
        assert_member=assert_member,
        reconcile=reconcile,
        manual_hint=manual_hint,
        vantage=vantage,
    )


GITHUB_STATE_ROWS: tuple[ObligationRow, ...] = (
    _github_state_row(
        row_id="secret-names",
        assert_member=assert_secret_names,
        reconcile=reconcile_secret_names,
        vantage=ADMIN_VANTAGE,
    ),
    _github_state_row(
        row_id="app-installation",
        assert_member=assert_app_installation,
        manual_hint="install the fleet GitHub App on the repo (owner settings → GitHub Apps)",
        vantage=CENTRAL_APP_VANTAGE,
    ),
    _github_state_row(
        row_id="branch-protection",
        assert_member=assert_branch_protection,
        reconcile=reconcile_branch_protection,
        vantage=ADMIN_VANTAGE,
    ),
    _github_state_row(
        row_id="merge-settings",
        assert_member=assert_merge_settings,
        reconcile=reconcile_merge_settings,
    ),
    _github_state_row(
        row_id="delete-branch-on-merge",
        assert_member=assert_delete_branch_on_merge,
        reconcile=reconcile_delete_branch_on_merge,
    ),
    _github_state_row(
        row_id="topic-livespec-sibling",
        assert_member=assert_topic,
        reconcile=reconcile_topic,
    ),
)
