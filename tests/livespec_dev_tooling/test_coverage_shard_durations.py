"""Regression coverage for the committed coverage-shard duration table."""

from __future__ import annotations

import subprocess
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TABLE = _REPO_ROOT / "scripts" / "just" / "coverage-shard-durations.tsv"


def test_the_committed_duration_table_lists_every_current_test_file() -> None:
    table_files = {
        line.split("\t", maxsplit=1)[0]
        for line in _TABLE.read_text(encoding="utf-8").splitlines()
        if line
    }
    tracked = subprocess.run(
        ["git", "ls-files", "tests/**"],
        cwd=_REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    suite_files = {
        path
        for path in tracked
        if path.endswith(".py")
        and (Path(path).name.startswith("test_") or Path(path).name.endswith("_test.py"))
    }

    assert suite_files <= table_files
