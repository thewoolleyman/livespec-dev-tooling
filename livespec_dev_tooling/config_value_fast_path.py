"""Stable public entry point for the config-value pre-commit workflow check."""

from __future__ import annotations

from livespec_dev_tooling.workflow_checks.config_value_fast_path import (
    CONFIG_VALUE_FAST_PATH_RULES,
    ConfigValueFastPathRule,
    main,
)

__all__: list[str] = ["CONFIG_VALUE_FAST_PATH_RULES", "ConfigValueFastPathRule", "main"]


if __name__ == "__main__":
    raise SystemExit(main())
