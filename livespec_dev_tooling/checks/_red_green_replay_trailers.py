"""Git commit-message trailer I/O for `red_green_replay` — HEAD-state + trailer writer.

Extracted from `_red_green_replay_modes.py` so that module stays under
the file-LLOC ceiling (fleet-check-coverage). This sibling carries the
low-level git commit-message read/write surface the Red/Green/suite-green
handlers and the parent supervisor share: the HEAD-state resolver
(`head_red_awaiting_green`), the two HEAD readers (`head_trailer_value`,
`current_head_sha`), and the trailer writer (`write_trailers`).

`red_green_replay.py` imports `head_red_awaiting_green`;
`_red_green_replay_modes.py` imports the other three — both via the
`checks/` bare-sibling path after their own `sys.path` insert. The
leading underscore in the filename marks this a private helper rather
than a check entry point.

THE THREE READERS ARE ON THE `IOResult` RAILWAY — livespec-dev-tooling-qndn,
epic 8o8e. Each ran `subprocess.run` with no guard and folded every
failure onto its ordinary answer:

- `head_red_awaiting_green` decides WHICH LEG of the commit ritual runs.
  A non-zero git exit yielded empty stdout, which reads as "no Red
  trailers", which routes to the suite-green leg. That is a fail-WRONG,
  not a fail-closed: the hook would stamp the wrong evidence shape onto a
  commit rather than refuse it.
- `head_trailer_value` and `current_head_sha` said so in their own
  docstrings — "or empty if absent", "or empty on failure". The sentinel
  stated aloud is still a sentinel, and the first of the two conflates an
  ABSENT trailer (an answer) with a git that did not run.

⛔ AND THE ONE CASE A NAIVE CONVERSION BREAKS, which is why
`head_red_awaiting_green` RESOLVES HEAD before reading it: in a repository
with NO COMMITS, `git log -1` exits 128. That is an unborn HEAD, not a
broken environment — and it is a REAL state, because `just bootstrap`
installs these hooks BEFORE a new member repo's first commit. Reading a
non-zero `git log` as a failure would refuse that first commit outright.
`git rev-parse --verify --quiet HEAD` separates the two: exit 1 is "no
HEAD yet" (an answer — there is no Red awaiting a Green), and any other
non-zero is a git that did not answer. The extra invocation buys that
distinction and nothing else.

`write_trailers` is deliberately NOT converted. It is annotated `-> None`
and reports nothing to its caller today; giving it a failure track is a
separate decision about what the ritual should do when git cannot WRITE a
trailer, and folding that into a type change would smuggle a behavior
change through a refactor.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

# Carried even though this module is only ever reached BY IMPORT: without it
# the vendored `returns` resolves only because both importers happen to carry
# the preamble, which is a property of the callers rather than of this file.
# The module that broke the 2026-07-30 release fan-out fleet-wide was in
# exactly that state until it became a process entry point — and this module
# is imported BY one, the commit-msg hook.
_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.io import IOFailure, IOResult, IOSuccess  # noqa: E402  — vendor-path-aware import.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware import.

if TYPE_CHECKING:  # pragma: no cover
    import structlog.stdlib

__all__: list[str] = [
    "GitCommandFailed",
    "_narrate_git_failure",
    "current_head_sha",
    "dropped_red_trailers",
    "head_red_awaiting_green",
    "head_trailer_value",
    "write_trailers",
]


# `git rev-parse --verify --quiet <ref>` exits 1 when the ref does not
# resolve. For `HEAD` in a fresh repository that is an UNBORN head — the
# state every repo is in before its first commit — and it is an answer.
_UNBORN_HEAD = 1

# What an unborn HEAD answers: there is no Red commit, so none is awaiting a
# Green. Named rather than written inline because the bare literal is also
# what the pre-conversion reader returned for a git that never ran, and the
# whole point of the conversion is that those are different answers.
_NO_RED_AWAITING_GREEN = False

_HEAD_PROBE_ARGS: list[str] = ["rev-parse", "--verify", "--quiet", "HEAD"]
_HEAD_MESSAGE_ARGS: list[str] = ["log", "-1", "--format=%B"]

_RED_TRAILER_KEY = "TDD-Red-Test-File-Checksum:"
_GREEN_TRAILER_KEY = "TDD-Green-Verified-At:"
# `_RED_TRAILER_KEY` above is the ONE key the HEAD-state resolver routes on.
# This is the whole SET, which is a different question: routing asks whether a
# Red exists at HEAD, and `dropped_red_trailers` asks whether the amend being
# authored still CARRIES it.
_RED_TRAILER_PREFIX = "TDD-Red-"


@dataclass(frozen=True, kw_only=True)
class GitCommandFailed:
    """A `git` invocation the commit ritual depends on did not answer.

    Deliberately NOT inhabited by "git answered, and the answer was empty":
    an absent trailer and an unborn HEAD are both ordinary answers. `argv` is
    the exact command so the operator can rerun it — the hook runs inside
    `git commit`, where a bare "git failed" leaves nothing to act on.
    """

    argv: str
    detail: str


def _command_failure(*, args: list[str], detail: str) -> GitCommandFailed:
    return GitCommandFailed(argv=" ".join(["git", *args]), detail=detail)


def _completed_git(
    *, args: list[str]
) -> IOResult[subprocess.CompletedProcess[str], GitCommandFailed]:
    """Run `git <args>` in the process cwd, or name the invocation that could not run.

    The failure track here is narrow and STRUCTURAL: `subprocess.run` itself
    raising. There is no `shutil.which` guard anywhere on this path — the hook
    is invoked BY git, so git existing reads as a given, and "reads as a
    given" is exactly what this catch replaces. What a given exit code MEANS
    is each reader's own policy, one layer up.
    """
    try:
        completed = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as unusable:
        return IOFailure(_command_failure(args=args, detail=str(unusable)))
    return IOSuccess(completed)


def _git_stdout(*, args: list[str]) -> IOResult[str, GitCommandFailed]:
    """Stripped stdout of a git command for which EVERY non-zero exit is a failure.

    Both readers built on this run against a HEAD the caller has already
    established, so a non-zero exit contradicts that precondition. The exit
    code rides in `detail` because git's stderr is sometimes empty and a
    diagnostic with neither is unactionable.
    """
    probed = _completed_git(args=args)
    if isinstance(probed, IOFailure):
        return probed
    completed = unsafe_perform_io(probed.unwrap())
    if completed.returncode != 0:
        return IOFailure(
            _command_failure(
                args=args, detail=f"exit {completed.returncode}: {completed.stderr.strip()}"
            )
        )
    return IOSuccess(completed.stdout.strip())


def _narrate_git_failure(*, log: structlog.stdlib.BoundLogger, failed: GitCommandFailed) -> int:
    """Report an unanswered git command and REJECT the commit (exit 1).

    ⛔ Never exit 0, and never fall through to a leg. WHICH leg the ritual
    runs is decided by reading HEAD; if that read did not happen, the ritual
    does not know what it is verifying, and stamping evidence it could not
    check is worse than refusing the commit. Shared by both callers so the
    refusal is worded once.
    """
    log.error(
        "a git command the Red-Green-Replay ritual depends on did not answer; "
        "the commit is refused rather than routed to a leg chosen from a "
        "reading that never happened",
        check_id="red-green-replay-git-command-failed",
        argv=failed.argv,
        detail=failed.detail,
        hint=(
            "Rerun the reported `argv` from the repository root to see git's "
            "own diagnostic. This is an ENVIRONMENT failure, not a protocol "
            "violation: nothing about the staged tree needs changing."
        ),
    )
    return 1


def head_red_awaiting_green() -> IOResult[bool, GitCommandFailed]:
    """Whether HEAD carries `TDD-Red-*` trailers WITHOUT `TDD-Green-*`.

    The genuine amend-in-progress signature (work-item
    livespec-dev-tooling-xn0): a COMPLETED Red+Green commit at HEAD
    also carries Red trailers — the normal state of real history —
    so keying Branch-4 routing on Red-trailer presence alone
    misrouted every fresh product commit atop a completed pair into
    the Green-amend leg, stamping bare `TDD-Green-*` trailers that
    the commit-range validator then rejected. Only a Red awaiting
    its Green may take the amend leg; everything else falls through
    to the suite-green leg.

    HEAD is resolved before it is read: see the module docstring's unborn-HEAD
    note, which is the case that makes the extra invocation load-bearing
    rather than defensive.
    """
    resolved = _completed_git(args=_HEAD_PROBE_ARGS)
    if isinstance(resolved, IOFailure):
        return resolved
    head = unsafe_perform_io(resolved.unwrap())
    if head.returncode == _UNBORN_HEAD:
        return IOSuccess(_NO_RED_AWAITING_GREEN)
    if head.returncode != 0:
        return IOFailure(
            _command_failure(
                args=_HEAD_PROBE_ARGS,
                detail=f"exit {head.returncode}: {head.stderr.strip()}",
            )
        )
    return _git_stdout(args=_HEAD_MESSAGE_ARGS).map(
        lambda message: _RED_TRAILER_KEY in message and _GREEN_TRAILER_KEY not in message
    )


def _red_trailers_absent_from(*, head_message: str, message: str) -> tuple[str, ...]:
    carried = (line.strip() for line in head_message.splitlines())
    return tuple(
        line for line in carried if line.startswith(_RED_TRAILER_PREFIX) and line not in message
    )


def dropped_red_trailers(*, message: str) -> IOResult[tuple[str, ...], GitCommandFailed]:
    """The `TDD-Red-*` lines HEAD's message carries that `message` no longer does.

    An EMPTY tuple is the ordinary answer "the amend kept the block" — what
    `git commit --amend --no-edit` produces, since it passes the existing
    message through untouched. A NON-EMPTY tuple is the measured half-pair
    (work-item livespec-dev-tooling-zv78): `git commit --amend -m` and
    `--amend -F` REPLACE the entire message, destroying the Red evidence at
    the very moment the Green leg reads it off HEAD and appends its own
    trailers beside nothing. Measured twice — PR #1022 (`-F`) and PR #1111
    (`-m`), each producing a commit carrying `Red: 0 / Green: 2`.

    ⛔ Empty must NOT also spell a git that did not answer, which is why this
    rides the railway: the two would be indistinguishable, and the failure
    would read as the permissive answer, admitting exactly the amend the
    caller asks about.

    CONTAINMENT, not line-order equality: git's `interpret-trailers` may
    reflow the block, and an author rewording the body above it is doing
    nothing wrong. Only the disappearance of a Red line is.
    """
    return _git_stdout(args=_HEAD_MESSAGE_ARGS).map(
        lambda head_message: _red_trailers_absent_from(head_message=head_message, message=message)
    )


def head_trailer_value(*, key: str) -> IOResult[str, GitCommandFailed]:
    """The value of HEAD~0's named trailer — empty when the trailer is ABSENT.

    Empty stays an ordinary answer: a commit legitimately carries no trailer
    of a given key. What is no longer spelled the same way is a git that did
    not run, which the old docstring's "or empty if absent" quietly covered.
    """
    return _git_stdout(args=["log", "-1", f"--pretty=%(trailers:key={key},valueonly)"])


def current_head_sha() -> IOResult[str, GitCommandFailed]:
    """The current HEAD SHA via `git rev-parse HEAD`.

    Called only from the Green leg, where HEAD is the Red commit being
    amended, so there is no unborn-HEAD case here and every non-zero exit is
    a failure. Its old docstring said "or empty on failure" — the sentinel
    stated aloud, and that empty string landed in a
    `TDD-Green-Parent-Reflog` trailer, so the failure was recorded AS
    EVIDENCE.
    """
    return _git_stdout(args=["rev-parse", "HEAD"])


def write_trailers(*, msg_path: Path, trailers: tuple[tuple[str, str], ...]) -> None:
    # Two-step write to handle the v034 D2-D3 Red re-amend case
    # (surfaced concretely 2026-05-04 during v039 D3 authoring):
    # three Red re-amends produced three sets of `TDD-Red-*`
    # trailers in the commit message, after which
    # `head_trailer_value` returned a newline-joined string of
    # three identical paths and the Green-mode handler raised
    # FileNotFoundError on Path.read_bytes().
    #
    # Step 1: pre-strip any line in the existing message whose
    # leading token matches one of the keys we're about to write.
    # We CANNOT use `git interpret-trailers --if-exists=replace`
    # here because git's `replace` matching uses prefix-aliasing
    # (treats `TDD-Red-Test` and `TDD-Red-Test-File-Checksum` as
    # the same trailer when one is a prefix of the other) and
    # silently DROPS the longer-keyed trailer when a shorter
    # prefix is present. The Red trailer schema has exactly
    # this collision (`TDD-Red-Test` is a strict prefix of
    # `TDD-Red-Test-File-Checksum` and `TDD-Red-Output-Checksum`'s
    # base form), so prefix-matching corrupts the trailer set
    # rather than fixing the duplicate-append bug.
    #
    # Step 2: invoke `git interpret-trailers --in-place` to add
    # the new trailers. Git's trailer-block-formatting rules
    # (blank-line separator between body and trailer block,
    # `Key: value` formatting, etc.) are preserved.
    keys_to_replace = {key for key, _ in trailers}
    original_text = msg_path.read_text(encoding="utf-8")
    stripped_lines: list[str] = []
    for line in original_text.splitlines(keepends=True):
        head = line.split(":", 1)[0]
        if head in keys_to_replace:
            continue
        stripped_lines.append(line)
    _ = msg_path.write_text("".join(stripped_lines), encoding="utf-8")

    args: list[str] = []
    for key, value in trailers:
        args.extend(["--trailer", f"{key}: {value}"])
    _ = subprocess.run(
        ["git", "interpret-trailers", "--in-place", *args, str(msg_path)],
        capture_output=True,
        text=True,
        check=False,
    )
