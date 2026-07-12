"""The LOCAL-vantage first-touch obligation table for the fleet contract.

These rows run from the LOCAL vantage only (per
`livespec/SPECIFICATION/non-functional-requirements.md` §"Governed-repo
lifecycle"): the governed-repo verb walks `LOCAL_OBLIGATION_ROWS`
reconciling each checkout-local prerequisite (toolchain install,
dependency sync, hook installation, plugin registration, beads-runtime
detect-and-guide). The central (GitHub-vantage) table lives in
`_contract_rows.py`; no row needs both vantages.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from livespec_dev_tooling.fleet._context import RowOutcome
from livespec_dev_tooling.fleet._local_context import LocalContext
from livespec_dev_tooling.fleet._rows_local import (
    assert_commit_refuse_hooks,
    assert_git_notes_refspec,
    assert_worktree_root_trust,
    reconcile_beads_dir_perms,
    reconcile_claude_plugins,
    reconcile_codex_plugins,
    reconcile_commit_refuse_hooks,
    reconcile_git_notes_refspec,
    reconcile_mise_trust_install,
    reconcile_uv_sync,
    reconcile_worktree_root_trust,
)
from livespec_dev_tooling.fleet._rows_local_beads import (
    reconcile_beads_bd_binary,
    reconcile_beads_config_committed,
    reconcile_beads_dolt_server,
    reconcile_beads_metadata_present,
    reconcile_beads_tenant_secret,
)
from livespec_dev_tooling.fleet._rows_local_jsonc import reconcile_livespec_jsonc_complete

__all__: list[str] = [
    "LOCAL_OBLIGATION_ROWS",
    "LocalObligationRow",
]


class LocalRowFn(Protocol):
    """One LOCAL-vantage obligation-row operation (assert or reconcile) over a checkout."""

    def __call__(self, *, ctx: LocalContext) -> RowOutcome: ...


@dataclass(frozen=True, kw_only=True)
class LocalObligationRow:
    """One LOCAL-vantage first-touch obligation: a reconcile + an optional drift assert.

    `assert_local` is None for pure provisioning rows (toolchain install,
    dependency sync, plugin registration, beads-dir hardening) that carry
    no persistent committed state a drift sweep can re-check; the verb
    runs their idempotent `reconcile_local` unconditionally. A row that
    leaves persistent state (the commit-refuse hooks, the notes refspec,
    the worktree-root mise-trust entry) carries a real `assert_local`, so
    the assert/drift side gains the matching local check for free and the
    verb reconciles only an unmet row.

    These rows run from the LOCAL vantage only (per
    `livespec/SPECIFICATION/non-functional-requirements.md`
    §"Governed-repo lifecycle"); the central rows (`OBLIGATION_ROWS`) run
    against the manifest from the GitHub vantage, and no row needs both.
    """

    row_id: str
    assert_local: LocalRowFn | None
    reconcile_local: LocalRowFn


LOCAL_OBLIGATION_ROWS: tuple[LocalObligationRow, ...] = (
    LocalObligationRow(
        row_id="mise-trust-install",
        assert_local=None,
        reconcile_local=reconcile_mise_trust_install,
    ),
    LocalObligationRow(
        row_id="uv-sync",
        assert_local=None,
        reconcile_local=reconcile_uv_sync,
    ),
    LocalObligationRow(
        row_id="commit-refuse-hooks",
        assert_local=assert_commit_refuse_hooks,
        reconcile_local=reconcile_commit_refuse_hooks,
    ),
    LocalObligationRow(
        row_id="git-notes-refspec",
        assert_local=assert_git_notes_refspec,
        reconcile_local=reconcile_git_notes_refspec,
    ),
    LocalObligationRow(
        row_id="worktree-root-mise-trust",
        assert_local=assert_worktree_root_trust,
        reconcile_local=reconcile_worktree_root_trust,
    ),
    LocalObligationRow(
        row_id="beads-dir-perms",
        assert_local=None,
        reconcile_local=reconcile_beads_dir_perms,
    ),
    LocalObligationRow(
        row_id="claude-plugins",
        assert_local=None,
        reconcile_local=reconcile_claude_plugins,
    ),
    LocalObligationRow(
        row_id="codex-plugins",
        assert_local=None,
        reconcile_local=reconcile_codex_plugins,
    ),
    # Config-completeness row (livespec-zs22.8 M6): GUARANTEES a harnesses-bearing
    # .livespec.jsonc and MACHINE-FILLS the beads `connection` block from
    # .beads/config.yaml. It carries no `assert_local` — its reconcile both detects
    # (an absent / unparseable / harnesses-less config, or an existing connection's
    # drift → a warning the operator resolves by hand, the `harnesses` statuses being
    # a human-judgment seam never fabricated) and machine-fixes (the non-secret
    # connection block; the tenant password stays the beads-tenant-secret row).
    LocalObligationRow(
        row_id="livespec-jsonc-complete",
        assert_local=None,
        reconcile_local=reconcile_livespec_jsonc_complete,
    ),
    # Beads-runtime detect-and-guide rows (livespec-zs22.8 M4): each PROBES one
    # ledger-backend prerequisite and, when unmet, emits a WARNING-severity guided
    # TODO the verb surfaces rather than fails on. All are gated on a `.beads/`
    # directory (a non-beads repo skips). They carry no `assert_local` — the probe
    # IS the reconcile (it cannot machine-fix a host/secret/runtime seam).
    LocalObligationRow(
        row_id="beads-bd-binary",
        assert_local=None,
        reconcile_local=reconcile_beads_bd_binary,
    ),
    LocalObligationRow(
        row_id="beads-dolt-server",
        assert_local=None,
        reconcile_local=reconcile_beads_dolt_server,
    ),
    LocalObligationRow(
        row_id="beads-tenant-secret",
        assert_local=None,
        reconcile_local=reconcile_beads_tenant_secret,
    ),
    LocalObligationRow(
        row_id="beads-config-committed",
        assert_local=None,
        reconcile_local=reconcile_beads_config_committed,
    ),
    LocalObligationRow(
        row_id="beads-metadata-present",
        assert_local=None,
        reconcile_local=reconcile_beads_metadata_present,
    ),
)
