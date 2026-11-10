"""Tests for the orchestrator hold probe a tag adopt runs in a clone's environment.

The probe exits 0 exactly when the livespec-dev-tooling package it runs from
provides the Session reconcile hold, so a tag adopt can refuse a clone whose
own `just ensure-plugins` would move the adopted build back.
"""

from __future__ import annotations

import importlib
from types import ModuleType

from livespec_dev_tooling.fleet import orchestrator_hold_probe
from livespec_dev_tooling.fleet.orchestrator_hold_probe import (
    HOLD_MODULE,
    RECONCILE_MODULE,
    provides_hold,
)

__all__: list[str] = []


def _module(*, name: str, attributes: dict[str, object]) -> ModuleType:
    module = ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    return module


def test_the_probe_exits_zero_from_a_package_that_provides_the_hold() -> None:
    assert orchestrator_hold_probe.main() == 0


def test_this_package_provides_the_hold_through_its_reconcile() -> None:
    assert provides_hold(import_module=importlib.import_module)


def test_a_package_without_the_hold_module_does_not_provide_the_hold() -> None:
    reconcile = importlib.import_module(RECONCILE_MODULE)

    def import_module(name: str) -> ModuleType:
        if name == HOLD_MODULE:
            raise ModuleNotFoundError(name)
        return reconcile

    assert not provides_hold(import_module=import_module)


def test_a_reconcile_that_does_not_use_the_hold_does_not_provide_it() -> None:
    hold = importlib.import_module(HOLD_MODULE)
    reconcile = _module(name=RECONCILE_MODULE, attributes={})

    def import_module(name: str) -> ModuleType:
        return hold if name == HOLD_MODULE else reconcile

    assert not provides_hold(import_module=import_module)


def test_a_reconcile_whose_hold_names_are_its_own_does_not_provide_it() -> None:
    hold = importlib.import_module(HOLD_MODULE)
    reconcile = _module(
        name=RECONCILE_MODULE,
        attributes={
            "orchestrator_state": object(),
            "hold_notice": hold.hold_notice,
            "without_plugin_commands": hold.without_plugin_commands,
        },
    )

    def import_module(name: str) -> ModuleType:
        return hold if name == HOLD_MODULE else reconcile

    assert not provides_hold(import_module=import_module)
