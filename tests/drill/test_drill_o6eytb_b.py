"""Throwaway semantic-conflict drill (livespec-dev-tooling-o6eytb); removed by the cleanup PR."""

from __future__ import annotations

from pathlib import Path


def test_drill_directory_holds_exactly_one_data_file() -> None:
    """Passes alone; fails once a second drill data file lands beside it."""
    data_files = sorted(p.name for p in Path(__file__).parent.iterdir() if p.suffix == ".txt")
    assert len(data_files) == 1, data_files
