"""Commit-time replay delegation seam."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

__all__: list[str] = ["ReplayVerdict", "run_replay"]


@dataclass(frozen=True, kw_only=True)
class ReplayVerdict:
    """The location and result of one replay leg."""

    local: bool
    reason: str


def run_replay(*, repo_root: Path, pytest_argv: list[str]) -> ReplayVerdict:
    """Decide how the replay leg should run."""
    _ = (repo_root, pytest_argv)
    return ReplayVerdict(local=True, reason="delegated_commit_tests is not enabled")
