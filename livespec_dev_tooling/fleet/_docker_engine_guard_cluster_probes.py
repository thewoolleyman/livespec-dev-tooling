"""The probes that ask the CLUSTER and the service manager about this host.

Governing specification: `SPECIFICATION/non-functional-requirements.md`
section "Docker engine install guard", "Probes" -- "Services", "Node
Ready" and the placement half of "DNS". Governing design:
`docs/docker-engine-guard-design.md` Mechanism 3 as corrected by R8 and
F7.

These three share a module because they share a QUESTION: is this host
still a working member of the cluster it was a member of before the
install. None of them enters a pod's network namespace -- those probes
live next door -- and none of them touches Docker.

Stdlib only, Python 3.10 syntax.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from livespec_dev_tooling.fleet._docker_engine_guard_sample import ProbeResult
from livespec_dev_tooling.fleet._docker_engine_guard_units import unit_active_states

if TYPE_CHECKING:
    from collections.abc import Sequence

    from livespec_dev_tooling.fleet._docker_engine_guard_runner import GuardCommandRunner

__all__: list[str] = [
    "ACTIVE",
    "REQUIRED_UNITS",
    "SERVICES_PROBE",
    "services_probe",
]

# The two units the guarded host's own life depends on, whatever else the
# fleet declares. `k3s-agent` is the CI pool agent this machine exists to
# run, and `tailscaled` serves the only remote access path there is --
# the whole guard exists because nobody can reach this host physically.
REQUIRED_UNITS: Final[tuple[str, ...]] = (
    "k3s-agent.service",
    "tailscaled.service",
)

ACTIVE: Final[str] = "active"

SERVICES_PROBE: Final[str] = "services"


def services_probe(*, runner: GuardCommandRunner, must_stay_running: Sequence[str]) -> ProbeResult:
    """Whether the two required units and every declared one are active.

    `activating` and `failed` are NOT active, and the difference matters
    to whoever reads the failure: the first is a unit on its way back and
    the second is one that gave up, so each unit is reported with the
    state it was actually in rather than merely as "not active".

    The declared units are appended to the required two and de-duplicated
    IN ORDER, so a fleet variable that names `k3s-agent` again costs one
    read rather than two and the recorded argv sequence stays the same
    whatever the declaration repeats.
    """
    units = tuple(dict.fromkeys((*REQUIRED_UNITS, *must_stay_running)))
    states = unit_active_states(runner=runner, units=units)
    stopped = tuple(f"{unit} is {states[unit]}" for unit in units if states[unit] != ACTIVE)
    return ProbeResult(name=SERVICES_PROBE, passed=not stopped, error="; ".join(stopped))
