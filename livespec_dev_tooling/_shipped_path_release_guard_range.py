"""_shipped_path_release_guard_range — enumerate `origin/master..HEAD` for the guard.

Slice C of the R6 guard (work-item `livespec-dev-tooling-sxdz`). A private
sibling of `shipped_path_release_guard_check`, split off for COHESION: this
module is the git-range BOUNDARY and nothing else. It answers "which commits are
in the range, and for each, what did the author write and what did they touch" —
and it answers nothing about whether any of that is a violation.

⛔ NO PART OF THE RULE LIVES HERE. The decision stays in
`shipped_path_release_guard_core` and the policy (the override trailer's
spelling, the remedy text, the per-repo resolution) stays in the check module
that imports this one. That is not an arbitrary boundary: a range loop is
exactly where a second copy of the rule would be cheapest to write — a
`startswith` over `changed_paths` right here would look local and correct and
would silently defeat the A/B split. This module therefore returns DATA, and the
check module decides over it with the same core call the commit-msg path uses.

The direction of the import is what enforces that: this module imports neither
the core nor the check, so it has nothing to decide WITH.

ON THE `IOResult` RAILWAY (`livespec-dev-tooling-qndn.2`, epic `8o8e`). Both
public readers invoke `git` DIRECTLY rather than through an injected seam, so
they are the I/O boundary itself and `IOResult` rather than `Result` is the
honest container. The failure track carries a git command that DID NOT ANSWER —
see `RangeCommandFailed` for why that can never be spelled as a short range.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# Carried rather than inherited from an importer: a bare `from returns...`
# import resolves only if some module up the chain happens to have inserted
# `_vendor/` already, which is a property of the caller rather than of this
# module.
_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.io import IOFailure, IOResult, IOSuccess  # noqa: E402  — vendor-path-aware.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware.

__all__: list[str] = [
    "RANGE_BASE",
    "RangeCommandFailed",
    "RangeCommit",
    "commits_in_range",
    "range_base_resolvable",
]


# The branch-level gate's base, matching `checks/red_green_replay.py`'s
# `_RANGE_BASE`. On `master` itself the range is empty and the gate passes
# trivially, which is correct: those commits were already judged on the way in.
RANGE_BASE = "origin/master"


@dataclass(frozen=True, kw_only=True)
class RangeCommit:
    """One commit in the range: its sha, its RAW message, and the paths it changed.

    The message is carried raw rather than pre-split into subject and body so the
    check module can apply the SAME `_split_message` and the SAME override-trailer
    match it applies to a pending commit's message file. Two parsers for one
    message format is how the two modes drift apart.
    """

    sha: str
    message: str
    changed_paths: tuple[str, ...]


@dataclass(frozen=True, kw_only=True)
class RangeCommandFailed:
    """A git command that DID NOT ANSWER, and which one.

    ⛔ NOT "the range is empty". This module's own header records why the two
    must never share a spelling: an empty commit list is indistinguishable from a
    clean branch, so a git that never ran — or ran and failed — has to leave the
    range UNKNOWN rather than short. A partial enumeration is the same defect
    wearing a longer list: its dropped commits would read as judged and clean.

    `argv` is the command as invoked, so an operator can rerun exactly it;
    `detail` carries the exit status and stderr, or the reason the process never
    started at all.
    """

    argv: str
    detail: str


def _argv(*, args: list[str]) -> str:
    """The invocation as a single rerunnable string, for the failure track."""
    return " ".join(["git", *args])


def _git_run(
    *, repo_root: Path, args: list[str]
) -> IOResult[subprocess.CompletedProcess[str], RangeCommandFailed]:
    """Invoke one git command, separating a git that never RAN from one that answered.

    The catch is NARROW and ENUMERATED (`OSError`) — git absent from PATH, a git
    that cannot be exec'd, a fork failure — which is the sanctioned hand-rolled
    seam lift; a bug raised in here still propagates. `check=False` throughout,
    because the exit status means different things to this module's two readers
    and only the CALLER knows which: for the base probe a non-zero exit is the
    ANSWER, and for the enumeration it is a failure.
    """
    # S603/S607: argv is a fixed list (literal git binary + literal flags and
    # shas this module itself produced); bare `git` resolves via PATH; no
    # untrusted shell input.
    try:
        return IOSuccess(
            subprocess.run(  # noqa: S603
                ["git", *args],  # noqa: S607
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                check=False,
            )
        )
    except OSError as never_ran:
        return IOFailure(RangeCommandFailed(argv=_argv(args=args), detail=str(never_ran)))


def _git_stdout(*, repo_root: Path, args: list[str]) -> IOResult[str, RangeCommandFailed]:
    """One git command's stdout, or WHY the range stays unknown.

    A NON-ZERO exit is a FAILURE here — unlike in `range_base_resolvable`, where
    it is the answer being asked for. These commands are issued only AFTER the
    base has been established as resolvable, so a non-zero exit contradicts the
    precondition the caller already checked, and its empty stdout would enumerate
    as a shorter range rather than as no range at all.
    """
    ran = _git_run(repo_root=repo_root, args=args)
    if isinstance(ran, IOFailure):
        return ran
    result = unsafe_perform_io(ran.unwrap())
    if result.returncode != 0:
        return IOFailure(
            RangeCommandFailed(
                argv=_argv(args=args),
                detail=f"exit {result.returncode}: {result.stderr.strip()}",
            )
        )
    return IOSuccess(result.stdout)


def range_base_resolvable(*, repo_root: Path) -> IOResult[bool, RangeCommandFailed]:
    """Report whether `origin/master` resolves in this checkout.

    Asked BEFORE enumerating, because an unresolvable base makes the range
    UNDECIDABLE rather than clean — a shallow clone or a missing fetch would
    otherwise yield an empty commit list that reads exactly like "no violations".
    The caller turns a False here into a refusal, never into a pass.

    ⛔ THAT `False` STAYS ON THE SUCCESS TRACK: a non-zero exit IS the answer this
    probe asks for, not an error to propagate. A git that never RAN is the other
    track because the two want different remedies — "fetch the base ref" is
    useless advice to a checkout whose git could not be executed at all.
    """
    probed = _git_run(repo_root=repo_root, args=["rev-parse", "--verify", "--quiet", RANGE_BASE])
    if isinstance(probed, IOFailure):
        return probed
    return IOSuccess(unsafe_perform_io(probed.unwrap()).returncode == 0)


def _described(*, repo_root: Path, sha: str) -> IOResult[RangeCommit, RangeCommandFailed]:
    """One commit's RAW message and the paths it changed.

    Paths come from `git show --name-only` rather than `git diff-tree`, which
    reports NOTHING for a parentless commit — a root commit in the range would
    then read as touching no shipped path and pass on a technicality.
    """
    message = _git_stdout(repo_root=repo_root, args=["log", "-1", "--format=%B", sha])
    if isinstance(message, IOFailure):
        return message
    changed = _git_stdout(
        repo_root=repo_root, args=["show", "--no-commit-id", "--name-only", "--format=", sha]
    )
    if isinstance(changed, IOFailure):
        return changed
    return IOSuccess(
        RangeCommit(
            sha=sha,
            message=unsafe_perform_io(message.unwrap()),
            # splitlines(), never split(): a shipped path may contain a space.
            changed_paths=tuple(unsafe_perform_io(changed.unwrap()).splitlines()),
        )
    )


def commits_in_range(*, repo_root: Path) -> IOResult[tuple[RangeCommit, ...], RangeCommandFailed]:
    """Every NON-MERGE commit in `origin/master..HEAD`, oldest first.

    Merge commits are skipped (`--no-merges`) for the reason the sibling range
    gate skips them: the fleet's protected branches enforce linear history, so a
    merge in the range carries no diff of its own and would contribute only its
    parents' paths a second time.

    ⛔ THE FIRST git command that stops answering ENDS the enumeration on the
    failure track, and the commits already described are DISCARDED with it. A
    partial list would be reported as the whole range, so its dropped commits
    would read as judged and clean — the one outcome an enumerating gate must
    never produce.
    """
    # `splitlines()` with NO emptiness filter, deliberately: `--format=` emits
    # the paths and nothing else (no leading blank line), and an empty range
    # yields `""`, whose `splitlines()` is already `[]`. A defensive `if
    # line.strip()` here would be a branch nothing can take — dead weight that
    # the 100%-coverage gate would correctly refuse to call covered.
    listed = _git_stdout(
        repo_root=repo_root, args=["rev-list", "--reverse", "--no-merges", f"{RANGE_BASE}..HEAD"]
    )
    if isinstance(listed, IOFailure):
        return listed
    commits: list[RangeCommit] = []
    for sha in unsafe_perform_io(listed.unwrap()).splitlines():
        described = _described(repo_root=repo_root, sha=sha)
        if isinstance(described, IOFailure):
            return described
        commits.append(unsafe_perform_io(described.unwrap()))
    return IOSuccess(tuple(commits))
