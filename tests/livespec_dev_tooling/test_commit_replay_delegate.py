"""Commit-time replay delegation decisions."""

from __future__ import annotations

from pathlib import Path

from livespec_dev_tooling.commit_replay_delegate import run_replay

__all__: list[str] = []


def test_an_absent_commit_replay_opt_in_runs_locally(*, tmp_path: Path) -> None:
    """A repository must explicitly opt in before a replay leg can delegate."""
    verdict = run_replay(repo_root=tmp_path, pytest_argv=["pytest", "tests/test_widget.py"])

    assert verdict.local is True
    assert verdict.reason == "delegated_commit_tests is not enabled"
