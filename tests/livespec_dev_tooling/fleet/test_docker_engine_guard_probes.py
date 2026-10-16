"""Tests for the Docker engine install guard's preflight and its probes (child 4).

Governing specification: `SPECIFICATION/non-functional-requirements.md`
section "Docker engine install guard", "Preflight" and "Probes".
Governing design: `docs/docker-engine-guard-design.md`: Mechanism 3's
probes as corrected by R8, R9 (exclusive admission during the window),
F7 (admission and collision checks), F8 (the k3s witness) and R4's
comparison scope.

Every check and every probe is driven against RECORDED command output --
`ip -o addr show`, `ip route show table all`, `getent`, `systemctl show`,
`k3s crictl`, `k3s kubectl get --raw`, `docker ps`, `iptables-save` --
handed back by the one injectable runner, and each assertion reads the
ARGV the check or probe emitted. No real host is touched, no namespace is
entered and no process is spawned, which is what makes a probe set that
runs inside a pod's network namespace testable at all.

The modules under test are reached through `importlib` inside each test
body rather than imported at the top, and the recorded-command bus below
is annotated `Any` for the same reason: a top-level import of a module a
Red moment has not created yet makes that Red a COLLECTION error instead
of a genuine assertion failure. This is the pattern the sibling host and
lifecycle tests already use.
"""

from __future__ import annotations

import importlib
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__: list[str] = []

_RUNNER_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_runner"
_PREFLIGHT_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_preflight"
_PREFLIGHT_PATH = Path("livespec_dev_tooling/fleet/_docker_engine_guard_preflight.py")


def _result(*, argv: tuple[str, ...], returncode: int, stdout: str) -> Any:
    """One `GuardCommandResult`, built through the guard's own runner module."""
    runner_module = importlib.import_module(_RUNNER_MODULE)
    return runner_module.GuardCommandResult(argv=argv, returncode=returncode, stdout=stdout)


@dataclass(kw_only=True)
class _Commands:
    """A recorded command bus standing in for the guard's one timed runner.

    `answers` maps a whole argv to the output a real host would hand
    back and `codes` to the exit status, so a probe that reads a reply
    and a probe that merely has to succeed are both drivable. Each call
    is recorded with the timeout it carried, which is how "every command
    the preflight and the probes run is bounded" is asserted.
    """

    answers: dict[tuple[str, ...], str] = field(default_factory=dict)
    codes: dict[tuple[str, ...], int] = field(default_factory=dict)
    argvs: list[tuple[str, ...]] = field(default_factory=list)
    timeouts: list[int] = field(default_factory=list)

    def __call__(self, *, argv: Sequence[str], timeout_seconds: int) -> Any:
        key = tuple(argv)
        self.argvs.append(key)
        self.timeouts.append(timeout_seconds)
        return _result(
            argv=key, returncode=self.codes.get(key, 0), stdout=self.answers.get(key, "")
        )


def _lines(*rows: str) -> str:
    """Recorded command output, as a host writes it: one row per line."""
    return "".join(f"{row}\n" for row in rows)


# `ip -o addr show` on the guarded host before anything Docker-shaped
# exists: the wired interface, the tailnet address and k3s's own bridge,
# none of them anywhere near Docker's default subnet.
_ADDRESSES_CLEAR = _lines(
    "1: lo    inet 127.0.0.1/8 scope host lo",
    "2: enp2s0    inet 192.168.1.42/24 brd 192.168.1.255 scope global enp2s0",
    "3: tailscale0    inet 100.86.4.19/32 scope global tailscale0",
    "4: cni0    inet 10.42.2.1/24 brd 10.42.2.255 scope global cni0",
    "5: enp2s0    inet6 fe80::1a2b:3cff:fe4d:5e6f/64 scope link",
)

# The same read on a host that already carries a bridge inside
# 172.17.0.0/16 -- a hand-made lab bridge, which is exactly the shape
# that makes the Docker install steal an address range in use.
_ADDRESSES_OVERLAPPING = _ADDRESSES_CLEAR + _lines(
    "7: br-lab    inet 172.17.3.1/24 brd 172.17.3.255 scope global br-lab",
)

# `ip route show table all`: the default route, k3s's pod route, and the
# `local`/`broadcast` rows every host's `local` table carries -- those
# rows put a ROUTE TYPE before the destination, so a parse that read the
# first field blindly would compare the word `local` as an address.
_ROUTES_CLEAR = _lines(
    "default via 192.168.1.1 dev enp2s0 proto dhcp src 192.168.1.42 metric 100",
    "10.42.0.0/24 via 10.42.0.0 dev flannel.1 onlink",
    "10.42.2.0/24 dev cni0 proto kernel scope link src 10.42.2.1",
    "local 192.168.1.42 dev enp2s0 table local proto kernel scope host src 192.168.1.42",
    "broadcast 192.168.1.255 dev enp2s0 table local proto kernel scope link",
)

# The same read on a host where tailscaled's own table 52 already routes
# Docker's default subnet to the tailnet: a route the install would
# shadow, taking every tailnet peer in that range with it.
_ROUTES_OVERLAPPING = _ROUTES_CLEAR + _lines(
    "172.17.0.0/16 dev tailscale0 table 52",
)

_ROUTES6 = _lines(
    "fe80::/64 dev enp2s0 proto kernel metric 256 pref medium",
    "local ::1 dev lo table local proto kernel metric 0 pref medium",
)

# The ranges the controller declares for this host: the tailnet, and the
# cluster's pod and service CIDRs. They are DECLARED rather than read
# because they are facts about the cluster, not about this machine.
_DECLARED_CLEAR = {
    "cluster pod CIDR": "10.42.0.0/16",
    "cluster service CIDR": "10.43.0.0/16",
    "tailnet range": "100.64.0.0/10",
}

# The same declaration on a cluster whose pod CIDR was carved out of
# 172.16.0.0/12, which CONTAINS Docker's default subnet.
_DECLARED_OVERLAPPING = {
    "cluster pod CIDR": "172.16.0.0/12",
    "cluster service CIDR": "10.43.0.0/16",
    "tailnet range": "100.64.0.0/10",
}


def _clear_host_bus() -> _Commands:
    """A bus answering every preflight read of a host clear of Docker's subnet."""
    preflight = importlib.import_module(_PREFLIGHT_MODULE)
    return _Commands(
        answers={
            preflight.ADDRESS_SHOW_ARGV: _ADDRESSES_CLEAR,
            preflight.ROUTE_SHOW_ARGV["ipv4"]: _ROUTES_CLEAR,
            preflight.ROUTE_SHOW_ARGV["ipv6"]: _ROUTES6,
        }
    )


def test_preflight_refuses_every_overlap_of_the_docker_subnet() -> None:
    """172.17.0.0/16 may not overlap an address, a route or a declared range.

    All four sources named by design F7 are asserted here because they
    fail the same way and are easy to implement one of: an address on
    any interface, a route in ANY routing table (so `table all`, and
    both families), the tailnet range and the cluster's two CIDRs. An
    overlap that reached the install would hand Docker a range already
    carrying the host's own access path.
    """
    assert _PREFLIGHT_PATH.is_file()
    preflight = importlib.import_module(_PREFLIGHT_MODULE)

    clear = _clear_host_bus()
    assert preflight.subnet_overlaps(runner=clear, declared=_DECLARED_CLEAR) == ()
    assert tuple(clear.argvs) == (
        preflight.ADDRESS_SHOW_ARGV,
        preflight.ROUTE_SHOW_ARGV["ipv4"],
        preflight.ROUTE_SHOW_ARGV["ipv6"],
    )
    assert set(clear.timeouts) == {preflight.PREFLIGHT_TIMEOUT_SECONDS}

    addressed = _clear_host_bus()
    addressed.answers[preflight.ADDRESS_SHOW_ARGV] = _ADDRESSES_OVERLAPPING
    assert preflight.subnet_overlaps(runner=addressed, declared=_DECLARED_CLEAR) == (
        "172.17.0.0/16 overlaps the address 172.17.3.1/24 on br-lab",
    )

    routed = _clear_host_bus()
    routed.answers[preflight.ROUTE_SHOW_ARGV["ipv4"]] = _ROUTES_OVERLAPPING
    assert preflight.subnet_overlaps(runner=routed, declared=_DECLARED_CLEAR) == (
        "172.17.0.0/16 overlaps the route 172.17.0.0/16 in a routing table",
    )

    declared = _clear_host_bus()
    assert preflight.subnet_overlaps(runner=declared, declared=_DECLARED_OVERLAPPING) == (
        "172.17.0.0/16 overlaps the declared cluster pod CIDR 172.16.0.0/12",
    )
