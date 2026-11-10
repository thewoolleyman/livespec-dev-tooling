"""The host probe's locations come from the code and the account database, never the caller."""

from __future__ import annotations

import os
import pwd
from pathlib import Path

import pytest
from returns.io import IOFailure, IOSuccess

from livespec_dev_tooling.fleet._invocation_failure import BINARY_ABSENT, InvocationNotPerformed
from livespec_dev_tooling.fleet._local_context import CommandOutcome, CommandResult, CommandRunner
from livespec_dev_tooling.incident_fleet_host import FLEET_OWNER, production_probe


def _git(*, stdout: str, returncode: int = 0) -> tuple[CommandRunner, list[list[str]]]:
    seen: list[list[str]] = []

    def run(*, args: list[str], cwd: Path | None = None) -> CommandOutcome:
        _ = cwd
        seen.append(args)
        return IOSuccess(CommandResult(returncode=returncode, stdout=stdout, stderr=""))

    return run, seen


def test_the_fleet_owner_is_fixed() -> None:
    assert FLEET_OWNER == "thewoolleyman"


def test_the_clones_root_is_the_parent_of_the_primary_checkout_this_code_belongs_to() -> None:
    run, seen = _git(stdout="/srv/projects/livespec-dev-tooling/.git\n")
    probe = production_probe(run=run)
    assert probe.clones_root == Path("/srv/projects")
    assert seen[0][:3] == ["git", "-C", str(Path(__file__).resolve().parents[2])]
    assert "--git-common-dir" in seen[0]


def test_an_unanswered_git_leaves_no_clones_root_so_no_consumer_can_be_read() -> None:
    def run(*, args: list[str], cwd: Path | None = None) -> CommandOutcome:
        _ = cwd
        return IOFailure(InvocationNotPerformed(argv=tuple(args), kind=BINARY_ABSENT, detail="x"))

    assert production_probe(run=run).clones_root is None
    failed, _ = _git(stdout="", returncode=128)
    assert production_probe(run=failed).clones_root is None
    odd, _ = _git(stdout="/srv/projects/livespec-dev-tooling/worktree\n")
    assert production_probe(run=odd).clones_root is None


def test_home_comes_from_the_account_database_not_the_home_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", "/attacker/chosen")
    run, _ = _git(stdout="/srv/projects/livespec-dev-tooling/.git\n")
    probe = production_probe(run=run)
    assert probe.home == Path(pwd.getpwuid(os.getuid()).pw_dir)
    assert probe.proc_root == Path("/proc")
