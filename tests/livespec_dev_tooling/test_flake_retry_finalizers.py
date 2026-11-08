"""Unit coverage for retaining pytest fixture finalizers across a retry."""

from __future__ import annotations

import importlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_the_finalizer_module_ships_one_live_mechanism() -> None:
    """Only the registered hook patch is exported; no unregistered competing mechanism remains."""
    finalizers = importlib.import_module("livespec_dev_tooling.flake_retry_finalizers")

    assert finalizers.__all__ == ["preserve_finalizers"]
    assert not hasattr(finalizers, "RetryFinalizerPreserver")


def test_preserve_finalizers_does_nothing_without_rerunfailures() -> None:
    """A consumer without pytest-rerunfailures keeps its native fixture lifecycle."""
    finalizers = importlib.import_module("livespec_dev_tooling.flake_retry_finalizers")
    config = SimpleNamespace(pluginmanager=SimpleNamespace(get_plugin=Mock(return_value=None)))

    finalizers.preserve_finalizers(config=config)

    config.pluginmanager.get_plugin.assert_called_once_with("rerunfailures")


def test_the_finalizer_module_satisfies_lint_without_suppression_comments() -> None:
    """The retry-plugin patch must pass the private-access check, not silence it."""
    module_path = _REPO_ROOT / "livespec_dev_tooling" / "flake_retry_finalizers.py"

    assert "noqa" not in module_path.read_text(encoding="utf-8")
