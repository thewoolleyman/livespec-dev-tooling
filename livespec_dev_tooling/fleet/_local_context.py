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
from typing import TYPE_CHECKING, Protocol

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

if TYPE_CHECKING:
    from collections.abc import Callable

from livespec_dev_tooling.fleet._invocation_failure import (  # noqa: E402
    BINARY_ABSENT,
    SPAWN_FAILED,
    InvocationNotPerformed,
)

__all__: list[str] = [
    "FILE_UNDECODABLE",
    "FILE_UNREADABLE",
    "CommandOutcome",
    "CommandResult",
    "CommandRunner",
    "FileNotRead",
    "FileTextOutcome",
    "LocalContext",
    "PathKindOutcome",
    "command_answer",
    "default_command_runner",
]

# The two ways a local file read fails, kept APART because they call for
# different operator responses: undecodable is corrupt CONTENT, unreadable
# is a PATH or permissions problem. One fused kind would put two meanings
# in one variant, which the rendering-boundary clause's condition 3
# refuses. Spelled as `InvocationNotPerformed.kind` is, rather than
# inventing a second convention.
FILE_UNREADABLE = "file_unreadable"
FILE_UNDECODABLE = "file_undecodable"


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


@dataclass(frozen=True, kw_only=True)
class FileNotRead:
    """A local file that could not be READ — never one that is merely absent.

    Absence is an ANSWER and travels the SUCCESS track as `None`; this type
    carries only "the read did not produce text". Fusing the two is the
    defect this seam exists to remove: an `is_file()`-then-`read_text()`
    pre-check pair renders absent and unreadable identically while ALSO
    leaving the read's own failure uncaught.

    `path` is carried for the same reason `InvocationNotPerformed` carries
    `argv` — "a file could not be read" names no file, and every consumer
    of this track renders a reason a human has to act on.
    """

    path: Path
    kind: str
    detail: str


FileTextOutcome = IOResult[str | None, FileNotRead]
PathKindOutcome = IOResult[bool, FileNotRead]


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

    def file_text(self, *, path: Path) -> FileTextOutcome:
        """Read `path` as UTF-8: ABSENT is an ANSWER, UNREADABLE is a FAILURE.

        The local counterpart of `FleetContext.file_text`, and the seam
        whose absence made every local row that wanted a file call
        `Path.read_text()` directly — a side-effecting primitive called
        DIRECTLY rather than through an injected seam, which is what
        livespec's rendering-boundary condition 1 refuses.

        ⛔ NAMED `file_text` FOR A MECHANICAL REASON, NOT A STYLISTIC ONE.
        A caller reaches this through `ctx`, a PARAMETER, so the receiver
        resolves to nothing and `_no_expected_failure_mode` has only the
        VERB left to judge — and `read_text` is IN
        `_UNRESOLVED_RECEIVER_IO_VERBS`. A seam named after the primitive
        it wraps would leave every caller convicted exactly as before,
        so the fix would LOOK done while changing nothing. Any name
        outside that set works; matching `FleetContext` is what makes
        this a restoration rather than an invention.

        ⚠️ IT DELIBERATELY DOES NOT MIRROR `FleetContext.file_text`'s
        `str | None` SIGNATURE. That shape fuses absent with unreadable,
        which is why the central side needs `_absent_or_unreadable` to
        take a SECOND read of the member tree to disambiguate. Here the
        two are split at the source and no second read is needed.

        ONE `try` RATHER THAN AN `is_file()` PRE-CHECK PAIR: the pair
        fuses absent with unreadable, leaves a TOCTOU second arm no test
        can reach, AND leaves the read's own failure uncaught. The order
        of the arms is load-bearing — `FileNotFoundError` is an `OSError`
        so it must precede the general arm, and `UnicodeDecodeError` is a
        `ValueError` that the general `OSError` arm CANNOT catch. Both
        crashes this seam fixes were in those two different hierarchies.
        """
        try:
            return IOSuccess(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return IOSuccess(None)
        except UnicodeDecodeError as undecodable:
            return IOFailure(FileNotRead(path=path, kind=FILE_UNDECODABLE, detail=str(undecodable)))
        except OSError as unreadable:
            return IOFailure(FileNotRead(path=path, kind=FILE_UNREADABLE, detail=str(unreadable)))

    def dir_present(self, *, path: Path) -> PathKindOutcome:
        """Is `path` a directory? ABSENT is an ANSWER, UNSTATTABLE is a FAILURE.

        The PREDICATE counterpart of `file_text`, and the seam whose absence
        made every local row that wanted to probe a path call `Path.is_dir()` /
        `Path.is_file()` directly — a side-effecting primitive called DIRECTLY
        rather than through an injected seam, which is what livespec's
        rendering-boundary condition 1 refuses.

        ⛔ IT IS NOT A CONVENIENCE WRAPPER: THE PRIMITIVE RAISES. `pathlib`
        ignores only `(ENOENT, ENOTDIR, EBADF, ELOOP)`, so `EACCES` propagates
        and an unreadable parent takes an UNCAUGHT `PermissionError` straight
        out of the row and aborts the whole reconcile. That is the `a6et` shape
        again, and this fleet manufactures the condition itself:
        `reconcile_beads_dir_perms` chmods `.beads` to `700`, so a process
        running as a non-owner then raises on everything inside it.

        ⛔ NAMED `dir_present` FOR A MECHANICAL REASON, NOT A STYLISTIC ONE.
        A caller reaches this through `ctx`, a PARAMETER, so the receiver
        resolves to nothing and `_no_expected_failure_mode` has only the VERB
        left to judge — and `is_dir`, `is_file` and `exists` are ALL in
        `_UNRESOLVED_RECEIVER_IO_VERBS`. A seam named after the primitive it
        wraps would leave every caller convicted exactly as before, so the fix
        would LOOK done while changing nothing. Pinned by
        `test_the_seam_names_are_outside_the_unresolved_receiver_verb_set`.

        ONE `try` AROUND THE PRIMITIVE, and the arm is `OSError` alone: unlike
        the read seam there is no `UnicodeDecodeError` sibling here, because
        nothing is decoded. `ENOTDIR` and `ENOENT` never reach the arm — the
        primitive answers `False` for both — which is why absence stays an
        ANSWER without this seam having to classify it.
        """
        return self._stat_answer(path=path, is_kind=path.is_dir)

    def file_present(self, *, path: Path) -> PathKindOutcome:
        """Is `path` a regular file? Same three-way split as `dir_present`."""
        return self._stat_answer(path=path, is_kind=path.is_file)

    @staticmethod
    def _stat_answer(*, path: Path, is_kind: Callable[[], bool]) -> PathKindOutcome:
        """Lift one `pathlib` predicate onto the railway, shared by both seams.

        Shared rather than duplicated because the two differ ONLY in which
        primitive they ask; duplicating the `try` is how one of them would later
        acquire a second `except` arm the other lacks.
        """
        try:
            return IOSuccess(is_kind())
        except OSError as unstattable:
            return IOFailure(FileNotRead(path=path, kind=FILE_UNREADABLE, detail=str(unstattable)))

    def exec(self, *, args: list[str]) -> CommandOutcome:
        """Run a command with the target checkout as the working directory."""
        return self.run(args=args, cwd=self.checkout)

    def exec_in_worktree(self, *, args: list[str]) -> CommandOutcome:
        """Run a command with the INVOKED worktree as the working directory."""
        return self.run(args=args, cwd=self.invoked_worktree)
