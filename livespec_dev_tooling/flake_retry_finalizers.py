"""Preserve higher-scope pytest fixture finalizers while a test is retried."""

from __future__ import annotations

from collections.abc import Generator
from typing import cast

import pytest

__all__: list[str] = ["RetryFinalizerPreserver", "protocol_hook", "teardown_hook"]


class RetryFinalizerPreserver:
    """Keep finalizer-owning setup nodes alive across rerunfailures' teardown."""

    def __init__(self) -> None:
        self._preserved_stacks: dict[pytest.Item, dict[object, object]] = {}

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
        """Save higher-scope fixture finalizers before a retry clears their stack."""
        del nextitem
        stack = self._setup_stack(item=item)
        saved_stack = None if stack is None else stack.copy()
        yield
        if stack is None or saved_stack is None or not self._retry_is_pending(item=item):
            return
        preserved_stack = {key: value for key, value in saved_stack.items() if key is not item}
        _ = self._preserved_stacks.setdefault(item, preserved_stack)

    @pytest.hookimpl(hookwrapper=True, tryfirst=True)
    def protocol(
        self, *, item: pytest.Item, nextitem: pytest.Item | None
    ) -> Generator[None, None, None]:
        """Restore finalizer ownership after rerunfailures clears the setup stack."""
        del nextitem
        yield
        preserved_stack = self._preserved_stacks.pop(item, None)
        stack = self._setup_stack(item=item)
        if preserved_stack is None or stack is None:
            return
        restored_stack = preserved_stack.copy()
        restored_stack.update(stack)
        stack.clear()
        stack.update(restored_stack)


# PYTEST CALLS ITS HOOKS POSITIONALLY. pluggy reads a hook's argument names off
# its signature and passes them by position, so a keyword-only hook receives
# nothing, and a `*args` hook receives nothing either. These adapters preserve
# the public hook convention while the preserver itself stays keyword-only.
_PRESERVER = RetryFinalizerPreserver()


class _TeardownHook:
    @pytest.hookimpl(hookwrapper=True, tryfirst=True)
    def __call__(
        self, item: pytest.Item, nextitem: pytest.Item | None
    ) -> Generator[None, None, None]:
        yield from _PRESERVER.teardown(item=item, nextitem=nextitem)


class _ProtocolHook:
    @pytest.hookimpl(hookwrapper=True, tryfirst=True)
    def __call__(
        self, item: pytest.Item, nextitem: pytest.Item | None
    ) -> Generator[None, None, None]:
        yield from _PRESERVER.protocol(item=item, nextitem=nextitem)


teardown_hook = _TeardownHook().__call__
protocol_hook = _ProtocolHook().__call__
