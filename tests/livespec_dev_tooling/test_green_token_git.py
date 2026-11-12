"""Unit tests for `livespec_dev_tooling/_green_token_git.py`."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from livespec_dev_tooling._green_token_git import (
    git_dir,
    head_tree_hash,
    repo_root,
    worktree_is_clean,
)

__all__: list[str] = []

_EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


def _scrub(*, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep a surrounding hook's git variables away from the fixture repository."""
    _ = [
        monkeypatch.delenv(key, raising=False)
        for key in [name for name in os.environ if name.startswith(("GIT_", "COVERAGE_", "COV_"))]
    ]


def test_the_reads_answer_for_a_fresh_repository(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The git dir, the empty HEAD tree, the top level, and clean then dirty."""
    _scrub(monkeypatch=monkeypatch)
    for args in (
        ("init", "-q"),
        ("-c", "user.email=t@t.t", "-c", "user.name=T", "commit", "-q", "--allow-empty", "-m", "x"),
    ):
        _ = subprocess.run(["git", *args], cwd=str(tmp_path), check=True)

    assert git_dir(cwd=tmp_path) == (tmp_path / ".git").resolve()
    assert head_tree_hash(cwd=tmp_path) == _EMPTY_TREE
    assert repo_root(cwd=tmp_path) == tmp_path.resolve()
    assert worktree_is_clean(cwd=tmp_path) is True
    _ = (tmp_path / "stray.txt").write_text("stray\n", encoding="utf-8")
    assert worktree_is_clean(cwd=tmp_path) is False


def test_a_read_outside_a_repository_raises(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unanswerable read raises, so each caller decides how to treat it."""
    _scrub(monkeypatch=monkeypatch)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))

    with pytest.raises(subprocess.CalledProcessError):
        _ = git_dir(cwd=tmp_path)
