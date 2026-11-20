"""A rebase-queue commit computes its change set without a local default ref.

GitHub checks a merge-group rebase result out at depth one.  That commit has one
parent and is not a pull-request merge commit, but the default branch remains
available from origin and supplies the merge-base (livespec-dev-tooling-jkxym2).
"""

from __future__ import annotations

import importlib
import subprocess
from pathlib import Path

_GIT_IDENTITY = ("-c", "user.email=flake@example.invalid", "-c", "user.name=flake")


def _git(*, repo: Path, args: list[str]) -> str:
    completed = subprocess.run(
        ["git", *_GIT_IDENTITY, *args], cwd=repo, check=True, capture_output=True, text=True
    )
    return completed.stdout.strip()


def _commit(*, repo: Path, files: dict[str, str], message: str) -> str:
    for name, text in files.items():
        _ = (repo / name).write_text(text, encoding="utf-8")
    _git(repo=repo, args=["add", "-A"])
    _git(repo=repo, args=["commit", "-qm", message])
    return _git(repo=repo, args=["rev-parse", "HEAD"])


def _depth_one_rebase_queue_checkout(*, root: Path) -> tuple[Path, str]:
    """Create a one-parent queue commit without an ``origin/master`` ref locally."""
    origin = root / "origin"
    origin.mkdir()
    _git(repo=origin, args=["init", "-q", "-b", "master", "."])
    base = _commit(repo=origin, files={"app.py": "VALUE = 1\n"}, message="base")
    _git(repo=origin, args=["checkout", "-q", "-b", "rebase-queue"])
    queued = _commit(
        repo=origin,
        files={"app.py": "VALUE = 2\n", "queue.py": "QUEUED = True\n"},
        message="queue result",
    )
    _git(repo=origin, args=["checkout", "-q", "master"])
    _ = _commit(repo=origin, files={"default.py": "DEFAULT = True\n"}, message="master moved")

    work = root / "work"
    work.mkdir()
    _git(repo=work, args=["init", "-q", "."])
    _git(repo=work, args=["remote", "add", "origin", origin.as_uri()])
    _git(
        repo=work,
        args=[
            "fetch",
            "-q",
            "--depth=1",
            "origin",
            f"+{queued}:refs/remotes/gh-read-only-queue/master/pr-1-{queued}",
        ],
    )
    _git(repo=work, args=["checkout", "-q", "--force", "-B", "master", "FETCH_HEAD"])
    return work, base


def test_a_depth_one_one_parent_rebase_queue_checkout_uses_the_fetched_default_branch_merge_base(
    *, tmp_path: Path
) -> None:
    """A queue commit's parent is not assumed to be the default branch base."""
    changes = importlib.import_module("livespec_dev_tooling.flake_retry_changes")
    work, base = _depth_one_rebase_queue_checkout(root=tmp_path)

    assert changes.comparison_revision(repo_root=work) == base
    assert changes.change_paths(repo_root=work) == {Path("app.py"), Path("queue.py")}
