"""Read incident timing declarations without importing or running checks."""

from __future__ import annotations

import re

from livespec_dev_tooling.check_inventory import annotation_values, inventory_members
from livespec_dev_tooling.incident_local_gates import GateSpec

__all__: list[str] = ["inventory_gates", "timing_classes"]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-cerkbn
# The existing aggregate inventory remains the population. An absent or invalid
# timing declaration never grants permission to run an unbounded check.
#
# Both expedited paths read their timing class here (livespec-dev-tooling-oqpw6t):
# the local hooks through `inventory_gates`, and the CI entrance's packaged
# inventory through `incident_ci_inventory.render_inventory`.
_TIMING_KEY = "incident-timing"
_PRECONDITION_KEY = "incident-precondition"
# `not-applicable`: the gate encodes a normal-path precondition an incident
# commit cannot meet by design, so it could only ever refuse the repair; the
# member's `incident-precondition` annotation names that precondition.
_CLASSES = frozenset({"fast", "slow", "not-applicable"})

# The one stated difference from the aggregate's membership: a member that is
# not a bare recipe name is never handed to `just` as an argument. The aggregate
# itself refuses such an inventory at its justfile mirror check in
# `scripts/just/check.sh`, so for every inventory it can run the sets are equal.
_RECIPE = re.compile(r"check-[a-z0-9]+(?:-[a-z0-9]+)*")


def timing_classes(*, inventory: str) -> dict[str, str]:
    """Map each member to `fast`, `slow`, `not-applicable` or `unclassified`, in order.

    Only a single exact `incident-timing:` declaration of one of the first three
    on a member's only line classifies it. A missing, invalid or conflicting
    declaration, or a member listed twice, is `unclassified`.
    """
    declared: dict[str, list[str]] = {}
    for member in inventory_members(text=inventory):
        values = annotation_values(member=member, key=_TIMING_KEY)
        declared.setdefault(member.name, []).append(values[0] if len(values) == 1 else "")
    return {
        name: values[0] if len(values) == 1 and values[0] in _CLASSES else "unclassified"
        for name, values in declared.items()
    }


def inventory_gates(*, inventory: str) -> tuple[GateSpec, ...]:
    """Build argv from the canonical inventory, retaining explicit deferrals.

    These annotations are comments to the normal aggregate's existing reader.
    """
    preconditions = {
        member.name: " ".join(annotation_values(member=member, key=_PRECONDITION_KEY))
        for member in inventory_members(text=inventory)
    }
    return tuple(
        GateSpec(
            name=name,
            command=("just", name),
            classification=timing,
            precondition=preconditions[name],
        )
        for name, timing in timing_classes(inventory=inventory).items()
        if _RECIPE.fullmatch(name) is not None
    )
