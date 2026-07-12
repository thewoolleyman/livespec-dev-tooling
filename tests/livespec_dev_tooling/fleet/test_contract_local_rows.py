"""Tests for `livespec_dev_tooling/fleet/_contract_local_rows.py`.

Covers the LOCAL-vantage first-touch obligation-table invariants the
governed-repo verb relies on: the expected ordered row ids, id
uniqueness, which rows carry a persistent-state drift assert, and that
every row carries a callable reconcile.
"""

from __future__ import annotations

from livespec_dev_tooling.fleet._contract_local_rows import (
    LOCAL_OBLIGATION_ROWS,
    LocalObligationRow,
)

__all__: list[str] = []


_EXPECTED_LOCAL_ROW_IDS = (
    "mise-trust-install",
    "uv-sync",
    "commit-refuse-hooks",
    "git-notes-refspec",
    "worktree-root-mise-trust",
    "beads-dir-perms",
    "claude-plugins",
    "codex-plugins",
    "livespec-jsonc-complete",
    "beads-bd-binary",
    "beads-dolt-server",
    "beads-tenant-secret",
    "beads-config-committed",
    "beads-metadata-present",
)


def test_local_obligation_rows_have_the_expected_ordered_ids() -> None:
    assert tuple(row.row_id for row in LOCAL_OBLIGATION_ROWS) == _EXPECTED_LOCAL_ROW_IDS


def test_local_obligation_row_ids_are_unique() -> None:
    ids = [row.row_id for row in LOCAL_OBLIGATION_ROWS]
    assert len(set(ids)) == len(ids)


def test_only_persistent_state_rows_carry_a_drift_assert() -> None:
    assert_bearing = {row.row_id for row in LOCAL_OBLIGATION_ROWS if row.assert_local is not None}
    assert assert_bearing == {
        "commit-refuse-hooks",
        "git-notes-refspec",
        "worktree-root-mise-trust",
    }


def test_every_local_row_carries_a_callable_reconcile() -> None:
    assert all(isinstance(row, LocalObligationRow) for row in LOCAL_OBLIGATION_ROWS)
    assert all(callable(row.reconcile_local) for row in LOCAL_OBLIGATION_ROWS)
