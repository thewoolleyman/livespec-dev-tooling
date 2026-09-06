"""No two modules of `livespec_dev_tooling/fleet/` declare the same type name.

⛔ THIS IS THE ONLY MECHANISM THAT WILL EVER SURFACE A NAME COLLISION HERE,
which is why it is a test rather than a note. `ensure_plugins` shipped its own
`CommandResult` / `CommandRunner` beside `_local_context`'s pair for months:
same two names in one package, DIFFERENT shapes (exit code only versus exit
code + streams; a bare record versus an `IOResult` failure track), and neither
module aware of the other. Nothing convicted it — `check-public-api-result-typed`
had no expected failure mode to judge, and no check anywhere looks for a name
declared twice in one package. An invisible collision does not become visible by
being noticed once in a session; the observation dies with the context that made
it, so it is pinned here instead (`livespec-dev-tooling-6e83`).

WHAT THE COLLISION ACTUALLY COSTS, and it is why the assertion is on NAMES
rather than on shapes: a reader or an editor who imports one `CommandResult`
into a module that already imports the other gets a SILENT SHADOW, not an
error — both are legitimate names in the same package. The wrong import then
type-checks on the attribute the two agree about and fails only on the ones
they do not.

SCOPE — top-level classes of the fleet package's own modules. Nested classes
are addressed through their owner and cannot shadow one another on import;
imported names are not declarations, so a module re-exporting a sibling's type
is not a collision.
"""

from __future__ import annotations

import ast
from collections import defaultdict
from pathlib import Path

__all__: list[str] = []

_FLEET_DIR = Path(__file__).resolve().parents[3] / "livespec_dev_tooling" / "fleet"


def _declaring_modules() -> dict[str, list[str]]:
    """Every top-level class name in the fleet package, mapped to its modules."""
    declared: defaultdict[str, list[str]] = defaultdict(list)
    for module in sorted(_FLEET_DIR.glob("*.py")):
        for node in ast.parse(module.read_text(encoding="utf-8")).body:
            if isinstance(node, ast.ClassDef):
                declared[node.name].append(module.name)
    return dict(declared)


def test_the_fleet_package_declares_each_type_name_exactly_once() -> None:
    collisions = {
        name: modules for name, modules in _declaring_modules().items() if len(modules) > 1
    }
    assert collisions == {}


def test_the_collision_scan_reads_the_real_fleet_package() -> None:
    """A scan of an empty or wrong directory would pass the assertion above."""
    declared = _declaring_modules()
    assert declared["LocalContext"] == ["_local_context.py"]
    assert declared["InvocationNotPerformed"] == ["_invocation_failure.py"]
