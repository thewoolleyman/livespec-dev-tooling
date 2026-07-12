"""Mirror-paired test for `livespec_dev_tooling/checks/_primary_checkout_git_probes.py`.

The private sibling module carries the git rev-parse / git config
probes extracted from `primary_checkout_commit_refuse_hook_installed.py`
at the fleet-check-coverage LLOC-reduction split. The probes' end-to-end
coverage lives in `test_primary_checkout_commit_refuse_hook_installed.py`
(they are exercised outside-in through the parent check's subprocess
contract); THIS file unit-tests each probe directly against a real
tmp-path git repo, pinning the module boundary and both branches of
`git_common_dir` (relative common-dir at the repo root, absolute
common-dir from a linked worktree).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from livespec_dev_tooling.checks._primary_checkout_git_probes import (
    core_bare_is_true,
    git_common_dir,
    is_git_repo_at_all,
    is_inside_work_tree,
    work_tree_root,
)

__all__: list[str] = []


# Vars git sets when invoking hooks (lefthook pre-commit / pre-push).
# The probes' internal `git` subprocesses inherit the test process env;
# under a hook, GIT_DIR / GIT_INDEX_FILE would redirect those probes at
# the SURROUNDING repo instead of the tmp_path mini-repo.
_GIT_ENV_PASSTHROUGH_VARS: tuple[str, ...] = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_COMMON_DIR",
    "GIT_NAMESPACE",
    "GIT_LITERAL_PATHSPECS",
    "GIT_PREFIX",
)


@pytest.fixture(autouse=True)
def _scrub_git_hook_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in _GIT_ENV_PASSTHROUGH_VARS:
        monkeypatch.delenv(var, raising=False)


def _git(*, cwd: Path, args: list[str]) -> None:
    _ = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
        env={
            "HOME": str(cwd),
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_SYSTEM": "/dev/null",
            "PATH": "/usr/bin:/bin",
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@example.com",
        },
    )


def _make_repo(*, tmp_path: Path) -> Path:
    """Initialize a normal work-tree repo at `tmp_path/repo` with one commit."""
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    _git(cwd=repo, args=["init", "--quiet", "-b", "work"])
    _git(cwd=repo, args=["commit", "--quiet", "--allow-empty", "-m", "seed"])
    return repo


def test_is_git_repo_at_all_true_in_repo_false_outside(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path=tmp_path)
    plain = tmp_path / "plain"
    plain.mkdir()
    assert is_git_repo_at_all(cwd=repo) is True
    assert is_git_repo_at_all(cwd=plain) is False


def test_is_inside_work_tree_true_in_repo_false_in_git_dir(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path=tmp_path)
    assert is_inside_work_tree(cwd=repo) is True
    # Inside the `.git` directory is a git context that is NOT a work tree.
    assert is_inside_work_tree(cwd=repo / ".git") is False


def test_core_bare_is_true_false_for_normal_repo_true_for_bare(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path=tmp_path)
    assert core_bare_is_true(cwd=repo) is False
    bare = tmp_path / "bare.git"
    bare.mkdir()
    _git(cwd=bare, args=["init", "--bare", "--quiet"])
    assert core_bare_is_true(cwd=bare) is True


def test_git_common_dir_relative_from_repo_root(tmp_path: Path) -> None:
    """From the repo root `git --git-common-dir` is relative (`.git`) → resolved branch."""
    repo = _make_repo(tmp_path=tmp_path)
    result = git_common_dir(cwd=repo)
    assert result == (repo / ".git").resolve()
    assert result.is_absolute()
    assert result.is_dir()


def test_git_common_dir_absolute_from_linked_worktree(tmp_path: Path) -> None:
    """From a linked worktree `git --git-common-dir` is absolute → returned verbatim."""
    repo = _make_repo(tmp_path=tmp_path)
    linked = tmp_path / "linked"
    _git(cwd=repo, args=["worktree", "add", "--quiet", str(linked), "-b", "wt"])
    result = git_common_dir(cwd=linked)
    assert result.is_absolute()
    assert result.name == ".git"
    assert result.is_dir()


def test_work_tree_root_returns_toplevel(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path=tmp_path)
    result = work_tree_root(cwd=repo)
    assert result.is_dir()
    assert (result / ".git").exists()
    assert result.name == "repo"
