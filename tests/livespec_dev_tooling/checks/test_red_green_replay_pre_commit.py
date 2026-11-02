"""Mirror-paired tests for same-tree pre-commit suite evidence helpers."""

from __future__ import annotations

from pathlib import Path
from subprocess import CompletedProcess

import pytest

from livespec_dev_tooling.checks import _red_green_replay_pre_commit as pre_commit

__all__: list[str] = []


def test_staged_tree_hash_reads_the_index_or_refuses_to_guess(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An unreadable index never substitutes stale evidence for a suite run."""

    def write_tree(*args: object, **kwargs: object) -> CompletedProcess[str]:
        _ = args, kwargs
        return CompletedProcess(args=["git", "write-tree"], returncode=0, stdout="same-tree\n")

    def unavailable(*args: object, **kwargs: object) -> CompletedProcess[str]:
        _ = args, kwargs
        raise OSError("git unavailable")

    monkeypatch.setattr(pre_commit.subprocess, "run", write_tree)
    assert pre_commit.staged_tree_hash(cwd=tmp_path) == "same-tree"
    monkeypatch.setattr(pre_commit.subprocess, "run", unavailable)
    assert pre_commit.staged_tree_hash(cwd=tmp_path) is None
