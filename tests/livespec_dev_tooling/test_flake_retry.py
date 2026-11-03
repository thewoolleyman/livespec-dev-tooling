"""Integration coverage for the shipped untouched-test retry pytest plugin."""

from __future__ import annotations

import importlib
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_the_plugin_declares_the_bounded_single_test_retry_policy() -> None:
    """An untouched failure receives three retries, each one minute apart."""
    module_path = _REPO_ROOT / "livespec_dev_tooling" / "flake_retry.py"
    assert module_path.is_file(), "the flake-retry pytest plugin must be shipped"

    plugin = importlib.import_module("livespec_dev_tooling.flake_retry")

    assert plugin.RETRY_ATTEMPTS == 3
    assert plugin.RETRY_DELAY_SECONDS == 60
