"""Mirror coverage for the config-value commit-hook workflow check."""

from __future__ import annotations

from livespec_dev_tooling.workflow_checks.config_value_fast_path import (
    CONFIG_VALUE_FAST_PATH_RULES,
)

__all__: list[str] = []


def test_the_workflow_check_declares_the_required_capacity_keys() -> None:
    """The shared list remains the one declaration used by the hook classifier."""
    assert {rule.key_path for rule in CONFIG_VALUE_FAST_PATH_RULES} >= {
        "ADMISSION_CAPACITY_C",
        "dispatcher.wip_cap",
        "max_concurrent_runs",
        "stall_timeout_seconds",
    }
