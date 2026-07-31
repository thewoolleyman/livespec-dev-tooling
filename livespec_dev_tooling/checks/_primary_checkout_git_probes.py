"""_primary_checkout_git_probes — git rev-parse / git config probes for the hook check.

Extracted from `primary_checkout_commit_refuse_hook_installed.py` so
the parent check stays under the file-LLOC ceiling
(fleet-check-coverage). This sibling carries ONLY the project-agnostic
git-state probes the parent's `main()` sequences: is-inside-work-tree,
is-git-repo-at-all, core-bare-flag, sandbox-exempt, git-common-dir, and
work-tree-root. Each shells out to `git` against a caller-supplied
`cwd`; none reads the parent's constants or the canonical bodies.

EVERY PROBE IS ON THE `IOResult` RAILWAY — livespec-dev-tooling-qndn,
epic 8o8e, the fleet-wide ROP conversion. Each one shells out, so each
one had an inhabited failure track it could not express:

- the four `bool` probes returned False both for "git says no" and for
  "git never answered". `is_git_repo_at_all` is THE discriminator the
  parent uses to tell "not a repo" (skip, exit 0) from a bare-flag
  regression (fail), so a broken environment routed to SKIP — a green
  that means nothing.
- `git_common_dir` and `work_tree_root` used `check=True`, and their
  docstrings advertised the raise ("raises rather than silently
  returning a sentinel"). An uncaught failure track stated in prose is
  still an uncaught failure track.

WHAT IS AND IS NOT A FAILURE HERE, because that split is the substance
of the conversion rather than the type change. An invocation that
COMPLETES and answers is a success WHATEVER it answers: `git rev-parse
--git-dir` exiting non-zero means "not a repository", and `git config
--get <key>` exiting 1 means the key is UNSET — both are ANSWERS the
caller acts on. A failure is git not answering at all: `subprocess.run`
raising (git gone from PATH after the caller's `shutil.which` guard, a
`git` that cannot be exec'd, a fork failure), or a command exiting
non-zero where the probe's own precondition says it cannot.

The leading underscore in the filename marks this as a private helper
module; its behavior is exercised through the parent check's
subprocess contract and its own mirror-paired test.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# Carried even though this module is only ever reached BY IMPORT today: without
# it the vendored `returns` resolves only because the ONE importer happens to
# carry the preamble, which is a property of the caller rather than of this
# file. The module that broke the 2026-07-30 release fan-out fleet-wide was in
# exactly that state until it became a process entry point.
_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.io import IOFailure, IOResult, IOSuccess  # noqa: E402  — vendor-path-aware import.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware import.

__all__: list[str] = [
    "GitProbeFailed",
    "core_bare_is_true",
    "git_common_dir",
    "is_git_repo_at_all",
    "is_inside_work_tree",
    "sandbox_exempt_is_true",
    "work_tree_root",
]


# `git config --get <key>` exits 1 — and prints nothing — when the key is
# UNSET. That is the ANSWER "no value is configured, so git's default
# applies", and it is the ONLY non-zero exit the two config probes accept as
# one. Every other non-zero code (an unreadable config file, a repo git
# refuses to open) is a read that did not happen.
_CONFIG_KEY_UNSET = 1

# What an UNSET key resolves to for both keys this module reads: git's default
# for `core.bare` is false, and an absent `livespec.sandboxExempt` marker is
# not a declaration. Named rather than written inline because the bare literal
# is the value the pre-conversion probes returned for a FAILED read too, and
# the whole point of the conversion is that those are different answers.
_UNSET_KEY_RESOLVES_TO = False

_GIT_TRUE = "true"


@dataclass(frozen=True, kw_only=True)
class GitProbeFailed:
    """A probe could not obtain an answer from `git`.

    Deliberately NOT inhabited by "git answered no": see the module
    docstring's split. Every field exists so the operator can act without
    guessing — `argv` and `cwd` together are the exact command to rerun, and
    the parent check narrates all four into its structured finding. A bare
    "a git probe failed" would be the same manufactured-confidence shape the
    conversion removes, one level up.
    """

    probe: str
    argv: str
    cwd: str
    detail: str


def _probe_failure(*, probe: str, cwd: Path, args: list[str], detail: str) -> GitProbeFailed:
    return GitProbeFailed(probe=probe, argv=" ".join(["git", *args]), cwd=str(cwd), detail=detail)


def _completed_git(
    *, probe: str, cwd: Path, args: list[str]
) -> IOResult[subprocess.CompletedProcess[str], GitProbeFailed]:
    """Run `git <args>` in `cwd`, or name the invocation that could not run.

    The failure track here is narrow and STRUCTURAL: `subprocess.run` itself
    raising. What a given exit code MEANS is each probe's own policy, one
    layer up, so a completed invocation is a success here however it exited.
    """
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as unusable:
        return IOFailure(_probe_failure(probe=probe, cwd=cwd, args=args, detail=str(unusable)))
    return IOSuccess(completed)


def _git_stdout(*, probe: str, cwd: Path, args: list[str]) -> IOResult[str, GitProbeFailed]:
    """Stripped stdout of a git command for which EVERY non-zero exit is a failure.

    For the three `rev-parse` probes the caller's precondition (a surrounding
    repository, a surrounding work tree) is what makes a non-zero exit
    impossible-if-the-precondition-holds — so a non-zero exit is the
    precondition being false, which is a broken environment rather than an
    answer. The exit code rides in `detail` because git's stderr is sometimes
    empty and a diagnostic with neither is unactionable.
    """
    probed = _completed_git(probe=probe, cwd=cwd, args=args)
    if isinstance(probed, IOFailure):
        return probed
    completed = unsafe_perform_io(probed.unwrap())
    if completed.returncode != 0:
        return IOFailure(
            _probe_failure(
                probe=probe,
                cwd=cwd,
                args=args,
                detail=f"exit {completed.returncode}: {completed.stderr.strip()}",
            )
        )
    return IOSuccess(completed.stdout.strip())


def _git_config_is_true(*, probe: str, cwd: Path, key: str) -> IOResult[bool, GitProbeFailed]:
    """Whether `git config --get <key>` resolves to the literal `true`.

    Three outcomes, and keeping them apart is the whole point: exit 1 is the
    key being UNSET (False, an answer); exit 0 compares the value (only the
    literal `true` is True — the marker is a declaration, not the mere
    presence of a key); any other exit is a read that did not happen.
    """
    args = ["config", "--get", key]
    probed = _completed_git(probe=probe, cwd=cwd, args=args)
    if isinstance(probed, IOFailure):
        return probed
    completed = unsafe_perform_io(probed.unwrap())
    if completed.returncode == _CONFIG_KEY_UNSET:
        return IOSuccess(_UNSET_KEY_RESOLVES_TO)
    if completed.returncode != 0:
        return IOFailure(
            _probe_failure(
                probe=probe,
                cwd=cwd,
                args=args,
                detail=f"exit {completed.returncode}: {completed.stderr.strip()}",
            )
        )
    return IOSuccess(completed.stdout.strip() == _GIT_TRUE)


def _absolute_common_dir(*, cwd: Path, raw: str) -> Path:
    candidate = Path(raw)
    if candidate.is_absolute():
        return candidate
    return (cwd / candidate).resolve()


def is_inside_work_tree(*, cwd: Path) -> IOResult[bool, GitProbeFailed]:
    """Whether `cwd` is inside a git working tree.

    Uses `git rev-parse --is-inside-work-tree`. The caller invokes this only
    after `is_git_repo_at_all` has confirmed a surrounding repo, so the
    command exits `0` and prints `true`/`false`; a `false` (e.g., cwd is
    inside the `.git` directory itself, which is a git context that is NOT a
    working tree) is an ANSWER. A non-zero exit contradicts that precondition
    and is a Failure — reporting it as `False` made a broken environment
    indistinguishable from a bare repo, which the parent check then narrated
    as a skip.
    """
    return _git_stdout(
        probe="is_inside_work_tree", cwd=cwd, args=["rev-parse", "--is-inside-work-tree"]
    ).map(lambda answer: answer == _GIT_TRUE)


def is_git_repo_at_all(*, cwd: Path) -> IOResult[bool, GitProbeFailed]:
    """Whether `cwd` is inside ANY git repository (work tree OR bare).

    Uses `git rev-parse --git-dir`, which exits `0` for both a normal
    working-tree clone and a `core.bare = true` repository, and non-zero when
    there is no surrounding repo. That non-zero exit is THE ANSWER "not a
    repository" — the one non-zero this module reads as a value — so it stays
    on the success track. This is the discriminator that lets the check
    distinguish a genuinely-not-a-repo directory (skip) from a bare-flag
    regression (fail), which is exactly why a git that never ran must not
    reach the caller spelled the same way.
    """
    return _completed_git(probe="is_git_repo_at_all", cwd=cwd, args=["rev-parse", "--git-dir"]).map(
        lambda completed: completed.returncode == 0
    )


def core_bare_is_true(*, cwd: Path) -> IOResult[bool, GitProbeFailed]:
    """Whether `git config --get core.bare` resolves to `true`.

    The caller MUST have verified `cwd` is inside a git repository via
    `is_git_repo_at_all` first. An unset key exits 1 and prints nothing, which
    is git's default `false` — an answer, not a failed read.
    """
    return _git_config_is_true(probe="core_bare_is_true", cwd=cwd, key="core.bare")


def sandbox_exempt_is_true(*, cwd: Path) -> IOResult[bool, GitProbeFailed]:
    """Whether `git config --get livespec.sandboxExempt` resolves to `true`.

    The DECLARED sandbox-exemption marker, set by the Fabro sandbox's prepare
    step and already read by `CANONICAL_HOOK_BODY` in two places (the
    refuse-at-primary arm and the positive-location arm). Reading it here lets
    the pack-presence arm honour the same declaration rather than assert a
    property that cannot hold in a fresh, un-bootstrapped clone.

    Same three outcomes as `core_bare_is_true`. This one gates an EXEMPTION,
    so a failed read collapsing onto `False` was the SAFE direction — and
    still indistinguishable, which is what made it a defect rather than a
    preference.
    """
    return _git_config_is_true(
        probe="sandbox_exempt_is_true", cwd=cwd, key="livespec.sandboxExempt"
    )


def git_common_dir(*, cwd: Path) -> IOResult[Path, GitProbeFailed]:
    """The absolute path to the `.git` common directory for `cwd`.

    Uses `git rev-parse --git-common-dir`. The caller MUST have verified `cwd`
    is inside a git working tree first; a non-zero exit is therefore that
    precondition being false, and it now flows as a Failure rather than the
    `CalledProcessError` this function used to raise by design. The common dir
    is the primary's `.git/` (shared by secondary worktrees), so reading
    `<common-dir>/hooks/` against any worktree resolves to the primary's hooks
    directory.
    """
    return _git_stdout(probe="git_common_dir", cwd=cwd, args=["rev-parse", "--git-common-dir"]).map(
        lambda raw: _absolute_common_dir(cwd=cwd, raw=raw)
    )


def work_tree_root(*, cwd: Path) -> IOResult[Path, GitProbeFailed]:
    """The absolute path to the git work-tree root for `cwd`.

    Uses `git rev-parse --show-toplevel`. Same precondition and same
    converted `check=True` raise as `git_common_dir`. The work-tree root
    anchors the no-vendored-copy scan, so an unresolved one must not reach
    that scan as any path at all.
    """
    return _git_stdout(probe="work_tree_root", cwd=cwd, args=["rev-parse", "--show-toplevel"]).map(
        Path
    )
