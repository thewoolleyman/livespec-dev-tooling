"""The change set the flake-retry decision rests on, read from git.

CI checks out one commit (`actions/checkout` at its default `fetch-depth: 1`).
That checkout has no parent of `HEAD`, so the change set has to bring in the one
commit it needs rather than read as unknown and retry nothing
(livespec-dev-tooling-bejgoo). An analysis that still fails means touched.
"""

from __future__ import annotations

from pathlib import Path

from livespec_dev_tooling.gate_remote_invocation import Failure, default_gate_command_runner

__all__: list[str] = ["change_paths"]


def _run_git(*, root: Path, args: list[str]) -> set[Path] | None:
    """Read one newline-delimited git path query, or report an unknown result."""
    invoked = default_gate_command_runner(argv=["git", *args], cwd=root)
    if isinstance(invoked, Failure):
        return None
    completed = invoked.unwrap()
    if completed.returncode != 0:
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


def _fetch_parent(*, repo_root: Path, head: str) -> None:
    """Deepen a shallow checkout by the one commit the change set compares against.

    A failed fetch is not reported here: the diff that needed the parent then
    fails too, and that is where an unknown change set is decided.
    """
    if _run_git(root=repo_root, args=["rev-parse", "--verify", "--quiet", "HEAD^"]) is None:
        _ = _run_git(root=repo_root, args=["fetch", "--quiet", "--deepen=1", "origin", head])


def change_paths(*, repo_root: Path) -> set[Path] | None:
    """Return committed, index, working-tree, and untracked changes."""
    remote = _default_branch_ref(repo_root=repo_root)
    if remote is None:
        return None
    base = _run_git(root=repo_root, args=["merge-base", "HEAD", remote])
    head = _run_git(root=repo_root, args=["rev-parse", "HEAD"])
    if base is None or head is None or len(base) != 1 or len(head) != 1:
        return None
    comparison = "HEAD^" if base == head else next(iter(base)).as_posix()
    if base == head:
        _fetch_parent(repo_root=repo_root, head=next(iter(head)).as_posix())
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
