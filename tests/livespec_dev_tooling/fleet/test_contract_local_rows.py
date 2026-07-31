"""Tests for `livespec_dev_tooling/fleet/_contract_local_rows.py`.

Covers the LOCAL-vantage first-touch obligation-table invariants the
governed-repo verb relies on: the expected ordered row ids, id
uniqueness, which rows carry a persistent-state drift assert, and that
every row carries a callable reconcile.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from returns.io import IOSuccess

from livespec_dev_tooling.fleet import local_reconcile
from livespec_dev_tooling.fleet._context import RowFinding, RowPass
from livespec_dev_tooling.fleet._contract_local_rows import (
    LOCAL_OBLIGATION_ROWS,
    LocalObligationRow,
)
from livespec_dev_tooling.fleet._local_context import (
    CommandOutcome,
    CommandResult,
    LocalContext,
)
from livespec_dev_tooling.install_worktree_pack import (
    CANONICAL_BRANCH_PROTECTION_BODY,
    CANONICAL_BRANCH_PROTECTION_JUST_BODY,
    CANONICAL_WORKTREE_JUST_BODY,
    CANONICAL_WORKTREE_LIB_BODY,
)

__all__: list[str] = []


_EXPECTED_LOCAL_ROW_IDS = (
    "mise-trust-install",
    "uv-sync",
    "worktree-pack",
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
        "worktree-pack",
        "commit-refuse-hooks",
        "git-notes-refspec",
        "worktree-root-mise-trust",
    }


def test_every_local_row_carries_a_callable_reconcile() -> None:
    assert all(isinstance(row, LocalObligationRow) for row in LOCAL_OBLIGATION_ROWS)
    assert all(callable(row.reconcile_local) for row in LOCAL_OBLIGATION_ROWS)


_PACK_FILES: tuple[tuple[str, str], ...] = (
    ("branch-protection.just", CANONICAL_BRANCH_PROTECTION_JUST_BODY),
    ("branch-protection.sh", CANONICAL_BRANCH_PROTECTION_BODY),
    ("worktree-lib.sh", CANONICAL_WORKTREE_LIB_BODY),
    ("worktree.just", CANONICAL_WORKTREE_JUST_BODY),
)


def _worktree_pack_row() -> LocalObligationRow:
    """The `worktree-pack` row, obtained from the table rather than imported."""
    rows = [row for row in LOCAL_OBLIGATION_ROWS if row.row_id == "worktree-pack"]
    assert rows, "LOCAL_OBLIGATION_ROWS carries no `worktree-pack` row"
    return rows[0]


def _ctx(*, checkout: Path, recorded: list[list[str]], returncode: int = 0) -> LocalContext:
    """A LocalContext whose runner records argv and reports `returncode`."""

    def run(*, args: list[str], cwd: Path | None = None) -> CommandOutcome:
        _ = cwd
        recorded.append(args)
        return IOSuccess(CommandResult(returncode=returncode, stdout="", stderr=""))

    return LocalContext(checkout=checkout, home=checkout / "home", run=run)


def _write_canonical_pack(*, checkout: Path) -> None:
    pack_dir = checkout / "dev-tooling"
    pack_dir.mkdir(parents=True, exist_ok=True)
    for name, body in _PACK_FILES:
        _ = (pack_dir / name).write_text(body, encoding="utf-8")


def test_worktree_pack_row_precedes_commit_refuse_hooks_and_follows_uv_sync() -> None:
    """Order is the design: the pack must materialize BEFORE the hook row asserts.

    `commit-refuse-hooks`' assert shells out to the whole verifier, pack arm
    included, so a pack row placed after it would make that row fail for
    another row's obligation with a reconcile that cannot clear it. `uv-sync`
    must still precede, because the pack reconcile runs under `uv`.
    """
    ids = [row.row_id for row in LOCAL_OBLIGATION_ROWS]
    assert ids.index("uv-sync") < ids.index("worktree-pack") < ids.index("commit-refuse-hooks")


def test_worktree_pack_assert_finds_a_pack_less_checkout(*, tmp_path: Path) -> None:
    row = _worktree_pack_row()
    assert row.assert_local is not None
    outcome = row.assert_local(ctx=_ctx(checkout=tmp_path, recorded=[]))
    assert isinstance(outcome, RowFinding), outcome


def test_worktree_pack_assert_passes_on_a_canonical_pack(*, tmp_path: Path) -> None:
    _write_canonical_pack(checkout=tmp_path)
    row = _worktree_pack_row()
    assert row.assert_local is not None
    outcome = row.assert_local(ctx=_ctx(checkout=tmp_path, recorded=[]))
    assert isinstance(outcome, RowPass), outcome


def test_worktree_pack_assert_reds_on_deletion_drift(*, tmp_path: Path) -> None:
    """Self-heal seam: a canonical pack minus one file is drift, not satisfied."""
    _write_canonical_pack(checkout=tmp_path)
    (tmp_path / "dev-tooling" / "worktree.just").unlink()
    row = _worktree_pack_row()
    assert row.assert_local is not None
    outcome = row.assert_local(ctx=_ctx(checkout=tmp_path, recorded=[]))
    assert isinstance(outcome, RowFinding), outcome


def test_worktree_pack_reconcile_invokes_the_canonical_installer(*, tmp_path: Path) -> None:
    """The reconcile must delegate to the single installer, not reimplement it."""
    recorded: list[list[str]] = []
    row = _worktree_pack_row()
    outcome = row.reconcile_local(ctx=_ctx(checkout=tmp_path, recorded=recorded))
    assert isinstance(outcome, RowPass), outcome
    assert any(
        "livespec_dev_tooling.install_worktree_pack" in arg for args in recorded for arg in args
    ), recorded


def test_worktree_pack_reconcile_reports_a_finding_when_the_installer_fails(
    *, tmp_path: Path
) -> None:
    """A non-zero installer exit is a definitive finding, not a silent pass."""
    outcome = _worktree_pack_row().reconcile_local(
        ctx=_ctx(checkout=tmp_path, recorded=[], returncode=1)
    )
    assert isinstance(outcome, RowFinding), outcome


def test_worktree_pack_reconcile_targets_the_invoked_worktree_not_the_primary(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The pack is PER-WORKTREE: it must materialize where `just` was invoked.

    Every other LOCAL row is primary-scoped — hooks live in the shared
    `.git/hooks`, the notes refspec and mise trust are shared — so the verb
    resolves `ctx.checkout` via `--git-common-dir`, the PRIMARY root. The pack
    is different: it lives in each checkout's own `dev-tooling/`, and the root
    justfile's `import?` lines resolve relative to the worktree you stand in.
    A pack installed only into the primary leaves every linked worktree with no
    `worktree-create` in `just --list` — the exact discoverability hole this
    slice closes. So the reconcile's installer must run with the INVOKED
    worktree as cwd, not the primary.
    """
    primary = tmp_path / "primary"
    invoked = tmp_path / "invoked-worktree"
    primary.mkdir()
    invoked.mkdir()
    recorded: list[tuple[list[str], Path | None]] = []

    def run(*, args: list[str], cwd: Path | None = None) -> CommandOutcome:
        recorded.append((args, cwd))
        if args[:3] == ["git", "rev-parse", "--git-common-dir"]:
            return IOSuccess(CommandResult(returncode=0, stdout=f"{primary}/.git\n", stderr=""))
        if args[:3] == ["git", "rev-parse", "--show-toplevel"]:
            return IOSuccess(CommandResult(returncode=0, stdout=f"{invoked}\n", stderr=""))
        return IOSuccess(CommandResult(returncode=0, stdout="", stderr=""))

    monkeypatch.setattr(local_reconcile, "default_command_runner", run)
    monkeypatch.setattr(sys, "argv", ["local_reconcile", "--checkout", str(invoked)])
    _ = local_reconcile.main()

    installer_cwds = [
        cwd
        for args, cwd in recorded
        if any("livespec_dev_tooling.install_worktree_pack" in arg for arg in args)
    ]
    assert installer_cwds, "the pack installer was never invoked"
    assert (
        installer_cwds[0] == invoked
    ), f"pack installer ran in {installer_cwds[0]}, expected the invoked worktree {invoked}"
