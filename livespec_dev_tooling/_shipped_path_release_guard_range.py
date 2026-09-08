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
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

__all__: list[str] = [
    "RANGE_BASE",
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


def _git_stdout(*, repo_root: Path, args: list[str]) -> str:
    # S603/S607: argv is a fixed list (literal git binary + literal flags and
    # shas this module itself produced); bare `git` resolves via PATH; no
    # untrusted shell input.
    result = subprocess.run(  # noqa: S603
        ["git", *args],  # noqa: S607
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def range_base_resolvable(*, repo_root: Path) -> bool:
    """Report whether `origin/master` resolves in this checkout.

    Asked BEFORE enumerating, because an unresolvable base makes the range
    UNDECIDABLE rather than clean — a shallow clone or a missing fetch would
    otherwise yield an empty commit list that reads exactly like "no violations".
    The caller turns a False here into a refusal, never into a pass.
    """
    # S603/S607: fixed argv as above. `check=False` because a non-zero exit IS
    # the answer being probed for, not an error to propagate.
    probe = subprocess.run(  # noqa: S603
        ["git", "rev-parse", "--verify", "--quiet", RANGE_BASE],  # noqa: S607
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=False,
    )
    return probe.returncode == 0


def commits_in_range(*, repo_root: Path) -> tuple[RangeCommit, ...]:
    """Every NON-MERGE commit in `origin/master..HEAD`, oldest first.

    Merge commits are skipped (`--no-merges`) for the reason the sibling range
    gate skips them: the fleet's protected branches enforce linear history, so a
    merge in the range carries no diff of its own and would contribute only its
    parents' paths a second time.

    Paths come from `git show --name-only` rather than `git diff-tree`, which
    reports NOTHING for a parentless commit — a root commit in the range would
    then read as touching no shipped path and pass on a technicality.
    """
    # `splitlines()` with NO emptiness filter, deliberately: `--format=` emits
    # the paths and nothing else (no leading blank line), and an empty range
    # yields `""`, whose `splitlines()` is already `[]`. A defensive `if
    # line.strip()` here would be a branch nothing can take — dead weight that
    # the 100%-coverage gate would correctly refuse to call covered.
    shas = _git_stdout(
        repo_root=repo_root, args=["rev-list", "--reverse", "--no-merges", f"{RANGE_BASE}..HEAD"]
    ).splitlines()
    return tuple(
        RangeCommit(
            sha=sha,
            message=_git_stdout(repo_root=repo_root, args=["log", "-1", "--format=%B", sha]),
            # splitlines(), never split(): a shipped path may contain a space.
            changed_paths=tuple(
                _git_stdout(
                    repo_root=repo_root,
                    args=["show", "--no-commit-id", "--name-only", "--format=", sha],
                ).splitlines()
            ),
        )
        for sha in shas
    )
