"""Read local gate timing declarations without importing or running checks."""

from __future__ import annotations

import re

from livespec_dev_tooling.incident_local_gates import GateSpec

__all__: list[str] = ["inventory_gates"]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-cerkbn
# The existing aggregate inventory remains the population. An absent or invalid
# timing declaration never grants permission to run an unbounded check.
_TARGET = re.compile(r"check-[a-z0-9]+(?:-[a-z0-9]+)*")
_TIMING = re.compile(r"#\s*incident-timing:\s*(\S+)")


def inventory_gates(*, inventory: str) -> tuple[GateSpec, ...]:
    """Build argv from the canonical inventory, retaining explicit deferrals.

    Only a single exact ``incident-timing: fast`` declaration selects work.
    Conflicting declarations and duplicate targets are unclassified. These
    annotations are comments to the normal aggregate's existing reader.
    """
    entries: dict[str, list[str]] = {}
    for line in inventory.splitlines():
        target = line.split("#", maxsplit=1)[0].strip()
        if _TARGET.fullmatch(target) is None:
            continue
        declarations = _TIMING.findall(line)
        timing = declarations[0] if len(declarations) == 1 else "unclassified"
        entries.setdefault(target, []).append(timing)
    return tuple(
        GateSpec(
            name=target,
            command=("just", target),
            classification=timings[0] if len(timings) == 1 else "unclassified",
        )
        for target, timings in entries.items()
    )
