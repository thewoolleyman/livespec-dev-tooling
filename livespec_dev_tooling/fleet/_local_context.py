"""Shared types + subprocess seam for the LOCAL-vantage first-touch reconcile.

The local counterpart to `_context.py`'s GitHub-vantage `FleetContext`:
where central obligation rows reach a member over the `gh` API, the local
first-touch rows run host commands IN a target checkout (toolchain
install, dependency sync, hook install, git config, plugin registration).
`LocalContext` carries the target checkout path, the operator HOME, and
the SINGLE subprocess seam (`CommandRunner`) every local row issues
commands through — so the local obligation rows stay hermetically testable
with a canned-response runner, exactly as the central rows test against a
canned `gh` runner. Local row functions receive a `LocalContext` and
return the SAME `RowOutcome` values (`RowPass`/`RowFinding`/`RowSkip` from
`_context`) the central rows use, reusing one outcome vocabulary across
both vantages rather than forking a parallel one.

Per `livespec/SPECIFICATION/non-functional-requirements.md`
§"Governed-repo lifecycle": a reconcile row runs from exactly one
vantage and no row needs both. These rows are the LOCAL vantage; the
central rows (secrets, branch protection, topic, shim PRs) stay in
`wire_fleet_member`.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

__all__: list[str] = [
    "CommandResult",
    "CommandRunner",
    "LocalContext",
    "default_command_runner",
]


@dataclass(frozen=True, kw_only=True)
class CommandResult:
    """Outcome of one local command invocation (exit code + captured streams)."""

    returncode: int
    stdout: str
    stderr: str


class CommandRunner(Protocol):
    """Callable seam for host command invocations; `args` includes the program."""

    def __call__(self, *, args: list[str], cwd: Path | None = None) -> CommandResult: ...


def default_command_runner(*, args: list[str], cwd: Path | None = None) -> CommandResult:
    """Run `args` as a subprocess; a missing program yields a synthetic failure result.

    Mirrors `_context.default_gh_runner`: a program absent from PATH
    returns a synthetic exit-127 result rather than raising, so a row
    that probes an optional tool degrades to a definitive finding rather
    than crashing the verb.
    """
    if shutil.which(args[0]) is None:
        return CommandResult(returncode=127, stdout="", stderr=f"{args[0]} not on PATH")
    completed = subprocess.run(
        args,
        capture_output=True,
        text=True,
        check=False,
        cwd=None if cwd is None else str(cwd),
    )
    return CommandResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


@dataclass(frozen=True, kw_only=True)
class LocalContext:
    """Target checkout + operator HOME + the host-command seam local rows use."""

    checkout: Path
    home: Path
    run: CommandRunner

    def exec(self, *, args: list[str]) -> CommandResult:
        """Run a command with the target checkout as the working directory."""
        return self.run(args=args, cwd=self.checkout)
