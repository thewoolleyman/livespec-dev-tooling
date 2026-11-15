"""A fast incident member never declares a host precondition the hook cannot probe.

`SPECIFICATION/contracts.md` §"Expedited incident execution" says a member classed
fast MUST NOT read host-installed tools or the host's home directory, and that a
member needing one declares the precondition so the hook probes it before running
the member. The hook has no precondition probe today: every member that declares
an `incident-precondition` is classed `not-applicable`, so it never runs in
incident mode and is deferred with the precondition named. That rule holds only
because nothing is both fast and preconditioned. This guard makes that fail
closed (livespec-dev-tooling-7qb2bs, legacy-coordinator-agent grade of
livespec-dev-tooling#4731). A future fast member that declares a precondition is
refused here until a hook probe for it exists and this guard is widened to name
that probe.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from livespec_dev_tooling.incident_gate_inventory import precondition_names, timing_classes

_ROOT = Path(__file__).resolve().parents[2]
_DATA = _ROOT / "livespec_dev_tooling" / "data"
_INVENTORIES = sorted(
    [_DATA / "incident-ci-inventory.json", *(_DATA / "incident-ci-inventory").rglob("*.json")]
)

# Preconditions the expedited hook can probe before running a fast member. Empty
# until such a probe ships; adding a name here is the deliberate act that admits a
# fast, preconditioned member.
_PROBED_PRECONDITIONS: frozenset[str] = frozenset()


def _fast_preconditioned(*, targets: list[dict[str, object]]) -> list[str]:
    return sorted(
        f"{target['name']}: {target['precondition']}"
        for target in targets
        if target.get("classification") == "fast"
        and target.get("precondition")
        and target["precondition"] not in _PROBED_PRECONDITIONS
    )


@pytest.mark.parametrize("path", _INVENTORIES, ids=lambda path: path.relative_to(_DATA).as_posix())
def test_no_released_inventory_classes_a_preconditioned_member_fast(path: Path) -> None:
    targets = json.loads(path.read_text())["targets"]
    assert _fast_preconditioned(targets=targets) == []


def test_this_repository_classes_no_preconditioned_member_fast() -> None:
    inventory = (_ROOT / "check-targets.txt").read_text()
    classes = timing_classes(inventory=inventory)
    offending = sorted(
        f"{name}: {precondition}"
        for name, precondition in precondition_names(inventory=inventory).items()
        if precondition
        and classes.get(name) == "fast"
        and precondition not in _PROBED_PRECONDITIONS
    )
    assert offending == []


def test_the_guard_refuses_a_fast_member_that_declares_an_unprobed_precondition() -> None:
    targets: list[dict[str, object]] = [
        {"name": "check-live-tool", "classification": "fast", "precondition": "a-host-tool"},
        {"name": "check-normal-only", "classification": "not-applicable", "precondition": "x"},
        {"name": "check-plain", "classification": "fast"},
    ]
    assert _fast_preconditioned(targets=targets) == ["check-live-tool: a-host-tool"]
