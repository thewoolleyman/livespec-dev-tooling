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
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

# `returns` is VENDORED, not installed, so a bare import resolves only if
# some EARLIER import in the same process already put `_vendor/` on
# `sys.path`. Relying on that ordering is what broke the fleet's release
# fan-out for seven hours (`vzwa`'s `89296e0`); this module is imported
# by `local_reconcile`, a `python -m` entry point where nothing runs first.
_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.io import IOFailure, IOResult, IOSuccess  # noqa: E402  — vendor-path-aware import.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware import.

from livespec_dev_tooling.fleet._invocation_failure import (  # noqa: E402
    BINARY_ABSENT,
    SPAWN_FAILED,
    InvocationNotPerformed,
)

__all__: list[str] = [
    "CommandOutcome",
    "CommandResult",
    "CommandRunner",
    "LocalContext",
    "command_answer",
    "default_command_runner",
]


@dataclass(frozen=True, kw_only=True)
class CommandResult:
    """Answer of one local command invocation that RAN (exit code + streams)."""

    returncode: int
    stdout: str
    stderr: str


# The railway alias for this seam. It reads inverted against `_snapshot`'s
# `DownloadResult = IOResult[DownloadOutcome, ...]` because the value type
# here was already named `CommandResult` before the conversion; renaming it
# would churn thirty-odd canned fakes across the suite to buy nothing.
CommandOutcome = IOResult[CommandResult, InvocationNotPerformed]


class CommandRunner(Protocol):
    """Callable seam for host command invocations; `args` includes the program.

    The failure track carries ONLY "the invocation did not happen". A
    program that RAN is a success carrying its exit code as data, however
    that code reads — the seam does not adjudicate what the program said.
    """

    def __call__(self, *, args: list[str], cwd: Path | None = None) -> CommandOutcome: ...


def default_command_runner(*, args: list[str], cwd: Path | None = None) -> CommandOutcome:
    """Run `args` as a subprocess; a program that never ran FAILS.

    This used to answer an absent program with
    `CommandResult(returncode=127)` — a fabricated code a real program can
    also return, so "never ran" and "ran and exited 127" were the same
    value, and rows downstream read the sentinel as an ANSWER. It is a
    failure-track value now, and a completed invocation is a success
    whatever its exit code.
    """
    argv = tuple(args)
    if shutil.which(args[0]) is None:
        return IOFailure(
            InvocationNotPerformed(argv=argv, kind=BINARY_ABSENT, detail=f"{args[0]} not on PATH")
        )
    try:
        completed = subprocess.run(
            args,
            capture_output=True,
            text=True,
            check=False,
            cwd=None if cwd is None else str(cwd),
        )
    except OSError as unspawnable:
        # Previously UNCAUGHT, so it propagated out of the seam and aborted
        # the whole local reconcile partway through a row rather than
        # failing that row.
        return IOFailure(
            InvocationNotPerformed(argv=argv, kind=SPAWN_FAILED, detail=str(unspawnable))
        )
    return IOSuccess(
        CommandResult(
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
    )


def command_answer(*, outcome: CommandOutcome) -> CommandResult | InvocationNotPerformed:
    """The answer of a command that RAN, or the record of one that did not.

    Every consumer of this seam needs exactly this split and none needs it
    differently, so it lives here once rather than as nineteen inline
    `isinstance` + `unsafe_perform_io` pairs — which would be the same
    duplication shape one layer up. `fleet/_pin_walk_failure.py` is the
    precedent for extracting the shared rendering of a failure track.

    It deliberately returns THIS seam's vocabulary rather than `RowOutcome`:
    the obligation-table types live in `_context`, and importing them here
    would make the subprocess seam depend on the layer that sits on top of
    it. Each row maps `InvocationNotPerformed` to its own `RowFinding`.
    """
    if isinstance(outcome, IOFailure):
        return unsafe_perform_io(outcome.failure())
    return unsafe_perform_io(outcome.unwrap())


@dataclass(frozen=True, kw_only=True)
class LocalContext:
    """Target checkout + operator HOME + the host-command seam local rows use."""

    checkout: Path
    home: Path
    run: CommandRunner
    worktree: Path | None = None

    @property
    def invoked_worktree(self) -> Path:
        """The worktree the verb was invoked from; falls back to `checkout`.

        `checkout` is the PRIMARY root (resolved via `--git-common-dir`), which
        is right for shared obligations: hooks in `.git/hooks`, the notes
        refspec, mise trust. A row whose artifact is PER-WORKTREE — the
        worktree-discipline pack, whose `import?` lines resolve relative to the
        checkout you stand in — must use this instead. Optional, defaulting to
        `checkout`, so every existing row and caller is unaffected.
        """
        return self.worktree if self.worktree is not None else self.checkout

    def exec(self, *, args: list[str]) -> CommandOutcome:
        """Run a command with the target checkout as the working directory."""
        return self.run(args=args, cwd=self.checkout)

    def exec_in_worktree(self, *, args: list[str]) -> CommandOutcome:
        """Run a command with the INVOKED worktree as the working directory."""
        return self.run(args=args, cwd=self.invoked_worktree)
