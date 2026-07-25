"""Shared fixtures for check subprocess tests."""

from __future__ import annotations

from pathlib import Path

import pytest

__all__: list[str] = []

_LEGACY_LAYOUT_BLOCK = """[tool.livespec_dev_tooling]
source_trees = [".claude-plugin/scripts/livespec"]
io_trees = [".claude-plugin/scripts/livespec/io"]
commands_trees = [".claude-plugin/scripts/livespec/commands"]
supervisor_entry_files = [
    ".claude-plugin/scripts/livespec/doctor/run_static.py",
    ".claude-plugin/scripts/bin/_bootstrap.py",
]
dataclasses_tree = ".claude-plugin/scripts/livespec/schemas/dataclasses"
pure_trees = [
    ".claude-plugin/scripts/livespec/parse",
    ".claude-plugin/scripts/livespec/validate",
]
covered_trees = [
    ".claude-plugin/scripts/livespec",
    ".claude-plugin/scripts/bin",
    "dev-tooling",
]
source_tree_prefixes = [
    ".claude-plugin/scripts/livespec/",
    ".claude-plugin/scripts/bin/",
    "dev-tooling/checks/",
]
target_dirs = [".claude-plugin/scripts", "dev-tooling", "tests"]
neutral_hook_body_path = ""
mirror_pairings = [
    { source_tree = ".claude-plugin/scripts/livespec", test_tree = "tests/livespec" },
    { source_tree = ".claude-plugin/scripts/bin", test_tree = "tests/bin" },
    { source_tree = "dev-tooling/checks", test_tree = "tests/dev-tooling/checks" },
    { source_tree = "livespec_dev_tooling/checks", test_tree = "tests/livespec_dev_tooling/checks" },
]
"""


@pytest.fixture
def tmp_path(*, tmp_path_factory: pytest.TempPathFactory) -> Path:
    repo_root = tmp_path_factory.mktemp("repo")
    (repo_root / "pyproject.toml").write_text(_LEGACY_LAYOUT_BLOCK, encoding="utf-8")
    return repo_root
