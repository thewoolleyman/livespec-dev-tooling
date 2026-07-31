"""The local command seam's failure track — `livespec-dev-tooling-8o8e` row 33.

`default_command_runner` used to answer "the invocation never happened"
with a FABRICATED `CommandResult(returncode=127)`, a success-shaped
record indistinguishable from a program that genuinely exited 127. It
also let `subprocess.run` raise straight through the seam, killing the
whole local reconcile partway through a row rather than failing that row.
Both are failure-track VALUES now.

The success track is unchanged in meaning: a command that RAN carries its
exit code as DATA, whatever that code is. `test_a_command_that_ran_...`
pins that asymmetry, because collapsing it the other way — reading every
non-zero exit as a failure — is the tightening error this thread has
already committed once.

THE TWO ROW TESTS ARE THE POINT OF THE CONVERSION, not decoration. The
fabricated 127 did not stay inside the seam: it reached rows that read it
as an ANSWER, and two of them laundered "the program is not installed"
into a confident, wrong verdict about the member —

- `reconcile_claude_plugins` asked `just --show ensure-plugins`, read the
  127 as "no such recipe", and SKIPPED with "member declares no Claude
  plugin surface". An absent `just` reported as a deliberate declaration
  by the member is a fabricated CLEAN result, which is this epic's own
  subject arriving in its own remediation.
- `assert_git_notes_refspec` read the 127's empty stdout and reported the
  refspec ABSENT from a file it never managed to read.
"""

from __future__ import annotations

import shutil
import subprocess
from typing import TYPE_CHECKING

import pytest
from returns.io import IOFailure, IOResult, IOSuccess
from returns.unsafe import unsafe_perform_io

from livespec_dev_tooling.fleet._context import RowFinding
from livespec_dev_tooling.fleet._invocation_failure import (
    BINARY_ABSENT,
    SPAWN_FAILED,
    InvocationNotPerformed,
)
from livespec_dev_tooling.fleet._local_context import (
    CommandResult,
    LocalContext,
    default_command_runner,
)
from livespec_dev_tooling.fleet._rows_local import (
    assert_git_notes_refspec,
    reconcile_claude_plugins,
)

if TYPE_CHECKING:
    from pathlib import Path

__all__: list[str] = []


def _absent_program(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every program unresolvable REGARDLESS of the host's real PATH.

    Patching `shutil.which` rather than prepending a shim directory: a
    shim only works if it is the WHOLE PATH, and a fixture a real binary
    later on PATH can defeat is a fixture that cannot fail.
    """

    def fake_which(_name: str) -> str | None:
        return None

    monkeypatch.setattr(shutil, "which", fake_which)


def test_absent_program_is_a_failure_value_not_a_fabricated_127(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A missing binary lands on the FAILURE track, carrying argv."""
    _absent_program(monkeypatch)
    result = default_command_runner(args=["mise", "trust"])
    assert isinstance(result, IOFailure)
    failure = unsafe_perform_io(result.failure())
    assert isinstance(failure, InvocationNotPerformed)
    assert failure.kind == BINARY_ABSENT
    assert failure.argv == ("mise", "trust")


def test_a_command_that_ran_and_exited_nonzero_is_a_success_carrying_its_code(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An invocation that COMPLETED and ANSWERED is a success whatever it answered."""

    def fake_which(_name: str) -> str | None:
        return "/usr/bin/mise"

    def fake_run(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=cmd, returncode=4, stdout="out", stderr="nope\n")

    monkeypatch.setattr(shutil, "which", fake_which)
    monkeypatch.setattr(subprocess, "run", fake_run)
    result = default_command_runner(args=["mise", "trust"])
    assert isinstance(result, IOSuccess)
    assert unsafe_perform_io(result.unwrap()) == CommandResult(
        returncode=4, stdout="out", stderr="nope\n"
    )


def test_an_unspawnable_program_is_a_failure_value_rather_than_a_raise(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`subprocess.run` raising used to abort the whole local reconcile."""

    def fake_which(_name: str) -> str | None:
        return "/usr/bin/mise"

    def fake_run(_cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(shutil, "which", fake_which)
    monkeypatch.setattr(subprocess, "run", fake_run)
    result = default_command_runner(args=["mise", "trust"])
    assert isinstance(result, IOFailure)
    failure = unsafe_perform_io(result.failure())
    assert failure.kind == SPAWN_FAILED
    assert "Permission denied" in failure.detail


def _ctx_where_nothing_runs(*, checkout: Path) -> LocalContext:
    """A context whose runner reports EVERY invocation as never performed.

    Unconditional on purpose. An earlier spelling took a `program` name and
    fell through to a canned success for anything else — an arm neither row
    below can reach, since each fails on its FIRST command. A fixture branch
    no test executes is the fixture-shaped version of the dead code this
    epic exists to remove, so the fixture states one condition and states it
    for everything.
    """

    def run(
        *, args: list[str], cwd: Path | None = None
    ) -> IOResult[CommandResult, InvocationNotPerformed]:
        del cwd
        return IOFailure(
            InvocationNotPerformed(
                argv=tuple(args), kind=BINARY_ABSENT, detail=f"{args[0]} not on PATH"
            )
        )

    return LocalContext(checkout=checkout, home=checkout / "home", run=run)


def test_an_uninvokable_just_is_a_finding_not_a_declared_absence_of_plugins(
    *, tmp_path: Path
) -> None:
    """An absent `just` must not read as "the member declares no plugin surface".

    The skip is reserved for a `just` that RAN and reported no such
    recipe — a real statement about the member. A `just` that never ran
    makes no statement about the member at all.
    """
    outcome = reconcile_claude_plugins(ctx=_ctx_where_nothing_runs(checkout=tmp_path))
    assert isinstance(outcome, RowFinding)
    assert "just" in outcome.message


def test_an_uninvokable_git_is_a_finding_not_an_absent_notes_refspec(*, tmp_path: Path) -> None:
    """Empty stdout from a command that never ran is not evidence of absence."""
    outcome = assert_git_notes_refspec(ctx=_ctx_where_nothing_runs(checkout=tmp_path))
    assert isinstance(outcome, RowFinding)
    assert "git" in outcome.message
