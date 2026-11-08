"""Preserve higher-scope pytest fixture finalizers while a test is retried."""

from __future__ import annotations

from collections.abc import Generator
from typing import cast

import pytest

__all__: list[str] = ["RetryFinalizerPreserver", "preserve_finalizers"]


def _keep_setup_state(*_: object) -> None:
    """Let pytest's normal teardown keep scope finalizers until their owner closes."""


def preserve_finalizers(*, config: pytest.Config) -> None:
    """Prevent rerunfailures from dropping higher-scope finalizers for a retry."""
    rerunfailures = config.pluginmanager.get_plugin("rerunfailures")
    if rerunfailures is None:
        return
    for hookimpl in config.pluginmanager.hook.pytest_runtest_teardown.get_hookimpls():
        if hookimpl.plugin is rerunfailures:
            object.__setattr__(hookimpl, "function", _keep_setup_state)
    object.__setattr__(rerunfailures, "_remove_failed_setup_state_from_session", _keep_setup_state)


class RetryFinalizerPreserver:
    """Keep finalizer-owning setup nodes alive across rerunfailures' teardown."""

    @staticmethod
    def _setup_stack(*, item: pytest.Item) -> dict[object, object] | None:
        """Return pytest's setup-state stack without depending on its private types."""
        session_attributes = cast(dict[str, object], vars(item.session))
        setup_state = session_attributes.get("_setupstate")
        if setup_state is None:
            return None
        setup_state_attributes = cast(dict[str, object], vars(setup_state))
        stack = setup_state_attributes.get("stack")
        return cast(dict[object, object], stack) if isinstance(stack, dict) else None

    @staticmethod
    def _retry_is_pending(*, item: pytest.Item) -> bool:
        """Match rerunfailures' retry decision for this plugin's `flaky` marker."""
        marker = item.get_closest_marker("flaky")
        reruns = None if marker is None else marker.kwargs.get("reruns")
        execution_count = vars(item).get("execution_count")
        failed_statuses = vars(item).get("_test_failed_statuses")
        terminal_errors = vars(item).get("_terminal_errors")
        if not (
            isinstance(reruns, int)
            and isinstance(execution_count, int)
            and isinstance(failed_statuses, dict)
            and isinstance(terminal_errors, dict)
        ):
            return False
        failed = cast(dict[object, object], failed_statuses)
        terminal = cast(dict[object, object], terminal_errors)
        return execution_count <= reruns and any(failed.values()) and not any(terminal.values())

    @pytest.hookimpl(hookwrapper=True, tryfirst=True)
    def teardown(
        self, *, item: pytest.Item, nextitem: pytest.Item | None
    ) -> Generator[None, None, None]:
        """Restore finalizer-owning nodes before pytest chooses the following item."""
        del nextitem
        stack = self._setup_stack(item=item)
        saved_stack = None if stack is None else stack.copy()
        yield
        if stack is None or saved_stack is None or not self._retry_is_pending(item=item):
            return
        restored_stack = {key: value for key, value in saved_stack.items() if key is not item}
        restored_stack.update(stack)
        stack.clear()
        stack.update(restored_stack)

    @pytest.hookimpl(hookwrapper=True, tryfirst=True)
    def protocol(
        self, *, item: pytest.Item, nextitem: pytest.Item | None
    ) -> Generator[None, None, None]:
        """Remain a wrapper so existing plugin ordering stays stable."""
        del item, nextitem
        yield


# PYTEST CALLS ITS HOOKS POSITIONALLY. pluggy reads a hook's argument names off
# its signature and passes them by position, so a keyword-only hook receives
# nothing, and a `*args` hook receives nothing either. These adapters preserve
# the public hook convention while the preserver itself stays keyword-only.
