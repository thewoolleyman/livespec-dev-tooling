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


def test_the_finalizer_preserver_declines_unrecognized_retry_state() -> None:
    """Private rerun state absent from an item must not be treated as retryable."""
    finalizers = importlib.import_module("livespec_dev_tooling.flake_retry_finalizers")

    assert not finalizers.RetryFinalizerPreserver._retry_is_pending(item=Mock())  # noqa: SLF001


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


def _setup_item(*, stack: dict[object, object]) -> SimpleNamespace:
    return SimpleNamespace(session=SimpleNamespace(_setupstate=SimpleNamespace(stack=stack)))


def _config_for(*, plugin: object, teardown_impl: SimpleNamespace) -> SimpleNamespace:
    others = SimpleNamespace(plugin=object(), function=Mock())
    hook = SimpleNamespace(
        pytest_runtest_teardown=SimpleNamespace(
            get_hookimpls=Mock(return_value=[others, teardown_impl])
        )
    )
    return SimpleNamespace(
        pluginmanager=SimpleNamespace(get_plugin=Mock(return_value=plugin), hook=hook)
    )


def test_the_upstream_teardown_hook_still_runs_and_only_its_stack_removals_are_undone() -> None:
    """rerunfailures keeps its own teardown work; only the dropped scope finalizers return."""
    finalizers = importlib.import_module("livespec_dev_tooling.flake_retry_finalizers")
    item = Mock()
    stack: dict[object, object] = {"session": ([], None), "module": ([], None), item: ([], None)}
    saved = dict(stack)
    item.session = SimpleNamespace(_setupstate=SimpleNamespace(stack=stack))
    calls: list[tuple[object, object]] = []

    def upstream(received: object, nextitem: object) -> None:
        calls.append((received, nextitem))
        for key in [key for key in stack if key is not item]:
            del stack[key]

    impl = SimpleNamespace(plugin=SimpleNamespace(), function=upstream)
    config = _config_for(plugin=impl.plugin, teardown_impl=impl)

    finalizers.preserve_finalizers(config=config)
    impl.function(item, "next")

    assert calls == [(item, "next")]
    assert list(stack.items()) == list(saved.items())


def test_the_upstream_setup_state_cleanup_still_runs_and_only_failed_nodes_stay_dropped() -> None:
    """Failures are cleared as upstream does, while healthy scope finalizers are re-attached."""
    finalizers = importlib.import_module("livespec_dev_tooling.flake_retry_finalizers")
    failure = RuntimeError("setup failed")
    stack: dict[object, object] = {
        "session": (["session-finalizer"], None),
        "module": (["module-finalizer"], failure),
        "class": (["class-finalizer"], None),
    }
    item = _setup_item(stack=stack)
    calls: list[object] = []

    def upstream(received: object) -> None:
        calls.append(received)
        item.session._setupstate.stack = {}  # noqa: SLF001

    plugin = SimpleNamespace(_remove_failed_setup_state_from_session=upstream)
    impl = SimpleNamespace(plugin=plugin, function=Mock())
    config = _config_for(plugin=plugin, teardown_impl=impl)

    finalizers.preserve_finalizers(config=config)
    plugin._remove_failed_setup_state_from_session(item)  # noqa: SLF001

    assert calls == [item]
    assert item.session._setupstate.stack == {"session": (["session-finalizer"], None)}  # noqa: SLF001


def test_the_wrapped_hooks_still_run_the_upstream_hook_without_pytest_setup_state() -> None:
    """Unexpected pytest internals leave the upstream hook running rather than crashing it."""
    finalizers = importlib.import_module("livespec_dev_tooling.flake_retry_finalizers")
    item = SimpleNamespace(session=SimpleNamespace())
    upstream = Mock()
    impl = SimpleNamespace(plugin=SimpleNamespace(), function=upstream)
    config = _config_for(plugin=impl.plugin, teardown_impl=impl)

    finalizers.preserve_finalizers(config=config)
    impl.function(item, None)

    upstream.assert_called_once_with(item, None)


def test_preserve_finalizers_tolerates_a_rerunfailures_without_the_setup_state_cleanup() -> None:
    """A rerunfailures build lacking the cleanup helper still gets its teardown hook wrapped."""
    finalizers = importlib.import_module("livespec_dev_tooling.flake_retry_finalizers")
    upstream = Mock()
    impl = SimpleNamespace(plugin=SimpleNamespace(), function=upstream)
    config = _config_for(plugin=impl.plugin, teardown_impl=impl)

    finalizers.preserve_finalizers(config=config)
    impl.function(_setup_item(stack={}), None)

    assert not hasattr(impl.plugin, "_remove_failed_setup_state_from_session")
    upstream.assert_called_once()
