"""Paired test for `livespec_dev_tooling/charters/__init__.py`."""

from __future__ import annotations

import importlib

__all__: list[str] = []


def test_charters_package_reexports_public_api() -> None:
    """The package import surface stays wired to the implementation module."""
    module = importlib.import_module("livespec_dev_tooling.charters")
    implementation = importlib.import_module("livespec_dev_tooling.charters.charters")

    assert module.__all__ == [
        "CHARTER_GLOBS",
        "DETECTORS",
        "charters_in",
        "defects_in",
    ]
    assert module.CHARTER_GLOBS is implementation.CHARTER_GLOBS
    assert module.DETECTORS is implementation.DETECTORS
    assert module.charters_in is implementation.charters_in
    assert module.defects_in is implementation.defects_in
