"""The change set the flake-retry decision rests on, read from git.

CI checks out one commit (`actions/checkout` at its default `fetch-depth: 1`).
That checkout has no parent of `HEAD`, so the change set has to bring in the one
commit it needs rather than read as unknown and retry nothing
(livespec-dev-tooling-bejgoo). An analysis that still fails means touched.

Every pytest-xdist worker computes this during collection, so the fetch runs under a
file lock: concurrent fetches collide on git's shallow lock, and the loser would read
the parent as missing (livespec-dev-tooling-xfe2po).
"""

from __future__ import annotations

import fcntl
from pathlib import Path

from livespec_dev_tooling.gate_remote_invocation import Failure, default_gate_command_runner

__all__: list[str] = ["change_paths", "withheld_reason"]

_FETCH_LOCK_NAME = "livespec-flake-retry-fetch.lock"
_LAST_FAILURE: list[str] = []
_FAILED_FETCH: list[str] = []


def withheld_reason() -> str:
    """Name the failed fetch, if any, then the last git query that failed."""
    return ", then ".join([*_FAILED_FETCH, _LAST_FAILURE[0]])


def _record_failure(*, args: list[str], detail: str) -> None:
    _LAST_FAILURE[:] = [f"`git {' '.join(args)}` failed ({detail})"]


def _run_git(*, root: Path, args: list[str]) -> set[Path] | None:
    """Read one newline-delimited git path query, or report an unknown result."""
    invoked = default_gate_command_runner(argv=["git", *args], cwd=root)
    if isinstance(invoked, Failure):
        _record_failure(args=args, detail=invoked.failure().detail)
        return None
    completed = invoked.unwrap()
    if completed.returncode != 0:
        lines = completed.stderr.strip().splitlines()
        detail = f"exit {completed.returncode}"
        _record_failure(args=args, detail=f"{detail}: {lines[0]}" if lines else detail)
        return None
    return {Path(line) for line in completed.stdout.splitlines() if line}


def _default_branch_ref(*, repo_root: Path) -> str | None:
    """Name the remote default branch, or report that it cannot be known.

    `origin/HEAD` is the authority when it is set. A CI checkout usually does
    not set it, so the conventional `origin/main` and `origin/master` are tried
    next, and a repository with neither has no computable change set.
    """
    default = _run_git(root=repo_root, args=["symbolic-ref", "--short", "refs/remotes/origin/HEAD"])
    if default is not None and len(default) == 1:
        return next(iter(default)).as_posix()
    for candidate in ("origin/main", "origin/master"):
        if (
            _run_git(root=repo_root, args=["rev-parse", "--verify", "--quiet", candidate])
            is not None
        ):
            return candidate
    return None


def _deepen_if_parent_missing(*, repo_root: Path, head: str) -> None:
    """Fetch the parent when it is absent, keeping a failure for the withheld reason."""
    if (
        _run_git(root=repo_root, args=["rev-parse", "--verify", "--quiet", "HEAD^"]) is None
        and _run_git(root=repo_root, args=["fetch", "--quiet", "--deepen=1", "origin", head])
        is None
    ):
        _FAILED_FETCH[:] = _LAST_FAILURE


def _fetch_parent(*, repo_root: Path, head: str) -> None:
    """Deepen a shallow checkout by the one commit the change set compares against.

    One worker at a time checks and fetches, so a later worker finds the parent
    already there. A failed fetch does not decide anything here: the query that
    needed the parent then fails too, and that is where an unknown change set is
    decided. A lock that cannot be taken falls back to fetching without it.
    """
    try:
        with (repo_root / ".git" / _FETCH_LOCK_NAME).open("a", encoding="utf-8") as held:
            fcntl.flock(held, fcntl.LOCK_EX)
            _deepen_if_parent_missing(repo_root=repo_root, head=head)
            return
    except OSError:
        pass
    _deepen_if_parent_missing(repo_root=repo_root, head=head)


def _comparison(*, repo_root: Path) -> str | None:
    """Name the revision the change set is measured from, or report it unknown.

    With a default-branch ref that is the merge-base, or `HEAD`'s parent on the
    default branch itself. Without one, a pull-request checkout is the merge
    commit GitHub builds, whose first parent is the base tip; any other lone
    commit has nothing to be measured against.
    """
    head = _run_git(root=repo_root, args=["rev-parse", "HEAD"])
    if head is None or len(head) != 1:
        return None
    sha = next(iter(head)).as_posix()
    remote = _default_branch_ref(repo_root=repo_root)
    if remote is None:
        _fetch_parent(repo_root=repo_root, head=sha)
        merged = _run_git(root=repo_root, args=["rev-parse", "--verify", "--quiet", "HEAD^2"])
        return None if merged is None else "HEAD^1"
    base = _run_git(root=repo_root, args=["merge-base", "HEAD", remote])
    if base is None or len(base) != 1:
        return None
    if base == head:
        _fetch_parent(repo_root=repo_root, head=sha)
        return "HEAD^"
    return next(iter(base)).as_posix()


def change_paths(*, repo_root: Path) -> set[Path] | None:
    """Return committed, index, working-tree, and untracked changes."""
    _LAST_FAILURE[:] = ["no git query failed, yet HEAD or its base did not resolve to one commit"]
    _FAILED_FETCH.clear()
    comparison = _comparison(repo_root=repo_root)
    if comparison is None:
        return None
    queries: tuple[list[str], ...] = (
        ["diff", "--name-only", comparison, "HEAD"],
        ["diff", "--name-only", "--cached"],
        ["diff", "--name-only"],
        ["ls-files", "--others", "--exclude-standard"],
    )
    changed: set[Path] = set()
    for query in queries:
        result = _run_git(root=repo_root, args=query)
        if result is None:
            return None
        changed.update(result)
    return changed
