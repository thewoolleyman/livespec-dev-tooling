"""_manifest_git — the fleet manifest read over GIT, off the REST budget.

WHY THIS MODULE EXISTS, and it is a measurement rather than a
preference. `check-fleet-conformance` reads ONE file from
`thewoolleyman/livespec` — `.livespec-fleet-manifest.jsonc` — and that
read is the run's ROOT FACT: without it no member is known, so its loss
is a PRECONDITION failure (exit 1) rather than one row's named skip. A
red default branch then trips the Dispatcher's master-CI admission gate
AND the pre-push `check-master-ci-green` inside every sandbox, so a
single refused read stalls the whole factory.

On 2026-09-06 it did, three times in one afternoon
(`livespec-dev-tooling-7yeveq`): HTTP 403 `API rate limit exceeded for
installation ID 131208965`, with no code change between a failing
attempt and a passing one. The installation's PRIMARY core budget was
11,074/12,500 remaining at 18:14:16Z and 12,401/12,500 at 18:21:15Z,
while the refusals landed at 18:16:02Z and 18:17:31Z — and this fleet's
entire nine-PR release fan-out costs ~81 reads on `_snapshot`'s tarball
route, so >11,000 requests in ~100 s is not reachable by its known
traffic. The refusals were a SECONDARY (abuse) limit rendered with the
primary limit's message.

⛔ A REMAINING-COUNT PREFLIGHT CANNOT FIX THIS, BY CONSTRUCTION. The
job's own `.github/actions/github-rate-budget-token` gate
(`min-core-remaining` 500) reported "rate budget healthy" 72 s before
the refusal. It polls `/rate_limit`, which reports the PRIMARY pool and
says nothing about a secondary limiter, so no threshold on it — and no
larger cushion — sees the refusal coming. Raising the floor would buy
false confidence, which is worse than the red.

SO THE ROUTE CHANGES, NOT THE VERDICT. `git` speaks to github.com over
a quota that is not the REST installation pool, so reading the file with
`git clone` + `git show` removes this read from the pool entirely — the
same move `_snapshot` already made for the far larger per-file walk
(653 reads -> 9). The contents API stays as a FALLBACK for the hosts
where git cannot answer, so a git-less runner is no worse off than
before. An unreadable manifest still fails loud on BOTH routes, and both
causes are recorded.

⛔ WHAT WAS DELIBERATELY NOT DONE: teaching the master-green gates to
treat a rate-limited conformance failure as non-blocking. A gate that
passes because the check could not RUN is the vacuous-gate defect this
repository has paid for three times (`z4qi`, `sh71`, `x7ml`). The
starvation it would relieve is real; the cure is worse, and nothing here
relaxes a verdict.

THE READ IS TWO INVOCATIONS AND NEITHER IS OPTIONAL. A blobless,
single-branch, depth-1 clone (`--filter=blob:none --no-checkout`) fetches
commits and trees but no file contents; `git show HEAD:<path>` then pulls
exactly the one blob from the promisor remote. `HEAD` is what resolves
the repository's default branch WITHOUT `FleetContext.canonical_ref`'s
`repos/{owner}/{repo}` call — which would spend the very pool this read
is leaving, and would leave the read half-exposed while looking fixed.

⛔ THE CREDENTIAL REACHES GIT THROUGH A HELPER, NEVER THROUGH ARGV. The
obvious spelling — `https://x-access-token:<token>@github.com/...` — puts
a secret in a process argument, which this package forbids outright
(`fleet/CLAUDE.md`: secret VALUES never appear in argv, logs, or
outcomes). `credential.helper=!gh auth git-credential` hands git the
token `gh` already holds, and the inherited helper list is cleared first
(the empty `credential.helper=`) so a host's own helper cannot answer
with a different identity than the one the rest of the lane runs as.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

# `returns` is VENDORED, not installed, so a bare import resolves only if some
# EARLIER import in the same process already put `_vendor/` on `sys.path`.
# Declared here regardless of who currently imports this module first, because
# the hazard is an ordering dependency no reader can see.
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
from livespec_dev_tooling.fleet._local_context import (  # noqa: E402
    CommandOutcome,
    CommandResult,
    CommandRunner,
    command_answer,
)

if TYPE_CHECKING:
    from livespec_dev_tooling.fleet._context import FleetContext

__all__: list[str] = [
    "GIT_READ_OPERATION",
    "GIT_READ_REFUSED",
    "GitReadRefused",
    "GitReader",
    "default_git_reader",
    "git_file_text",
    "manifest_text",
]

# The seam this module reads through, named for what it carries rather than
# aliased for style: it IS `_local_context`'s host-command seam (`args` includes
# the program, a program that RAN is a success whatever its exit code), and
# reusing it is what keeps the package's THREE subprocess seams sharing ONE
# failure type instead of growing a fourth that drifts.
GitReader = CommandRunner

# The `ReadFailure.operation` this route records under. It names the READ KIND,
# like `contents` / `tree` / `manifest` beside it, so a consumer can tell a git
# refusal from a contents refusal without parsing paths.
GIT_READ_OPERATION = "manifest_git"
# The `kind` for a git that RAN and said no. Deliberately NOT one of
# `classify_gh_failure`'s kinds: that vocabulary classifies GitHub's HTTP
# answers, and reusing `forbidden` or `rate_limited` here would assert an HTTP
# status this route never saw.
GIT_READ_REFUSED = "git_unreadable"

_ORIGIN = "https://github.com"
_WORKSPACE_PREFIX = "livespec-fleet-manifest-"
_CLONE_DIRNAME = "repo"
# Git's own switch for "never prompt a terminal for credentials". It has NO
# config-file equivalent, which is why this module carries its own seam rather
# than reusing `default_command_runner`: a credential prompt inside `just check`
# or the CI job does not fail, it WAITS — converting a bounded red into an
# unbounded stall, which is strictly worse than the failure being fixed here.
_NO_PROMPT_VAR = "GIT_TERMINAL_PROMPT"
# The empty first entry CLEARS whatever helpers the host has configured; the
# second supplies the token `gh` already holds, without it ever entering argv.
_CREDENTIAL_ARGS: tuple[str, ...] = (
    "-c",
    "credential.helper=",
    "-c",
    "credential.helper=!gh auth git-credential",
)
# Everything a one-file read needs and nothing more: no blobs (`--filter`), no
# working tree (`--no-checkout`), one branch, one commit, no tags.
_CLONE_ARGS: tuple[str, ...] = (
    "clone",
    "--quiet",
    "--depth",
    "1",
    "--single-branch",
    "--no-tags",
    "--filter=blob:none",
    "--no-checkout",
)


@dataclass(frozen=True, kw_only=True)
class GitReadRefused:
    """A git-transport read that did not produce the file's bytes.

    Carries what `FleetContext.record_read_failure` needs and no more —
    the caller owns `operation` and `path`, because it is the caller that
    knows WHICH read this was. It is not a `ReadFailure`: that type's
    `detail` is sanitized by construction, and a value built here has not
    passed through the sink that redacts it yet.
    """

    returncode: int
    kind: str
    detail: str


def default_git_reader(*, args: list[str], cwd: Path | None = None) -> CommandOutcome:
    """Run `args` with terminal prompting DISABLED; a git that never ran FAILS.

    A `CommandRunner` in shape, so any test can replace it, and a completed
    invocation is a SUCCESS carrying its exit code as data however that code
    reads — `git clone` exiting 128 on a repository the credential cannot see
    RAN and answered.
    """
    argv = tuple(args)
    if shutil.which(argv[0]) is None:
        return IOFailure(
            InvocationNotPerformed(argv=argv, kind=BINARY_ABSENT, detail=f"{argv[0]} not on PATH")
        )
    try:
        completed = subprocess.run(
            list(argv),
            capture_output=True,
            text=True,
            check=False,
            cwd=None if cwd is None else str(cwd),
            env={**os.environ, _NO_PROMPT_VAR: "0"},
        )
    except OSError as unspawnable:
        # Caught rather than propagated for the reason every sibling seam
        # catches it: an uncaught spawn failure leaves the whole sweep dead
        # partway through one read instead of failing that read.
        return IOFailure(
            InvocationNotPerformed(argv=argv, kind=SPAWN_FAILED, detail=str(unspawnable))
        )
    return IOSuccess(
        CommandResult(
            returncode=completed.returncode, stdout=completed.stdout, stderr=completed.stderr
        )
    )


def _answered(*, run: GitReader, args: list[str]) -> str | GitReadRefused:
    """One git invocation's stdout, or WHY it produced none.

    The two refusals stay apart because they want different operator
    responses: a git that never ran is an install or permissions problem on
    THIS host, and a git that ran and exited non-zero is an answer from the
    remote.
    """
    answer = command_answer(outcome=run(args=args))
    if isinstance(answer, InvocationNotPerformed):
        # `returncode=0` beside a `kind` that names the cause — the existing
        # spelling for "nothing ran", kept so a fabricated exit code never
        # stands in for a real one.
        return GitReadRefused(returncode=0, kind=answer.kind, detail=answer.reason)
    if answer.returncode != 0:
        return GitReadRefused(
            returncode=answer.returncode, kind=GIT_READ_REFUSED, detail=answer.stderr
        )
    return answer.stdout


def git_file_text(
    *, run: GitReader, owner: str, repo: str, path: str
) -> IOResult[str, GitReadRefused]:
    """`path` from `owner/repo`'s default branch, read over the git transport.

    `IOResult` rather than `Result`: this creates a temporary directory on the
    local filesystem with no seam between it and the disk, which is what
    livespec v179 member 1 clause (c) sees and is the honest type. The
    NETWORK half does go through the injected `run` seam, which is what keeps
    every test of this hermetic.

    The workspace is discarded on both tracks. Keeping a blobless clone would
    cost disk for a payload nothing reads twice, and leaving it behind on the
    failure track would leave a half-built checkout for the next run to find.
    """
    with tempfile.TemporaryDirectory(prefix=_WORKSPACE_PREFIX) as workspace:
        checkout = Path(workspace) / _CLONE_DIRNAME
        url = f"{_ORIGIN}/{owner}/{repo}.git"
        cloned = _answered(
            run=run, args=["git", *_CREDENTIAL_ARGS, *_CLONE_ARGS, url, str(checkout)]
        )
        if isinstance(cloned, GitReadRefused):
            return IOFailure(cloned)
        shown = _answered(run=run, args=["git", "-C", str(checkout), "show", f"HEAD:{path}"])
        if isinstance(shown, GitReadRefused):
            return IOFailure(shown)
        return IOSuccess(shown)


def manifest_text(
    *, ctx: FleetContext, read_git: GitReader | None, repo: str, path: str
) -> str | None:
    """The manifest bytes: git first when a git seam is injected, else contents API.

    `read_git=None` is the FAIL-SAFE default the operator-invoked lanes keep —
    no construction site acquires a subprocess it did not ask for — and the
    central CI lane injects the real seam, because it is the lane whose red
    stalls the factory.

    ⛔ THE GIT CAUSE IS RECORDED ONLY WHEN THE FALLBACK ALSO FAILS, and that
    is a deliberate asymmetry rather than an omission. `read_failure_cause` is
    the field a reader of a GREEN run scans to decide whether anything
    degraded; recording a refusal that the fallback then answered would make
    every git-less host report `other-read-failure` on a healthy run, which is
    how a diagnostic field becomes noise a reader learns to skip. When BOTH
    routes fail the git cause is reported beside the contents cause, so the
    operator sees which route failed and how instead of guessing whether the
    new route is even wired.
    """
    if read_git is None:
        return ctx.file_text(repo=repo, path=path)
    read = git_file_text(run=read_git, owner=ctx.owner, repo=repo, path=path)
    if not isinstance(read, IOFailure):
        return unsafe_perform_io(read.unwrap())
    fallback = ctx.file_text(repo=repo, path=path)
    if fallback is None:
        refused = unsafe_perform_io(read.failure())
        ctx.record_read_failure(
            operation=GIT_READ_OPERATION,
            path=f"{repo}:{path}",
            returncode=refused.returncode,
            kind=refused.kind,
            detail=refused.detail,
        )
    return fallback
