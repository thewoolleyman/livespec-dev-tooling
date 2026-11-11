"""The git reads the green token and the pre-push evidence beside it are keyed on.

Each one raises `subprocess.CalledProcessError` when git cannot answer, so a
caller decides for itself whether an unanswerable read refuses or falls back.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

__all__: list[str] = ["git_dir", "head_tree_hash", "repo_root", "worktree_is_clean"]


def _git_stdout(*, cwd: Path, args: tuple[str, ...]) -> str:
    """Return one git command's stripped stdout, raising when it fails."""
    result = subprocess.run(  # noqa: S603
        ["git", *args],  # noqa: S607
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def git_dir(*, cwd: Path) -> Path:
    """Return the per-worktree git directory (always absolute path)."""
    return Path(_git_stdout(cwd=cwd, args=("rev-parse", "--absolute-git-dir")))


def head_tree_hash(*, cwd: Path) -> str:
    """Return the tree SHA of the current HEAD commit."""
    return _git_stdout(cwd=cwd, args=("rev-parse", "HEAD^{tree}"))


def worktree_is_clean(*, cwd: Path) -> bool:
    """Return True when the worktree has no uncommitted modifications."""
    return _git_stdout(cwd=cwd, args=("status", "--porcelain")) == ""


def repo_root(*, cwd: Path) -> Path:
    """Return the worktree's top level, where its `pyproject.toml` lives."""
    return Path(_git_stdout(cwd=cwd, args=("rev-parse", "--show-toplevel")))
