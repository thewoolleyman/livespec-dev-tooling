"""Tests for `livespec_dev_tooling/fleet/_rows_local.py`.

Every local first-touch row is exercised across its branches through a
canned-response command runner keyed on the full argument tuple (no real
subprocess, no host mutation): the assert-bearing rows over pass/finding,
the reconcile rows over success and each failure leg, and the beads-perms
row over its present / absent / chmod-failure outcomes.
"""

from __future__ import annotations

from pathlib import Path

from livespec_dev_tooling.fleet._context import RowFinding, RowOutcome, RowPass, RowSkip
from livespec_dev_tooling.fleet._local_context import CommandResult, LocalContext
from livespec_dev_tooling.fleet._rows_local import (
    NOTES_REFSPEC,
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

__all__: list[str] = []


_OK = CommandResult(returncode=0, stdout="", stderr="")


def _ctx(
    *,
    checkout: Path,
    home: Path | None = None,
    table: dict[tuple[str, ...], CommandResult] | None = None,
) -> LocalContext:
    """A `LocalContext` over a canned runner keyed on the full args tuple."""
    lookup = table or {}

    def run(*, args: list[str], cwd: Path | None = None) -> CommandResult:
        del cwd
        return lookup.get(tuple(args), _OK)

    return LocalContext(checkout=checkout, home=home or checkout / "home", run=run)


def test_mise_trust_install_passes_when_both_succeed(*, tmp_path: Path) -> None:
    outcome = reconcile_mise_trust_install(ctx=_ctx(checkout=tmp_path))
    assert isinstance(outcome, RowPass)


def test_mise_trust_failure_is_finding(*, tmp_path: Path) -> None:
    table = {("mise", "trust"): CommandResult(returncode=1, stdout="", stderr="x")}
    outcome = reconcile_mise_trust_install(ctx=_ctx(checkout=tmp_path, table=table))
    assert isinstance(outcome, RowFinding)
    assert "trust" in outcome.message


def test_mise_install_failure_is_finding(*, tmp_path: Path) -> None:
    table = {("mise", "install"): CommandResult(returncode=1, stdout="", stderr="x")}
    outcome = reconcile_mise_trust_install(ctx=_ctx(checkout=tmp_path, table=table))
    assert isinstance(outcome, RowFinding)
    assert "install" in outcome.message


def test_uv_sync_passes_on_success(*, tmp_path: Path) -> None:
    assert isinstance(reconcile_uv_sync(ctx=_ctx(checkout=tmp_path)), RowPass)


def test_uv_sync_failure_is_finding(*, tmp_path: Path) -> None:
    table = {("uv", "sync", "--all-groups"): CommandResult(returncode=1, stdout="", stderr="x")}
    assert isinstance(reconcile_uv_sync(ctx=_ctx(checkout=tmp_path, table=table)), RowFinding)


_HOOK_CHECK = (
    "uv",
    "run",
    "python",
    "-m",
    "livespec_dev_tooling.checks.primary_checkout_commit_refuse_hook_installed",
)
_HOOK_INSTALL = (
    "uv",
    "run",
    "python",
    "-m",
    "livespec_dev_tooling.install_commit_refuse_hooks",
)


def test_assert_hooks_passes_when_verifier_exits_zero(*, tmp_path: Path) -> None:
    assert isinstance(assert_commit_refuse_hooks(ctx=_ctx(checkout=tmp_path)), RowPass)


def test_assert_hooks_finding_when_verifier_fails(*, tmp_path: Path) -> None:
    table = {_HOOK_CHECK: CommandResult(returncode=3, stdout="", stderr="x")}
    assert isinstance(
        assert_commit_refuse_hooks(ctx=_ctx(checkout=tmp_path, table=table)), RowFinding
    )


def test_reconcile_hooks_passes_on_success(*, tmp_path: Path) -> None:
    assert isinstance(reconcile_commit_refuse_hooks(ctx=_ctx(checkout=tmp_path)), RowPass)


def test_reconcile_hooks_failure_is_finding(*, tmp_path: Path) -> None:
    table = {_HOOK_INSTALL: CommandResult(returncode=1, stdout="", stderr="x")}
    assert isinstance(
        reconcile_commit_refuse_hooks(ctx=_ctx(checkout=tmp_path, table=table)), RowFinding
    )


_NOTES_GET = ("git", "config", "--get-all", "remote.origin.fetch")
_NOTES_ADD = ("git", "config", "--add", "remote.origin.fetch", NOTES_REFSPEC)


def test_assert_notes_refspec_present_passes(*, tmp_path: Path) -> None:
    table = {
        _NOTES_GET: CommandResult(
            returncode=0, stdout=f"+refs/heads/*\n{NOTES_REFSPEC}\n", stderr=""
        )
    }
    assert isinstance(assert_git_notes_refspec(ctx=_ctx(checkout=tmp_path, table=table)), RowPass)


def test_assert_notes_refspec_absent_is_finding(*, tmp_path: Path) -> None:
    table = {
        _NOTES_GET: CommandResult(
            returncode=0, stdout="+refs/heads/*:refs/remotes/origin/*\n", stderr=""
        )
    }
    assert isinstance(
        assert_git_notes_refspec(ctx=_ctx(checkout=tmp_path, table=table)), RowFinding
    )


def test_reconcile_notes_refspec_passes_on_success(*, tmp_path: Path) -> None:
    assert isinstance(reconcile_git_notes_refspec(ctx=_ctx(checkout=tmp_path)), RowPass)


def test_reconcile_notes_refspec_failure_is_finding(*, tmp_path: Path) -> None:
    table = {_NOTES_ADD: CommandResult(returncode=1, stdout="", stderr="x")}
    assert isinstance(
        reconcile_git_notes_refspec(ctx=_ctx(checkout=tmp_path, table=table)), RowFinding
    )


_TRUST_GET = ("mise", "settings", "get", "trusted_config_paths")


def test_assert_worktree_trust_present_passes(*, tmp_path: Path) -> None:
    home = tmp_path / "home"
    root = str(home / ".worktrees")
    table = {_TRUST_GET: CommandResult(returncode=0, stdout=f"{root}\n", stderr="")}
    assert isinstance(
        assert_worktree_root_trust(ctx=_ctx(checkout=tmp_path, home=home, table=table)), RowPass
    )


def test_assert_worktree_trust_absent_is_finding(*, tmp_path: Path) -> None:
    table = {_TRUST_GET: CommandResult(returncode=0, stdout="/some/other/path\n", stderr="")}
    assert isinstance(
        assert_worktree_root_trust(ctx=_ctx(checkout=tmp_path, table=table)), RowFinding
    )


def test_reconcile_worktree_trust_passes_when_both_succeed(*, tmp_path: Path) -> None:
    assert isinstance(reconcile_worktree_root_trust(ctx=_ctx(checkout=tmp_path)), RowPass)


def test_reconcile_worktree_trust_mkdir_failure_is_finding(*, tmp_path: Path) -> None:
    home = tmp_path / "home"
    table = {
        ("mkdir", "-p", str(home / ".worktrees")): CommandResult(
            returncode=1, stdout="", stderr="x"
        )
    }
    outcome = reconcile_worktree_root_trust(ctx=_ctx(checkout=tmp_path, home=home, table=table))
    assert isinstance(outcome, RowFinding)
    assert "worktree root" in outcome.message


def test_reconcile_worktree_trust_settings_add_failure_is_finding(*, tmp_path: Path) -> None:
    home = tmp_path / "home"
    root = str(home / ".worktrees")
    table = {
        ("mise", "settings", "add", "trusted_config_paths", root): CommandResult(
            returncode=1, stdout="", stderr="x"
        )
    }
    outcome = reconcile_worktree_root_trust(ctx=_ctx(checkout=tmp_path, home=home, table=table))
    assert isinstance(outcome, RowFinding)
    assert "trusted_config_paths" in outcome.message


def test_beads_perms_skips_when_no_beads_dir(*, tmp_path: Path) -> None:
    outcome = reconcile_beads_dir_perms(ctx=_ctx(checkout=tmp_path))
    assert isinstance(outcome, RowSkip)


def test_beads_perms_passes_when_chmod_succeeds(*, tmp_path: Path) -> None:
    (tmp_path / ".beads").mkdir()
    assert isinstance(reconcile_beads_dir_perms(ctx=_ctx(checkout=tmp_path)), RowPass)


def test_beads_perms_chmod_failure_is_finding(*, tmp_path: Path) -> None:
    (tmp_path / ".beads").mkdir()
    table = {
        ("chmod", "700", str(tmp_path / ".beads")): CommandResult(
            returncode=1, stdout="", stderr="x"
        )
    }
    assert isinstance(
        reconcile_beads_dir_perms(ctx=_ctx(checkout=tmp_path, table=table)), RowFinding
    )


def test_claude_plugins_passes_on_success(*, tmp_path: Path) -> None:
    assert isinstance(reconcile_claude_plugins(ctx=_ctx(checkout=tmp_path)), RowPass)


def test_claude_plugins_failure_is_finding(*, tmp_path: Path) -> None:
    table = {("just", "ensure-plugins"): CommandResult(returncode=1, stdout="", stderr="x")}
    assert isinstance(
        reconcile_claude_plugins(ctx=_ctx(checkout=tmp_path, table=table)), RowFinding
    )


def test_codex_plugins_passes_on_success(*, tmp_path: Path) -> None:
    assert isinstance(reconcile_codex_plugins(ctx=_ctx(checkout=tmp_path)), RowPass)


def test_codex_plugins_failure_is_finding(*, tmp_path: Path) -> None:
    table = {("just", "ensure-codex-plugins"): CommandResult(returncode=1, stdout="", stderr="x")}
    assert isinstance(reconcile_codex_plugins(ctx=_ctx(checkout=tmp_path, table=table)), RowFinding)


def test_outcome_union_members_are_distinct() -> None:
    # Guard that the row helpers return the shared RowOutcome vocabulary.
    outcomes: list[RowOutcome] = [RowPass(), RowFinding(message="m"), RowSkip(reason="r")]
    assert len({type(o).__name__ for o in outcomes}) == 3
