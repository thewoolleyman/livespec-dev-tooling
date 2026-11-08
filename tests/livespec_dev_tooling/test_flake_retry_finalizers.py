"""Unit coverage for retaining pytest fixture finalizers across a retry."""

from __future__ import annotations

import importlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_the_finalizer_preserver_restores_only_the_stack_entries_removed_for_a_retry() -> None:
    """The retry keeps higher-scope finalizers and leaves the rerun item's entry intact."""
    module_path = _REPO_ROOT / "livespec_dev_tooling" / "flake_retry_finalizers.py"
    assert module_path.is_file(), "the finalizer preserver must be shipped beside the retry plugin"

    finalizers = importlib.import_module("livespec_dev_tooling.flake_retry_finalizers")
    preserver = finalizers.RetryFinalizerPreserver()
    item = Mock()
    scope_node = object()
    rerun_node = object()
    stack = {scope_node: "scope-finalizers", item: "item-finalizers"}
    item.session = SimpleNamespace(_setupstate=SimpleNamespace(stack=stack))
    item.get_closest_marker.return_value = SimpleNamespace(kwargs={"reruns": 1})
    item.execution_count = 1
    vars(item).update(
        {
            "_test_failed_statuses": {"call": True},
            "_terminal_errors": {"call": False},
        }
    )

    protocol = preserver.protocol(item=item, nextitem=None)
    next(protocol)
    teardown = preserver.teardown(item=item, nextitem=None)
    next(teardown)
    stack.clear()
    stack[rerun_node] = "rerun-finalizers"
    with pytest.raises(StopIteration):
        next(teardown)
    with pytest.raises(StopIteration):
        next(protocol)

    assert stack == {
        scope_node: "scope-finalizers",
        rerun_node: "rerun-finalizers",
    }


def test_the_finalizer_preserver_ignores_an_item_without_pytest_setup_state() -> None:
    """Unexpected pytest internals leave the retry alone rather than crashing it."""
    module_path = _REPO_ROOT / "livespec_dev_tooling" / "flake_retry_finalizers.py"
    assert module_path.is_file(), "the finalizer preserver must be shipped beside the retry plugin"

    finalizers = importlib.import_module("livespec_dev_tooling.flake_retry_finalizers")
    preserver = finalizers.RetryFinalizerPreserver()
    item = Mock(session=SimpleNamespace())

    teardown = preserver.teardown(item=item, nextitem=None)
    next(teardown)
    with pytest.raises(StopIteration):
        next(teardown)
