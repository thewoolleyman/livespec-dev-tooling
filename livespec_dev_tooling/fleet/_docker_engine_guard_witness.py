"""What each sample compares against the snapshot the preflight recorded.

Governing specification: `SPECIFICATION/non-functional-requirements.md`
section "Docker engine install guard", "Probes" -- "Sysctls", "k3s
witness" and "Interfaces". Governing design:
`docs/docker-engine-guard-design.md` R8 and F8.

These share a module because they share a METHOD, not merely a subject:
each one answers "is this still what it was", and each one gets its
answer by reading a record taken before the first package step and
comparing it with the host now. None of them has an opinion about what
the host OUGHT to look like -- the snapshot is the only record of what
this machine was, and a probe that asserted a value instead of a
baseline would pass a host it had already changed.

Stdlib only, Python 3.10 syntax.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from livespec_dev_tooling.fleet._docker_engine_guard_netstate import compare_sysctls
from livespec_dev_tooling.fleet._docker_engine_guard_sample import ProbeResult

if TYPE_CHECKING:
    from pathlib import Path

    from livespec_dev_tooling.fleet._docker_engine_guard_runner import GuardCommandRunner

__all__: list[str] = [
    "SYSCTL_PROBE",
    "sysctl_probe",
]

SYSCTL_PROBE: Final[str] = "sysctls"


def sysctl_probe(*, runner: GuardCommandRunner, snapshot: Path) -> ProbeResult:
    """Whether the five watched forwarding and bridge-netfilter values are unmoved.

    Every value that moved is named with where it was and where it is,
    because an operator reading a failed sample has to put it back and
    the snapshot is the only record of the original. A Docker install
    flips several of these, and one left flipped is how k3s's pod
    network stops forwarding without anything reporting an error.
    """
    moved = compare_sysctls(runner=runner, snapshot=snapshot)
    return ProbeResult(name=SYSCTL_PROBE, passed=not moved, error="; ".join(moved))
