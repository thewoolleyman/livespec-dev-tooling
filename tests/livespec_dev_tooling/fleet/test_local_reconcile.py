"""Tests for `livespec_dev_tooling/fleet/local_reconcile.py`.

The reconcile engine runs in-process against a canned-response
`LocalContext` (assert-then-reconcile over the LOCAL obligation
partition, with the beads-perms skip exercised); the checkout-root
resolver is covered across its not-a-checkout / absolute / relative
legs; the CLI entry point is exercised over its precondition /
unresolved / success branches. The `__main__` guard is coverage-excluded
(pyproject `exclude_also`), so it needs no subprocess invocation.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

from livespec_dev_tooling.fleet import local_reconcile
from livespec_dev_tooling.fleet._local_context import CommandResult, LocalContext
from livespec_dev_tooling.fleet.local_reconcile import _resolve_checkout_root, reconcile_checkout

if TYPE_CHECKING:
    import pytest
    import structlog.stdlib

__all__: list[str] = []


def _log() -> structlog.stdlib.BoundLogger:
    import structlog

    return structlog.get_logger("test_local_reconcile")


def _runner(*, table: dict[tuple[str, ...], CommandResult] | None = None):
    lookup = table or {}
    default = CommandResult(returncode=0, stdout="", stderr="")

    def run(*, args: list[str], cwd: Path | None = None) -> CommandResult:
        del cwd
        return lookup.get(tuple(args), default)

    return run


def test_reconcile_checkout_all_rows_resolve(*, tmp_path: Path) -> None:
    # Every command succeeds, stdout empty (drift asserts for notes /
    # worktree fail → their reconcile runs and passes); the commit-refuse
    # verifier exits 0 (assert passes → reconcile skipped); no .beads
    # tenant → that row skips.
    ctx = LocalContext(checkout=tmp_path, home=tmp_path / "home", run=_runner())
    assert reconcile_checkout(ctx=ctx, log=_log()) == 0


def test_reconcile_checkout_counts_failed_rows(*, tmp_path: Path) -> None:
    table = {("uv", "sync", "--all-groups"): CommandResult(returncode=1, stdout="", stderr="x")}
    ctx = LocalContext(checkout=tmp_path, home=tmp_path / "home", run=_runner(table=table))
    assert reconcile_checkout(ctx=ctx, log=_log()) == 1


def test_resolve_root_returns_none_when_not_a_checkout(*, tmp_path: Path) -> None:
    table = {
        ("git", "rev-parse", "--git-common-dir"): CommandResult(
            returncode=128, stdout="", stderr="x"
        )
    }
    assert _resolve_checkout_root(target=tmp_path, run=_runner(table=table)) is None


def test_resolve_root_uses_absolute_common_dir(*, tmp_path: Path) -> None:
    common = tmp_path / "primary" / ".git"
    table = {
        ("git", "rev-parse", "--git-common-dir"): CommandResult(
            returncode=0, stdout=f"{common}\n", stderr=""
        )
    }
    assert _resolve_checkout_root(target=tmp_path, run=_runner(table=table)) == common.parent


def test_resolve_root_resolves_relative_common_dir(*, tmp_path: Path) -> None:
    table = {
        ("git", "rev-parse", "--git-common-dir"): CommandResult(
            returncode=0, stdout=".git\n", stderr=""
        )
    }
    assert _resolve_checkout_root(target=tmp_path, run=_runner(table=table)) == tmp_path.resolve()


def test_main_precondition_failure_when_not_a_checkout(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "argv", ["local-reconcile", "--checkout", str(tmp_path)])
    table = {
        ("git", "rev-parse", "--git-common-dir"): CommandResult(
            returncode=128, stdout="", stderr="x"
        )
    }
    monkeypatch.setattr(local_reconcile, "default_command_runner", _runner(table=table))
    assert local_reconcile.main() == 1


def test_main_success_exits_zero(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["local-reconcile", "--checkout", str(tmp_path)])
    table = {
        ("git", "rev-parse", "--git-common-dir"): CommandResult(
            returncode=0, stdout=".git\n", stderr=""
        )
    }
    monkeypatch.setattr(local_reconcile, "default_command_runner", _runner(table=table))
    assert local_reconcile.main() == 0


def test_main_unresolved_rows_exit_four(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["local-reconcile", "--checkout", str(tmp_path)])
    table = {
        ("git", "rev-parse", "--git-common-dir"): CommandResult(
            returncode=0, stdout=".git\n", stderr=""
        ),
        ("uv", "sync", "--all-groups"): CommandResult(returncode=1, stdout="", stderr="x"),
    }
    monkeypatch.setattr(local_reconcile, "default_command_runner", _runner(table=table))
    assert local_reconcile.main() == 4


def test_main_defaults_checkout_to_cwd(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["local-reconcile"])
    monkeypatch.chdir(tmp_path)
    table = {
        ("git", "rev-parse", "--git-common-dir"): CommandResult(
            returncode=0, stdout=".git\n", stderr=""
        )
    }
    monkeypatch.setattr(local_reconcile, "default_command_runner", _runner(table=table))
    assert local_reconcile.main() == 0
