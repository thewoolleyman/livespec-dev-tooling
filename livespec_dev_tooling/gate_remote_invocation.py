"""The delegated gate client's host-invocation seam — R4.S7a.

Every command the gate client issues to a host goes through here, and nothing
here knows what a gate is. That is the cohesion line: HOW the client reaches a
host lives in this module, WHAT it does there lives in `gate_remote_client`. It
is also what lets the whole client be exercised against a canned runner with no
cluster, no mirror and no host touched.

THE TWO TRACKS ARE KEPT APART DELIBERATELY, and it is the same split
`fleet/_invocation_failure.py` records for the `gh` seam. A command that RAN is
a SUCCESS carrying its exit code as data, whatever that code reads; a command
that never ran is a FAILURE. Answering an absent binary with a fabricated exit
code makes the two indistinguishable, and callers then read the fabrication as
an answer — the defect the fleet reconcile's own command seam already paid for
once, when a `git log -1` exiting 128 on an unborn HEAD nearly made a hook
refuse the first commit of every fresh member repo.

Two lifters rather than one with a flag, because which one a step uses is a
real decision rather than a parameter: `require_success` is for a step whose
non-zero exit MEANS the step failed (the push, the submit, the delete), and
`require_invocation` for a step whose exit code is OBSERVATIONAL (the log
stream, whose exit merely echoes the gate's own).

`stream=True` hands the child THIS process's stdout and stderr, so "the log
reaches the caller's terminal" is a property of the INVOCATION — something a
canned runner can assert on — rather than of a write inside the client.
Capturing is exactly what would swallow the log, so the two modes are mutually
exclusive by construction.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, TypeAlias

# `returns` is VENDORED, not installed; a bare import here would resolve only
# when some earlier import in the process happened to run first.
_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.result import Failure, Result, Success  # noqa: E402  — vendor-path-aware import.

__all__: list[str] = [
    "GateCommandNotRun",
    "GateCommandOutcome",
    "GateCommandResult",
    "GateCommandRunner",
    "GateStepFailed",
    "Sleeper",
    "StepOutcome",
    "default_gate_command_runner",
    "default_sleeper",
    "require_invocation",
    "require_success",
]


@dataclass(frozen=True, kw_only=True)
class GateCommandResult:
    """Answer of one invocation that RAN — its exit code plus its streams.

    A streaming invocation captures nothing, so both streams are empty here
    while the child's output has already reached the terminal. The exit code is
    the only field a streaming step reads.
    """

    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True, kw_only=True)
class GateCommandNotRun:
    """An invocation that never HAPPENED.

    `argv` is carried because the diagnostic is useless without it: "the
    invocation did not happen" names no operation, and every consumer of this
    track renders a reason a human has to act on.
    """

    argv: tuple[str, ...]
    detail: str


@dataclass(frozen=True, kw_only=True)
class GateStepFailed:
    """A plumbing step that did not do its job.

    `returncode` is `None` — never a stand-in number — when there was no exit
    code at all, which is the one thing that tells a caller the command never
    ran rather than ran and refused.
    """

    step: str
    argv: tuple[str, ...]
    returncode: int | None
    detail: str


GateCommandOutcome: TypeAlias = Result[GateCommandResult, GateCommandNotRun]
StepOutcome: TypeAlias = Result[GateCommandResult, GateStepFailed]


class GateCommandRunner(Protocol):
    """Callable seam for every host command the gate client issues.

    The failure track carries ONLY "the invocation did not happen"; adjudicating
    an exit code belongs to whichever lifter the calling step chose.
    """

    def __call__(
        self,
        *,
        argv: list[str],
        cwd: Path,
        stdin: str | None = None,
        stream: bool = False,
    ) -> GateCommandOutcome: ...


class Sleeper(Protocol):
    """Seam for the wait between polls; the poll loop's only source of time."""

    def __call__(self, *, seconds: float) -> None: ...


def default_sleeper(*, seconds: float) -> None:
    """Sleep for `seconds` — the production `Sleeper`."""
    time.sleep(seconds)


def default_gate_command_runner(
    *,
    argv: list[str],
    cwd: Path,
    stdin: str | None = None,
    stream: bool = False,
) -> GateCommandOutcome:
    """Run `argv` in `cwd`, answering on the ran / did-not-run split.

    The PATH probe is separate from the spawn because the two failures call for
    different responses: an absent binary is an install problem, and an
    `OSError` out of the spawn is a permissions, resource, or TOCTOU problem.
    Neither may propagate — an exception out of this seam would abort a gate run
    mid-flight, after the ref has been pushed and before it has been deleted.
    """
    frozen = tuple(argv)
    program = frozen[0]
    if shutil.which(program) is None:
        return Failure(GateCommandNotRun(argv=frozen, detail=f"{program} not on PATH"))
    try:
        completed = subprocess.run(  # noqa: S603  — argv is a list; no shell is involved.
            list(argv),
            cwd=str(cwd),
            capture_output=not stream,
            text=True,
            check=False,
            input=stdin,
        )
    except OSError as unspawnable:
        return Failure(GateCommandNotRun(argv=frozen, detail=str(unspawnable)))
    return Success(
        GateCommandResult(
            returncode=completed.returncode,
            # A streaming child wrote to the terminal rather than to a pipe, so
            # these are `None`. Normalising to "" keeps the record's type honest
            # without inventing content a caller could mistake for output.
            stdout=completed.stdout or "",
            stderr=completed.stderr or "",
        )
    )


def _not_run(*, step: str, argv: Sequence[str], failure: GateCommandNotRun) -> StepOutcome:
    """Stamp the step onto a command that never ran, WITHOUT inventing a code."""
    return Failure(
        GateStepFailed(step=step, argv=tuple(argv), returncode=None, detail=failure.detail)
    )


def require_invocation(
    *, step: str, argv: Sequence[str], outcome: GateCommandOutcome
) -> StepOutcome:
    """Lift an outcome whose exit code is OBSERVATIONAL, not a verdict.

    The lenient lifter: the caller wants the number, so a non-zero exit passes
    straight through. Only a command that never ran fails the step.
    """
    if isinstance(outcome, Failure):
        return _not_run(step=step, argv=argv, failure=outcome.failure())
    return Success(outcome.unwrap())


def require_success(*, step: str, argv: Sequence[str], outcome: GateCommandOutcome) -> StepOutcome:
    """Lift an outcome whose non-zero exit MEANS the step failed.

    The strict lifter, for the plumbing steps: a push that was rejected or a
    submit the API server refused has not done its job, and the step carries the
    real exit code plus the program's own stderr so the reason survives.
    """
    if isinstance(outcome, Failure):
        return _not_run(step=step, argv=argv, failure=outcome.failure())
    result = outcome.unwrap()
    if result.returncode == 0:
        return Success(result)
    return Failure(
        GateStepFailed(
            step=step, argv=tuple(argv), returncode=result.returncode, detail=result.stderr
        )
    )
