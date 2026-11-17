"""A pull request's merge commit that its origin no longer advertises still resolves its change set.

`actions/checkout` fetches a pull request's merge commit at depth 1, and a shard job reaches the
flake-retry plugin minutes later. By then GitHub may have recomputed `refs/pull/N/merge` (the base
moved on, or the PR closed), so the commit the job holds is no longer the tip of any ref. Against
such an origin `git fetch --deepen=1 origin <sha>` exits 0 and deepens nothing, `HEAD^2` stays
missing, and the plugin withheld every retry of the session (livespec-dev-tooling-7tqp32: 32 of 208
orchestrator shard jobs on v1.216.0 or later).
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


def _commit(*, repo: Path, name: str, text: str, message: str) -> None:
    _ = (repo / name).write_text(text, encoding="utf-8")
    _git(repo=repo, args=["add", "-A"])
    _git(repo=repo, args=["commit", "-qm", message])


def _origin_that_stopped_advertising_the_merge(*, root: Path) -> tuple[Path, str]:
    """An origin holding the merge commit as an object, with no ref left that reaches it."""
    origin = root / "origin"
    origin.mkdir()
    _git(repo=origin, args=["init", "-q", "-b", "master", "."])
    _commit(repo=origin, name="app.py", text="VALUE = 1\n", message="base")
    _git(repo=origin, args=["checkout", "-q", "-b", "feature"])
    _commit(repo=origin, name="app.py", text="VALUE = 2\n", message="the pr")
    _git(repo=origin, args=["checkout", "-q", "master"])
    _commit(repo=origin, name="elsewhere.py", text="Y = 1\n", message="master moved on")
    _git(repo=origin, args=["checkout", "-q", "-b", "merge-ref"])
    _git(repo=origin, args=["merge", "-q", "--no-ff", "-m", "merge", "feature"])
    sha = _git(repo=origin, args=["rev-parse", "HEAD"])
    _git(repo=origin, args=["update-ref", "refs/pull/1/merge", sha])
    return origin, sha


def _depth_one_checkout(*, work: Path, origin: Path, sha: str) -> Path:
    """Reproduce `actions/checkout` on a pull request's merge ref at `fetch-depth: 1`."""
    work.mkdir()
    _git(repo=work, args=["init", "-q", "."])
    _git(repo=work, args=["remote", "add", "origin", origin.as_uri()])
    _git(
        repo=work, args=["fetch", "-q", "--depth=1", "origin", f"+{sha}:refs/remotes/pull/1/merge"]
    )
    _git(repo=work, args=["checkout", "-q", "--force", "-B", "master", "refs/remotes/pull/1/merge"])
    return work


def test_a_merge_commit_the_origin_no_longer_advertises_still_yields_the_change_set(
    *, tmp_path: Path
) -> None:
    """The merge ref moves away after checkout, so the plugin's fetch targets an unreachable sha."""
    changes = importlib.import_module("livespec_dev_tooling.flake_retry_changes")
    origin, sha = _origin_that_stopped_advertising_the_merge(root=tmp_path)
    work = _depth_one_checkout(work=tmp_path / "work", origin=origin, sha=sha)
    _git(repo=origin, args=["update-ref", "-d", "refs/pull/1/merge"])
    _git(repo=origin, args=["checkout", "-q", "master"])
    _git(repo=origin, args=["branch", "-q", "-D", "merge-ref"])

    resolved = changes.change_paths(repo_root=work)

    assert resolved == {Path("app.py")}
