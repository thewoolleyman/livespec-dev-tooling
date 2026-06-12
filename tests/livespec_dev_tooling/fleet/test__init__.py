"""Paired test for `livespec_dev_tooling/fleet/__init__.py`.

The package `__init__.py` is a pure-declaration module (only an empty
`__all__`); this test imports it so the per-file / incremental-coverage
gate has a mirror-paired test for the fleet-membership package,
matching the tests-mirror-pairing invariant (same pattern as the
`workflow_checks` package's paired test).
"""

from __future__ import annotations

import importlib

__all__: list[str] = []


def test_fleet_package_imports_with_empty_all() -> None:
    """The package imports cleanly and declares an empty public `__all__`."""
    module = importlib.import_module("livespec_dev_tooling.fleet")
    assert module.__all__ == []
