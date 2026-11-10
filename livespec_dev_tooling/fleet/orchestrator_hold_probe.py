"""The orchestrator hold probe: does this package provide the Session reconcile hold?

A tag adopt moves one clone's orchestrator build off the build the marketplace
offers. That clone's next session start runs its own `just ensure-plugins`,
from the livespec-dev-tooling package installed in the clone's environment, and
only a package that holds an installed orchestrator build leaves the adopted
build in place. The installed package can lag the clone's pin until the
environment is synced, so the tag adopt asks the package itself: it runs
`python -m livespec_dev_tooling.fleet.orchestrator_hold_probe` in the clone's
environment, and this module exits 0 exactly when the package it runs from
provides the hold. A package that predates the hold has no such module, and
the interpreter's own non-zero exit refuses it.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from types import ModuleType

__all__: list[str] = ["HOLD_MODULE", "RECONCILE_MODULE", "main", "provides_hold"]

RECONCILE_MODULE = "livespec_dev_tooling.fleet.ensure_plugins"
HOLD_MODULE = "livespec_dev_tooling.fleet._orchestrator_hold"

# The hold's three moving parts, each of which `ensure-plugins` must take from
# the hold module itself: classify the install, strip the orchestrator's
# install and update commands, and print the line naming the held build.
_HOLD_NAMES = ("orchestrator_state", "without_plugin_commands", "hold_notice")


def provides_hold(*, import_module: Callable[[str], ModuleType]) -> bool:
    """Whether the session reconcile takes every part of the hold from the hold module."""
    try:
        reconcile = import_module(RECONCILE_MODULE)
        hold = import_module(HOLD_MODULE)
    except ImportError:
        return False
    return all(
        getattr(hold, name, None) is not None
        and getattr(reconcile, name, None) is getattr(hold, name, None)
        for name in _HOLD_NAMES
    )


def main() -> int:
    """CLI entry point: exit 0 when this package provides the hold, 1 otherwise."""
    return 0 if provides_hold(import_module=importlib.import_module) else 1


if __name__ == "__main__":
    raise SystemExit(main())
