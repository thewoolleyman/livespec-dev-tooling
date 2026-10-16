"""The guarded host's kernel network state: the watched sysctls and `docker0`.

Governing specification: `SPECIFICATION/non-functional-requirements.md`
section "Docker engine install guard" -- the snapshot's five watched
forwarding and bridge-netfilter values, and "Host actions", "Sysctls" and
"Interfaces".

These two concerns share a module because they share a question: what did
the Docker install change about this host's packet path that a rollback
has to put back. Both are read through the one timed runner, so both can
be driven from recorded `sysctl -n` and `ip link` output.

Stdlib only, Python 3.10 syntax.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from livespec_dev_tooling.fleet._docker_engine_guard_runner import GuardCommandRunner

__all__: list[str] = [
    "SYSCTL_SNAPSHOT",
    "SYSCTL_TIMEOUT_SECONDS",
    "WATCHED_SYSCTLS",
    "read_sysctls",
    "write_sysctl_snapshot",
]

# The five values, sorted, so a snapshot and a report list them the same
# way: both families' forwarding, and the three bridge-netfilter hooks
# that decide whether a bridged frame is seen by iptables at all. A
# Docker install flips several of these, and a flipped one that a
# rollback leaves behind is how k3s's pod network silently stops
# forwarding.
WATCHED_SYSCTLS: Final[tuple[str, ...]] = (
    "net.bridge.bridge-nf-call-arptables",
    "net.bridge.bridge-nf-call-ip6tables",
    "net.bridge.bridge-nf-call-iptables",
    "net.ipv4.ip_forward",
    "net.ipv6.conf.all.forwarding",
)

# A `sysctl -n` read is a kernel read with no lock to wait on, so the
# bound is short; it exists to cap a wedged `/proc`, not a slow answer.
SYSCTL_TIMEOUT_SECONDS: Final[int] = 10

SYSCTL_SNAPSHOT: Final[str] = "sysctl.json"


def read_sysctls(*, runner: GuardCommandRunner) -> Mapping[str, str]:
    """Each watched value as the kernel reports it right now."""
    return {
        name: runner(
            argv=("sysctl", "-n", name), timeout_seconds=SYSCTL_TIMEOUT_SECONDS
        ).stdout.strip()
        for name in WATCHED_SYSCTLS
    }


def write_sysctl_snapshot(*, destination: Path, runner: GuardCommandRunner) -> None:
    """Record the five watched values in the run's `before/` directory."""
    _ = (destination / SYSCTL_SNAPSHOT).write_text(
        json.dumps(read_sysctls(runner=runner), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
