"""The `gh` subprocess seam for the fleet-membership contract.

Split out of `_context` to keep that file under the 250-LLOC hard
ceiling the railway conversion pushed it past, and coherent with
`_snapshot.py` already owning the DOWNLOADER seam separately.
`_context` re-exports every name here, so no consumer import changes.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

# `returns` is VENDORED, not installed; a bare import here would resolve
# only when some earlier import in the process happened to run first.
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
    "GhOutcome",
    "GhResult",
    "GhRunner",
    "default_gh_runner",
    "gh_answer",
]


@dataclass(frozen=True, kw_only=True)
class GhResult:
    """Answer of one `gh` invocation that RAN (exit code + captured streams)."""

    returncode: int
    stdout: str
    stderr: str


# The railway alias for this seam, matching `_local_context.CommandOutcome`
# and `_snapshot.DownloadResult`. The three subprocess seams share ONE
# failure type, so they cannot drift about what "did not run" means.
GhOutcome = IOResult[GhResult, InvocationNotPerformed]


class GhRunner(Protocol):
    """Callable seam for `gh` invocations; `args` excludes the leading `gh`.

    The failure track carries ONLY "the invocation did not happen". A `gh`
    that RAN is a success carrying its exit code as data, however that code
    reads — the seam does not adjudicate what GitHub said, and GitHub says
    404 and 422 as ordinary answers.
    """

    def __call__(self, *, args: list[str], stdin: str | None = None) -> GhOutcome: ...


def gh_answer(*, outcome: GhOutcome) -> GhResult | InvocationNotPerformed:
    """The answer of a `gh` that RAN, or the record of one that did not.

    The `_local_context.command_answer` shape, for the same reason: every
    consumer needs exactly this split, and eleven inline `isinstance` +
    `unsafe_perform_io` pairs would be the duplication shape one layer up.
    """
    if isinstance(outcome, IOFailure):
        return unsafe_perform_io(outcome.failure())
    return unsafe_perform_io(outcome.unwrap())


def default_gh_runner(*, args: list[str], stdin: str | None = None) -> GhOutcome:
    """Run `gh <args>`; a `gh` that never ran FAILS.

    This used to answer an absent `gh` with `GhResult(returncode=127)` — a
    fabricated code a real `gh` can also return, so "never ran" and "ran
    and exited 127" were the same value. It is a failure-track value now,
    and a completed invocation is a success whatever its exit code.
    """
    argv = ("gh", *args)
    if shutil.which("gh") is None:
        return IOFailure(
            InvocationNotPerformed(argv=argv, kind=BINARY_ABSENT, detail="gh CLI not on PATH")
        )
    try:
        completed = subprocess.run(
            list(argv),
            capture_output=True,
            text=True,
            check=False,
            input=stdin,
        )
    except OSError as unspawnable:
        # Previously UNCAUGHT, so it propagated out of the seam and killed
        # the whole nine-member sweep partway through one member rather
        # than failing that member.
        return IOFailure(
            InvocationNotPerformed(argv=argv, kind=SPAWN_FAILED, detail=str(unspawnable))
        )
    return IOSuccess(
        GhResult(
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
    )
