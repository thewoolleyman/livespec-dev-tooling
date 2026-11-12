"""Tests for the packaged cross-repository public API declaration inventory."""

from __future__ import annotations

import importlib
from pathlib import Path

__all__: list[str] = []


def test_checker_module_exists_and_accepts_the_committed_inventory() -> None:
    path = Path(__file__).resolve().parents[3] / (
        "livespec_dev_tooling/checks/cross_repo_public_api_package_data.py"
    )
    assert path.is_file()
    module = importlib.import_module(
        "livespec_dev_tooling.checks.cross_repo_public_api_package_data"
    )
    assert module.main() == 0
