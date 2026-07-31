"""The failure track shared by every subprocess seam in this package.

ONE type rather than one per seam. `GhRunner`, `CommandRunner` and
`GhDownloader` are three seams over the same operating-system fact — a
child process either started or it did not — and three byte-identical
dataclasses would be the `livespec-dev-tooling-8o8e.6` duplication
shape, where copies keep agreement by COPYING and drift the moment one
grows a field. `fleet/_pin_walk_failure.py` is the worked precedent for
extracting a shared failure type into a leaf module.

A LEAF: this module imports nothing from `livespec_dev_tooling.fleet`,
so `_context`, `_local_context` and `_snapshot` may all import it
without a cycle — `_snapshot` in particular must stay importable BY
`_context`.

WHAT BELONGS ON THIS TRACK, and it is narrower than "the command
failed". An invocation that COMPLETED and ANSWERED is a SUCCESS whatever
it answered: `gh` exiting 4 ran and said no, and its exit code is DATA
on the success track. Only the invocation never happening at all lands
here. Reading every non-zero exit as a failure is the tightening error
this thread has already committed once, when `git log -1` exiting 128 on
an unborn HEAD nearly made the commit-msg hook refuse the first commit
of every fresh member repo.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__: list[str] = [
    "BINARY_ABSENT",
    "DESTINATION_UNWRITABLE",
    "SPAWN_FAILED",
    "InvocationNotPerformed",
]

# The binary named by argv[0] is not on PATH. Previously spelled as a
# FABRICATED `returncode=127` on the success-shaped record, which is
# indistinguishable from a real program that genuinely exited 127 — the
# sentinel this conversion removes.
BINARY_ABSENT = "binary_absent"
# The binary resolved but the OS refused to start it: a non-executable
# file (`PermissionError`), a fork/exec failure, or a TOCTOU removal
# between the PATH probe and the spawn. Previously UNCAUGHT, so it
# propagated out of the seam and killed the whole nine-member sweep
# partway through one member.
SPAWN_FAILED = "spawn_failed"
# The download destination could not be opened for writing. Reachable
# only from the downloader seam, whose payload lands in a file rather
# than in captured stdout.
DESTINATION_UNWRITABLE = "destination_unwritable"


@dataclass(frozen=True, kw_only=True)
class InvocationNotPerformed:
    """A child process did not run — NOT a child process that ran and failed.

    `argv` is carried because the diagnostic is useless without it: "the
    invocation did not happen" names no operation, and every consumer of
    this track renders a reason a human has to act on.

    `kind` is a small closed vocabulary (the three module constants),
    matching `SnapshotUnavailable`'s existing `kind` spelling in
    `_snapshot.py` rather than inventing a second convention. The three
    stay APART because they call for different responses: a missing
    binary is an install problem, a spawn failure is a permissions or
    resource problem, and an unwritable destination is local disk.
    """

    argv: tuple[str, ...]
    kind: str
    detail: str

    @property
    def reason(self) -> str:
        """One human-readable line naming the kind and the program."""
        program = self.argv[0] if self.argv else "<no argv>"
        return f"{self.kind}: {program} ({self.detail})"
