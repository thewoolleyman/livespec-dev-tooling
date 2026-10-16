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

from livespec_dev_tooling.fleet._docker_engine_guard_firewall import DOCKER_BRIDGE

if TYPE_CHECKING:
    from livespec_dev_tooling.fleet._docker_engine_guard_runner import GuardCommandRunner

__all__: list[str] = [
    "IP_COMMAND",
    "LINK_SHOW_ARGV",
    "LINK_TIMEOUT_SECONDS",
    "SYSCTL_SNAPSHOT",
    "SYSCTL_TIMEOUT_SECONDS",
    "WATCHED_SYSCTLS",
    "compare_sysctls",
    "delete_bridge_interfaces",
    "read_bridge_links",
    "read_sysctls",
    "write_sysctl_snapshot",
]

IP_COMMAND: Final[str] = "ip"

# `-o` puts each link on ONE line, which is what makes `master docker0`
# readable per link at all: the default multi-line form puts the master on
# a continuation line and a line-wise scan would attribute it to the wrong
# interface.
LINK_SHOW_ARGV: Final[tuple[str, ...]] = (IP_COMMAND, "-o", "link", "show")

LINK_TIMEOUT_SECONDS: Final[int] = 15

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

# The index and the name are the only columns every `ip -o link` row has.
_LINK_COLUMNS: Final[int] = 2


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


def read_bridge_links(*, runner: GuardCommandRunner) -> tuple[str, ...]:
    """Every link mastered by `docker0`, then `docker0` itself.

    The bridge comes LAST so no veth is left orphaned if the deletion
    stops part way. Selection is by `master docker0` and not by a name
    prefix: a veth's name is random, and `flannel.1` -- mastered by `cni0`
    -- is exactly the shape a prefix or substring match gets wrong, which
    on this host means deleting a link k3s's pod network runs over.
    """
    answer = runner(argv=LINK_SHOW_ARGV, timeout_seconds=LINK_TIMEOUT_SECONDS)
    mastered: list[str] = []
    bridge: list[str] = []
    for raw in answer.stdout.splitlines():
        fields = raw.split()
        if len(fields) < _LINK_COLUMNS:
            continue
        name = fields[1].rstrip(":").split("@")[0]
        if name == DOCKER_BRIDGE:
            bridge.append(name)
        elif f"master {DOCKER_BRIDGE}" in raw:
            mastered.append(name)
    return (*mastered, *bridge)


def delete_bridge_interfaces(*, runner: GuardCommandRunner) -> tuple[str, ...]:
    """Delete `docker0` and every veth mastered by it; report what went."""
    going = read_bridge_links(runner=runner)
    for name in going:
        _ = runner(
            argv=(IP_COMMAND, "link", "delete", name),
            timeout_seconds=LINK_TIMEOUT_SECONDS,
        )
    return going


def snapshot_sysctls(*, snapshot: Path) -> Mapping[str, str]:
    """The five watched values as the run's `before/` directory recorded them."""
    recorded = json.loads((snapshot / SYSCTL_SNAPSHOT).read_text(encoding="utf-8"))
    return {name: str(recorded[name]) for name in WATCHED_SYSCTLS}


def compare_sysctls(*, runner: GuardCommandRunner, snapshot: Path) -> tuple[str, ...]:
    """Each watched value that moved, named with where it was and where it is.

    BOTH values are reported because an operator reading
    `rollback-partial` has to put the value back and the snapshot is the
    only record of what it was. A value that matches stays silent: a
    report naming all five every time would bury the one that matters.
    """
    recorded = snapshot_sysctls(snapshot=snapshot)
    current = read_sysctls(runner=runner)
    return tuple(
        f"{name} {recorded[name]} -> {current[name]}"
        for name in WATCHED_SYSCTLS
        if current[name] != recorded[name]
    )
