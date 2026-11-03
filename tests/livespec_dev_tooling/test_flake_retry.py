"""Integration coverage for the shipped untouched-test retry pytest plugin."""

from __future__ import annotations

import importlib
import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_the_plugin_declares_the_bounded_single_test_retry_policy() -> None:
    """An untouched failure receives three retries, each one minute apart."""
    module_path = _REPO_ROOT / "livespec_dev_tooling" / "flake_retry.py"
    assert module_path.is_file(), "the flake-retry pytest plugin must be shipped"

    plugin = importlib.import_module("livespec_dev_tooling.flake_retry")

    assert plugin.RETRY_ATTEMPTS == 3
    assert plugin.RETRY_DELAY_SECONDS == 60


def test_pytest_loads_the_plugin_from_the_shared_entry_point() -> None:
    """Consumers receive the retry policy without per-repository conftest wiring."""
    pyproject = (_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")

    pytest11 = re.search(
        r"^\[project\.entry-points\.pytest11\]$(?P<body>.*?)(?=^\[|\Z)",
        pyproject,
        re.MULTILINE | re.DOTALL,
    )

    assert pytest11 is not None
    assert 'livespec_flake_retry = "livespec_dev_tooling.flake_retry"' in pytest11.group("body")
