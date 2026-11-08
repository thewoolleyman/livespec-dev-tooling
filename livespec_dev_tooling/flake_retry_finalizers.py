"""Preserve higher-scope pytest fixture finalizers while a test is retried."""

from __future__ import annotations

import pytest

__all__: list[str] = ["preserve_finalizers"]


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
