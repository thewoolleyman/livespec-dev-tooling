"""Paired test for `livespec_dev_tooling/agent_hooks/__init__.py`.

The package `__init__.py` is a pure-declaration module (only an empty
`__all__`); this test imports it so the per-file / incremental-coverage
gate has a mirror-paired test for the new agent-hooks package,
matching the tests-mirror-pairing invariant (same pattern as
`tests/livespec_dev_tooling/workflow_checks/test__init__.py`).
"""

from __future__ import annotations

import importlib

__all__: list[str] = []


def test_agent_hooks_package_imports_with_empty_all() -> None:
    """The package imports cleanly and declares an empty public `__all__`."""
    module = importlib.import_module("livespec_dev_tooling.agent_hooks")
    assert module.__all__ == []
