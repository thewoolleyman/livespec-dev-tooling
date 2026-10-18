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
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

import pytest

__all__: list[str] = []

_RUNNER_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_runner"
_MODEL_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_model"
_HOST_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_host"
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

    def argvs_with(self, *, flag: str) -> tuple[tuple[str, ...], ...]:
        """Every recorded argv carrying `flag`, in the order it was emitted."""
        return tuple(argv for argv in self.argvs if flag in argv)


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


def _guard_paths(*, root: Path) -> Any:
    """The guard's durable and runtime roots, under a recorded tree."""
    model = importlib.import_module(_MODEL_MODULE)
    return model.GuardPaths(state_root=root / "var", runtime_root=root / "run")


def _real_host(*, root: Path, commands: _Commands, **roots: Any) -> Any:
    """The guard's REAL host, rooted under `root` and driven by `commands`.

    The same object the guard's command line builds, so what is asserted
    is the host layer the factory actually runs -- not a second
    implementation standing in for it. `roots` carries the two
    filesystem locations the host reads directly (`/proc` and k3s's
    containerd paths) when a test has to point them at a recorded tree.
    """
    host_module = importlib.import_module(_HOST_MODULE)
    return host_module.build_real_host(paths=_guard_paths(root=root), runner=commands, **roots)


# `getent group docker` on a host where the install has already created
# the group and somebody has been added to it, and `getent passwd` where
# one further account carries that group as its PRIMARY one. Both shapes
# have to be found: a member list names the first, and only the passwd
# table names the second.
_GROUP_WITH_MEMBERS = _lines("docker:x:999:bob,alice")
_PASSWD_TABLE = _lines(
    "root:x:0:0:root:/root:/bin/bash",
    "builder:x:1001:999:CI builder:/home/builder:/bin/bash",
    "chad:x:1000:1000:Chad:/home/chad:/bin/bash",
)


def test_preflight_refuses_every_account_the_docker_group_admits() -> None:
    """A member of the group and an account whose PRIMARY group it is both count.

    Design R9 admits the Docker API to nobody but the guard until the
    commit point, and the socket's group is `docker` -- so an account in
    that group is a second party on the API during the window. The two
    kinds of membership live in two different tables, and an answer that
    read only the member list would pass a host whose CI builder has
    `docker` as its login group.
    """
    assert "docker_group_accounts" in importlib.import_module(_PREFLIGHT_MODULE).__all__
    preflight = importlib.import_module(_PREFLIGHT_MODULE)

    absent = _Commands(answers={preflight.GETENT_PASSWD_ARGV: _PASSWD_TABLE})
    assert preflight.docker_group_accounts(runner=absent) == ()
    assert tuple(absent.argvs) == (preflight.GETENT_GROUP_ARGV, preflight.GETENT_PASSWD_ARGV)
    assert set(absent.timeouts) == {preflight.PREFLIGHT_TIMEOUT_SECONDS}

    admitting = _Commands(
        answers={
            preflight.GETENT_GROUP_ARGV: _GROUP_WITH_MEMBERS,
            preflight.GETENT_PASSWD_ARGV: _PASSWD_TABLE,
        }
    )
    assert preflight.docker_group_accounts(runner=admitting) == ("alice", "bob", "builder")


def test_the_real_host_reads_the_docker_group_through_the_preflight(tmp_path: Path) -> None:
    """`HostOps.docker_group_members` is that same read, and nothing else.

    `reserve` and `arm` both refuse on a non-empty answer, so the seam
    the lifecycle calls has to be the read above rather than a second
    one that could disagree with it.
    """
    assert "docker_group_accounts" in importlib.import_module(_PREFLIGHT_MODULE).__all__
    preflight = importlib.import_module(_PREFLIGHT_MODULE)
    commands = _Commands(
        answers={
            preflight.GETENT_GROUP_ARGV: _GROUP_WITH_MEMBERS,
            preflight.GETENT_PASSWD_ARGV: _PASSWD_TABLE,
        }
    )

    host = _real_host(root=tmp_path, commands=commands)

    assert host.docker_group_members() == ("alice", "bob", "builder")


_RESYNC_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_resync"
_RESYNC_PATH = Path("livespec_dev_tooling/fleet/_docker_engine_guard_resync.py")

# `/etc/rancher/k3s/config.yaml` as the fleet writes it: a comment, a
# scalar setting, a scalar resync interval, and an argument LIST whose
# first entry is not a resync interval at all. Every one of those four
# shapes has to survive the parse, and the list entry that is not a
# sync period must not be read as one.
_K3S_CONFIG = _lines(
    "# gmktec k3s agent configuration -- owned by the k3s-on-gmktec plan",
    "server: https://poweredge-xubuntu:6443",
    "flannel-iptables-resync: 10s",
    "kube-proxy-arg:",
    "  - proxy-mode=iptables",
    "  - iptables-sync-period=45s",
)

# A drop-in declaring kube-router's own period BELOW its default, and a
# second one whose value is a typo. The typo is in the fixture on
# purpose: an unparseable duration is NOT an interval, and reading it as
# a zero would shorten the window to the margin alone.
_K3S_DROPIN_ROUTER = _lines(
    "kube-router-arg:",
    "  - iptables-sync-period=4m30s",
)
_K3S_DROPIN_TYPO = _lines(
    "kube-proxy-arg:",
    "  - iptables-sync-period=everyfiveminutes",
)

# A drop-in that puts a reconciler's period ABOVE every default, which
# is what makes the window longer than the measured 420 seconds.
_K3S_DROPIN_SLOW = _lines(
    "kube-router-arg:",
    "  - iptables-sync-period=7m",
)


def _k3s_tree(*, root: Path, dropins: dict[str, str], config: str = _K3S_CONFIG) -> dict[str, Path]:
    """A recorded `/etc/rancher/k3s` tree: the base file and its drop-ins."""
    root.mkdir(parents=True, exist_ok=True)
    base = root / "config.yaml"
    _ = base.write_text(config, encoding="utf-8")
    directory = root / "config.yaml.d"
    directory.mkdir(parents=True, exist_ok=True)
    for name, body in dropins.items():
        _ = (directory / name).write_text(body, encoding="utf-8")
    return {"config": base, "dropins": directory}


def test_the_resync_window_is_the_largest_effective_interval_plus_two_minutes(
    tmp_path: Path,
) -> None:
    """Every effective interval is recorded with its SOURCE, and the largest governs.

    Design R8 requires the window to be derived from the effective
    intervals recorded with their source, never from defaults alone --
    so a setting no file mentions is still recorded, as a component
    default, because it is still in force. The window is the largest of
    them plus two minutes, which is what makes one full resync period of
    the slowest reconciler fit inside the window with room to see its
    result.
    """
    assert _RESYNC_PATH.is_file()
    resync = importlib.import_module(_RESYNC_MODULE)
    tree = _k3s_tree(
        root=tmp_path / "ordinary",
        dropins={"10-router.yaml": _K3S_DROPIN_ROUTER, "20-typo.yaml": _K3S_DROPIN_TYPO},
    )

    intervals = resync.read_resync_intervals(config=tree["config"], dropins=tree["dropins"])

    assert {(one.setting, one.seconds, one.source) for one in intervals} == {
        ("flannel-iptables-resync", 5.0, resync.DEFAULT_SOURCE),
        ("kube-proxy-arg iptables-sync-period", 30.0, resync.DEFAULT_SOURCE),
        ("kube-router-arg iptables-sync-period", 300.0, resync.DEFAULT_SOURCE),
        ("flannel-iptables-resync", 10.0, str(tree["config"])),
        ("kube-proxy-arg iptables-sync-period", 45.0, str(tree["config"])),
        (
            "kube-router-arg iptables-sync-period",
            270.0,
            str(tree["dropins"] / "10-router.yaml"),
        ),
    }
    model = importlib.import_module(_MODEL_MODULE)
    assert resync.resync_window_seconds(intervals=intervals) == model.DEFAULT_WINDOW_SECONDS

    slow = _k3s_tree(root=tmp_path / "slow", dropins={"10-slow.yaml": _K3S_DROPIN_SLOW})
    slower = resync.read_resync_intervals(config=slow["config"], dropins=slow["dropins"])
    assert resync.resync_window_seconds(intervals=slower) == 420 + resync.WINDOW_MARGIN_SECONDS

    bare = tmp_path / "bare"
    bare.mkdir()
    defaults = resync.read_resync_intervals(
        config=bare / "config.yaml", dropins=bare / "config.yaml.d"
    )
    assert {one.source for one in defaults} == {resync.DEFAULT_SOURCE}
    assert resync.resync_window_seconds(intervals=defaults) == model.DEFAULT_WINDOW_SECONDS


def _preflight_bus(*, group: str = "", addresses: str = _ADDRESSES_CLEAR) -> _Commands:
    """A bus answering every read the whole preflight makes."""
    preflight = importlib.import_module(_PREFLIGHT_MODULE)
    return _Commands(
        answers={
            preflight.ADDRESS_SHOW_ARGV: addresses,
            preflight.ROUTE_SHOW_ARGV["ipv4"]: _ROUTES_CLEAR,
            preflight.ROUTE_SHOW_ARGV["ipv6"]: _ROUTES6,
            preflight.GETENT_GROUP_ARGV: group,
            preflight.GETENT_PASSWD_ARGV: _PASSWD_TABLE,
        }
    )


def test_the_preflight_refuses_a_resync_interval_above_five_minutes(tmp_path: Path) -> None:
    """Above five minutes the install is refused, and every refusal names its source.

    A reconciler slower than five minutes would need a window longer
    than the dead-man's budgets cover, so the install is refused rather
    than stretched to fit. The three refusal families compose into ONE
    answer because the preflight is one decision: an operator reading it
    on a machine reachable only over Tailscale needs every reason at
    once, not the first one in some order.
    """
    assert "preflight_refusals" in importlib.import_module(_PREFLIGHT_MODULE).__all__
    preflight = importlib.import_module(_PREFLIGHT_MODULE)
    resync = importlib.import_module(_RESYNC_MODULE)

    ordinary = _k3s_tree(
        root=tmp_path / "ordinary",
        dropins={"10-router.yaml": _K3S_DROPIN_ROUTER, "20-typo.yaml": _K3S_DROPIN_TYPO},
    )
    assert (
        preflight.preflight_refusals(
            runner=_preflight_bus(),
            declared=_DECLARED_CLEAR,
            config=ordinary["config"],
            dropins=ordinary["dropins"],
        )
        == ()
    )

    slow = _k3s_tree(root=tmp_path / "slow", dropins={"10-slow.yaml": _K3S_DROPIN_SLOW})
    assert preflight.preflight_refusals(
        runner=_preflight_bus(),
        declared=_DECLARED_CLEAR,
        config=slow["config"],
        dropins=slow["dropins"],
    ) == (
        f"kube-router-arg {resync.SYNC_PERIOD_ARGUMENT} is 420s in "
        f"{slow['dropins'] / '10-slow.yaml'}, above the {resync.MAX_RESYNC_SECONDS}s maximum",
    )

    every = preflight.preflight_refusals(
        runner=_preflight_bus(group=_GROUP_WITH_MEMBERS, addresses=_ADDRESSES_OVERLAPPING),
        declared=_DECLARED_OVERLAPPING,
        config=slow["config"],
        dropins=slow["dropins"],
    )
    assert every == (
        "172.17.0.0/16 overlaps the address 172.17.3.1/24 on br-lab",
        "172.17.0.0/16 overlaps the declared cluster pod CIDR 172.16.0.0/12",
        "these accounts are in the docker group and could reach the API: "
        "('alice', 'bob', 'builder')",
        f"kube-router-arg {resync.SYNC_PERIOD_ARGUMENT} is 420s in "
        f"{slow['dropins'] / '10-slow.yaml'}, above the {resync.MAX_RESYNC_SECONDS}s maximum",
    )


def test_the_real_host_answers_the_whole_preflight(tmp_path: Path) -> None:
    """The host layer the factory runs IS the preflight above, one delegation deep."""
    assert "preflight_refusals" in importlib.import_module(_PREFLIGHT_MODULE).__all__
    slow = _k3s_tree(root=tmp_path / "slow", dropins={"10-slow.yaml": _K3S_DROPIN_SLOW})
    resync = importlib.import_module(_RESYNC_MODULE)

    host = _real_host(root=tmp_path / "guard", commands=_preflight_bus())

    assert host.preflight_refusals(
        declared=_DECLARED_CLEAR, config=slow["config"], dropins=slow["dropins"]
    ) == (
        f"kube-router-arg {resync.SYNC_PERIOD_ARGUMENT} is 420s in "
        f"{slow['dropins'] / '10-slow.yaml'}, above the {resync.MAX_RESYNC_SECONDS}s maximum",
    )


_CLUSTER_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_cluster_probes"
_CLUSTER_PATH = Path("livespec_dev_tooling/fleet/_docker_engine_guard_cluster_probes.py")
_SAMPLE_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_sample"
_SAMPLE_PATH = Path("livespec_dev_tooling/fleet/_docker_engine_guard_sample.py")

# What the fleet's `docker_engine_must_stay_running` holds on gmktec:
# the LLM server, plus the k3s agent named a second time, which must not
# be read twice.
_MUST_STAY_RUNNING = ("local-homelab-llama-server.service", "k3s-agent.service")


def _active_state_argv(*, unit: str) -> tuple[str, ...]:
    """The service manager read of one unit's `ActiveState`."""
    return ("systemctl", "show", "--property", "ActiveState", "--value", unit)


def test_the_services_probe_requires_the_agent_the_tailnet_and_every_named_unit() -> None:
    """k3s-agent, tailscaled and every `docker_engine_must_stay_running` unit.

    These three are the host's own life: the CI pool agent, the only
    remote access path, and whatever else the fleet declared must not
    stop. A sample that passed with one of them inactive would confirm
    an install that had already taken the machine out of service.
    """
    assert _CLUSTER_PATH.is_file()
    assert _SAMPLE_PATH.is_file()
    cluster = importlib.import_module(_CLUSTER_MODULE)

    running = _Commands(
        answers={
            _active_state_argv(unit=unit): _lines("active")
            for unit in ("k3s-agent.service", "tailscaled.service", *_MUST_STAY_RUNNING)
        }
    )
    passing = cluster.services_probe(runner=running, must_stay_running=_MUST_STAY_RUNNING)
    assert (passing.name, passing.passed, passing.error) == (cluster.SERVICES_PROBE, True, "")
    assert tuple(running.argvs) == (
        _active_state_argv(unit="k3s-agent.service"),
        _active_state_argv(unit="tailscaled.service"),
        _active_state_argv(unit="local-homelab-llama-server.service"),
    )

    stopped = _Commands(
        answers={
            _active_state_argv(unit="k3s-agent.service"): _lines("active"),
            _active_state_argv(unit="tailscaled.service"): _lines("activating"),
            _active_state_argv(unit="local-homelab-llama-server.service"): _lines("failed"),
        }
    )
    failing = cluster.services_probe(runner=stopped, must_stay_running=_MUST_STAY_RUNNING)
    assert (failing.name, failing.passed) == (cluster.SERVICES_PROBE, False)
    assert failing.error == (
        "tailscaled.service is activating; local-homelab-llama-server.service is failed"
    )


# What `get --raw /api/v1/nodes/gmktec-xubuntu/status` answers. The
# second condition is in the fixture on purpose: the Ready condition has
# to be SELECTED by its type, not taken as the first or the only one.
_NODE_STATUS_READY = (
    '{"status": {"conditions": ['
    '{"type": "MemoryPressure", "status": "False"}, '
    '{"type": "Ready", "status": "True"}'
    "]}}"
)
_NODE_STATUS_NOT_READY = (
    '{"status": {"conditions": ['
    '{"type": "MemoryPressure", "status": "False"}, '
    '{"type": "Ready", "status": "Unknown"}'
    "]}}"
)


def test_the_node_ready_probe_reads_the_nodes_own_status_subresource() -> None:
    """Through the node-status credential, and through `get --raw` on that node.

    Design R8 is explicit about the instrument: the committed grant is
    `get`/`patch` on `nodes/status` for THIS node only, so the probe
    reads the node's own status subresource and attempts nothing else
    with that credential. It is reported as Node Ready and never
    substituted by a kubelet healthz, which answers that the kubelet is
    alive rather than that the cluster still has this node.
    """
    assert "node_ready_probe" in importlib.import_module(_CLUSTER_MODULE).__all__
    cluster = importlib.import_module(_CLUSTER_MODULE)
    argv = cluster.node_status_argv(node="gmktec-xubuntu")
    assert argv == (
        "k3s",
        "kubectl",
        "--kubeconfig",
        str(cluster.NODE_STATUS_KUBECONFIG),
        "get",
        "--raw",
        "/api/v1/nodes/gmktec-xubuntu/status",
    )

    ready = _Commands(answers={argv: _NODE_STATUS_READY})
    passing = cluster.node_ready_probe(runner=ready, node="gmktec-xubuntu")
    assert (passing.name, passing.passed, passing.error) == (cluster.NODE_READY_PROBE, True, "")
    assert tuple(ready.argvs) == (argv,)

    unknown = _Commands(answers={argv: _NODE_STATUS_NOT_READY})
    failing = cluster.node_ready_probe(runner=unknown, node="gmktec-xubuntu")
    assert (failing.passed, failing.error) == (
        False,
        "the node's Ready condition reads ('Unknown',)",
    )

    refused = _Commands(codes={argv: 1})
    unread = cluster.node_ready_probe(runner=refused, node="gmktec-xubuntu")
    assert (unread.passed, unread.error) == (False, "the node status read exited 1")


# `k3s kubectl get pods -n kube-system -o wide` on the k3s server. The
# header, a non-CoreDNS pod and a CoreDNS replica that is Terminating
# are all in the fixture: each is a row the placement read must not
# count, and each is wrong in a different way.
_KUBE_SYSTEM_WIDE_CROSS_NODE = _lines(
    "NAME                     READY STATUS      RESTARTS AGE IP          NODE              NOMINATED READINESS",
    "coredns-6b9d4d9d4d-ab1   1/1   Running     0        12d 10.42.0.88  poweredge-xubuntu <none>    <none>",
    "coredns-6b9d4d9d4d-ol1   0/1   Terminating 0        12d 10.42.3.9   gmktec-xubuntu    <none>    <none>",
    "local-path-provisioner-1 1/1   Running     0        12d 10.42.0.5   poweredge-xubuntu <none>    <none>",
)
_KUBE_SYSTEM_WIDE_SAME_NODE = _lines(
    "NAME                     READY STATUS      RESTARTS AGE IP          NODE              NOMINATED READINESS",
    "coredns-6b9d4d9d4d-ab1   1/1   Running     0        12d 10.42.3.14  gmktec-xubuntu    <none>    <none>",
)


def test_the_dns_placement_read_reports_a_same_node_backend_as_not_counting() -> None:
    """Every CoreDNS backend must be on ANOTHER node, read through the k3s server.

    CoreDNS is not pinned to a node, so a reschedule onto this one is
    ordinary cluster behaviour and not evidence about Docker -- design
    F7 therefore reports a same-node placement as "same-node" that does
    NOT count toward confirmation, rather than failing the sample and
    rolling back a healthy install. A read that found no running
    backend at all IS a failure: the cluster then has no DNS to prove
    anything with.
    """
    assert "dns_placement_probe" in importlib.import_module(_CLUSTER_MODULE).__all__
    cluster = importlib.import_module(_CLUSTER_MODULE)
    argv = cluster.coredns_placement_argv(server="poweredge-xubuntu")
    assert argv == (
        "ssh",
        "-o",
        "BatchMode=yes",
        "poweredge-xubuntu",
        "k3s",
        "kubectl",
        "get",
        "pods",
        "-n",
        "kube-system",
        "-o",
        "wide",
    )

    cross = _Commands(answers={argv: _KUBE_SYSTEM_WIDE_CROSS_NODE})
    assert cluster.coredns_nodes(runner=cross, server="poweredge-xubuntu") == ("poweredge-xubuntu",)
    elsewhere = cluster.dns_placement_probe(
        runner=cross, server="poweredge-xubuntu", node="gmktec-xubuntu"
    )
    assert (elsewhere.name, elsewhere.passed, elsewhere.error) == (
        cluster.DNS_PLACEMENT_PROBE,
        True,
        "",
    )
    assert elsewhere.counts_toward_confirmation is True

    here = _Commands(answers={argv: _KUBE_SYSTEM_WIDE_SAME_NODE})
    same = cluster.dns_placement_probe(
        runner=here, server="poweredge-xubuntu", node="gmktec-xubuntu"
    )
    assert (same.passed, same.counts_toward_confirmation) == (True, False)
    assert same.error == (
        "CoreDNS answers from this node ('gmktec-xubuntu',), so the DNS probe is same-node"
    )

    none = _Commands(answers={argv: _lines("NAME READY STATUS RESTARTS AGE IP NODE")})
    missing = cluster.dns_placement_probe(
        runner=none, server="poweredge-xubuntu", node="gmktec-xubuntu"
    )
    assert (missing.passed, missing.counts_toward_confirmation) == (False, True)
    assert missing.error == "no running CoreDNS backend was found through the k3s server"


# The route this fleet actually HAS from a k3s agent to its server, and
# the reason the prefix has to be declared at all: `sudo -u cwoolley -H
# ssh` reaches the server as the human the fleet provisions keys for, and
# the trailing `sudo` is what lets `k3s kubectl` there read
# `/etc/rancher/k3s/k3s.yaml`, which only root can read. It is the same
# shape `ansible/roles/node_status_credential/files/
# refresh-node-status-kubeconfig` already uses. Measured 2026-10-16:
# gmktec-xubuntu is the agent and poweredge-xubuntu the control plane,
# and no root-to-root ssh credential exists between them.
_DECLARED_K3S_SERVER_ROUTE = (
    "sudo",
    "-u",
    "cwoolley",
    "-H",
    "ssh",
    "-o",
    "BatchMode=yes",
    "poweredge-xubuntu",
    "sudo",
)


def test_the_dns_placement_read_reaches_the_k3s_server_through_a_declared_route() -> None:
    """The route to the k3s server is a PARAMETER of the placement read.

    The read delegates the pod listing to the server, so it needs a
    credential there, and which route carries one is a fact about the
    fleet rather than about the guard: this one reaches the server as a
    human user and elevates on the far side. A hard-wired root-to-root
    `ssh` works only where such a credential is provisioned, and this
    fleet provisions none, so the prefix is declared and the command it
    carries -- `PLACEMENT_COMMAND` -- is the part that never varies.

    An undeclared route keeps the previous `ssh -o BatchMode=yes
    <server>` prefix, so a run that says nothing about the route behaves
    exactly as it did before this parameter existed.
    """
    cluster = importlib.import_module(_CLUSTER_MODULE)
    assert "PLACEMENT_COMMAND" in cluster.__all__
    assert cluster.PLACEMENT_COMMAND == (
        "k3s",
        "kubectl",
        "get",
        "pods",
        "-n",
        "kube-system",
        "-o",
        "wide",
    )

    routed = cluster.coredns_placement_argv(
        server="poweredge-xubuntu", k3s_server_argv=_DECLARED_K3S_SERVER_ROUTE
    )
    assert routed == (*_DECLARED_K3S_SERVER_ROUTE, *cluster.PLACEMENT_COMMAND)
    assert cluster.coredns_placement_argv(server="poweredge-xubuntu") == (
        "ssh",
        "-o",
        "BatchMode=yes",
        "poweredge-xubuntu",
        *cluster.PLACEMENT_COMMAND,
    )

    bus = _Commands(answers={routed: _KUBE_SYSTEM_WIDE_CROSS_NODE})
    assert cluster.coredns_nodes(
        runner=bus, server="poweredge-xubuntu", k3s_server_argv=_DECLARED_K3S_SERVER_ROUTE
    ) == ("poweredge-xubuntu",)
    elsewhere = cluster.dns_placement_probe(
        runner=bus,
        server="poweredge-xubuntu",
        node="gmktec-xubuntu",
        k3s_server_argv=_DECLARED_K3S_SERVER_ROUTE,
    )
    assert (elsewhere.passed, elsewhere.counts_toward_confirmation) == (True, True)
    assert tuple(bus.argvs) == (routed, routed)
    assert set(bus.timeouts) == {cluster.PLACEMENT_TIMEOUT_SECONDS}


_POD_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_pod_probes"
_POD_PATH = Path("livespec_dev_tooling/fleet/_docker_engine_guard_pod_probes.py")

# `k3s crictl pods --state Ready -o json`: the service-load-balancer pod
# is HOST-network and must be skipped, and the CI job pod behind it is
# the one a probe may enter.
_READY_PODS = '{"items": [{"id": "svclb0001"}, {"id": "cijob0002"}]}'
_HOST_NETWORK_POD = (
    '{"status": {"linux": {"namespaces": {"options": {"network": "NODE"}}}},'
    ' "info": {"pid": 991}}'
)
_POD_NETWORK_POD = (
    '{"status": {"linux": {"namespaces": {"options": {"network": "POD"}}}},'
    ' "info": {"pid": 40127}}'
)


def _crictl_bus(*, pods: str = _READY_PODS) -> _Commands:
    """A bus answering the pod list and each sandbox's `inspectp`."""
    pod_probes = importlib.import_module(_POD_MODULE)
    return _Commands(
        answers={
            pod_probes.POD_LIST_ARGV: pods,
            pod_probes.inspect_pod_argv(sandbox="svclb0001"): _HOST_NETWORK_POD,
            pod_probes.inspect_pod_argv(sandbox="cijob0002"): _POD_NETWORK_POD,
        }
    )


def test_the_dns_probe_queries_kube_dns_from_the_pod_namespace_without_a_resolver() -> None:
    """The query goes to the kube-dns service address, from inside a pod's namespace.

    The pod's namespace has no resolver file, which is why design R8
    has the query SENT AND PARSED by a host script rather than by a
    resolver: a probe that called `getaddrinfo` there would fail for
    want of `/etc/resolv.conf` on a perfectly healthy host. A
    host-network pod is skipped, because entering one proves nothing
    about the pod network -- the network a Docker install can break.
    """
    assert _POD_PATH.is_file()
    pod_probes = importlib.import_module(_POD_MODULE)

    selected = _crictl_bus()
    assert pod_probes.pod_namespace_pid(runner=selected) == "40127"
    assert tuple(selected.argvs) == (
        pod_probes.POD_LIST_ARGV,
        pod_probes.inspect_pod_argv(sandbox="svclb0001"),
        pod_probes.inspect_pod_argv(sandbox="cijob0002"),
    )
    assert pod_probes.pod_namespace_pid(runner=_crictl_bus(pods='{"items": []}')) == ""

    argv = pod_probes.dns_probe_argv(pid="40127", server="10.43.0.10", name="kubernetes.default")
    assert argv[:5] == ("nsenter", "--target", "40127", "--net", "--")
    assert argv[5:7] == (sys.executable, "-c")
    assert argv[8:] == ("10.43.0.10", "kubernetes.default")
    script = argv[7]
    assert "socket.SOCK_DGRAM" in script
    assert "struct.unpack" in script
    for resolver in ("getaddrinfo", "gethostbyname", "resolv.conf"):
        assert resolver not in script

    passing = _Commands()
    answered = pod_probes.dns_probe(
        runner=passing, pid="40127", server="10.43.0.10", name="kubernetes.default"
    )
    assert (answered.name, answered.passed, answered.error) == (pod_probes.DNS_PROBE, True, "")
    assert tuple(passing.argvs) == (argv,)
    assert set(passing.timeouts) == {pod_probes.POD_PROBE_TIMEOUT_SECONDS}

    refusing = _Commands(codes={argv: 1})
    unanswered = pod_probes.dns_probe(
        runner=refusing, pid="40127", server="10.43.0.10", name="kubernetes.default"
    )
    assert (unanswered.passed, unanswered.error) == (
        False,
        "the DNS query to 10.43.0.10 from the pod namespace exited 1",
    )


def test_the_api_probe_completes_a_tls_handshake_to_the_api_service_clusterip() -> None:
    """A handshake, from the pod namespace, to the service ClusterIP.

    A handshake is the right depth for this probe: it proves the pod
    network carried a round trip through kube-proxy's service address
    and back, which is exactly the path Docker's FORWARD and masquerade
    rules sit in. It deliberately does NOT verify the server's identity
    -- no credential is involved -- because identity is what the Node
    Ready read proves, through the node-status kubeconfig.
    """
    assert "api_probe" in importlib.import_module(_POD_MODULE).__all__
    pod_probes = importlib.import_module(_POD_MODULE)

    argv = pod_probes.api_probe_argv(pid="40127", address="10.43.0.1", port=443)
    assert argv[:5] == ("nsenter", "--target", "40127", "--net", "--")
    assert argv[5:7] == (sys.executable, "-c")
    assert argv[8:] == ("10.43.0.1", "443")
    script = argv[7]
    assert "ssl.SSLContext" in script
    assert "wrap_socket" in script
    assert "version()" in script

    passing = _Commands()
    shook = pod_probes.api_probe(runner=passing, pid="40127", address="10.43.0.1", port=443)
    assert (shook.name, shook.passed, shook.error) == (pod_probes.API_PROBE, True, "")
    assert tuple(passing.argvs) == (argv,)
    assert set(passing.timeouts) == {pod_probes.POD_PROBE_TIMEOUT_SECONDS}

    refusing = _Commands(codes={argv: 124})
    unshaken = pod_probes.api_probe(runner=refusing, pid="40127", address="10.43.0.1", port=443)
    assert (unshaken.passed, unshaken.error) == (
        False,
        "the TLS handshake to 10.43.0.1:443 from the pod namespace exited 124",
    )


# `getent ahostsv4 archive.ubuntu.com` on the host. The second row is
# the same address under a different socket type, which is why only the
# FIRST row's address is taken.
_ARCHIVE_ADDRESSES = _lines(
    "185.125.190.83  STREAM archive.ubuntu.com",
    "185.125.190.83  DGRAM",
    "185.125.190.83  RAW",
)


def test_the_https_probe_resolves_on_the_host_then_sends_sni_explicitly() -> None:
    """Resolved on the HOST, connected from the pod namespace, SNI sent by hand.

    The pod namespace has no resolver, so the name is resolved on the
    host and only the ADDRESS crosses into the namespace -- which then
    makes the SNI something the probe has to send itself, because a
    connection opened to an address carries no name. Design R8 also
    fixes the endpoint: an Ubuntu archive mirror, which has no per-hour
    quota, rather than the GitHub API, which rate-limits an
    unauthenticated caller at sixty an hour and would start failing
    samples part way through a window.
    """
    assert "https_probe" in importlib.import_module(_POD_MODULE).__all__
    pod_probes = importlib.import_module(_POD_MODULE)
    resolve = pod_probes.resolve_argv(host=pod_probes.UBUNTU_ARCHIVE_HOST)
    assert resolve == ("getent", "ahostsv4", "archive.ubuntu.com")

    resolving = _Commands(answers={resolve: _ARCHIVE_ADDRESSES})
    assert (
        pod_probes.resolve_on_host(runner=resolving, host=pod_probes.UBUNTU_ARCHIVE_HOST)
        == "185.125.190.83"
    )
    assert pod_probes.resolve_on_host(runner=_Commands(), host="nowhere.invalid") == ""

    argv = pod_probes.https_probe_argv(
        pid="40127",
        address="185.125.190.83",
        host=pod_probes.UBUNTU_ARCHIVE_HOST,
        path=pod_probes.UBUNTU_ARCHIVE_PATH,
    )
    assert argv[:5] == ("nsenter", "--target", "40127", "--net", "--")
    assert argv[8:] == ("185.125.190.83", "archive.ubuntu.com", pod_probes.UBUNTU_ARCHIVE_PATH)
    script = argv[7]
    assert "server_hostname=host" in script
    assert "'HEAD '" in script

    passing = _Commands(answers={resolve: _ARCHIVE_ADDRESSES})
    reached = pod_probes.https_probe(runner=passing, pid="40127")
    assert (reached.name, reached.passed, reached.error) == (pod_probes.HTTPS_PROBE, True, "")
    assert tuple(passing.argvs) == (resolve, argv)

    unresolved = pod_probes.https_probe(runner=_Commands(), pid="40127")
    assert (unresolved.passed, unresolved.error) == (
        False,
        "archive.ubuntu.com did not resolve on the host",
    )

    refusing = _Commands(answers={resolve: _ARCHIVE_ADDRESSES}, codes={argv: 1})
    unreached = pod_probes.https_probe(runner=refusing, pid="40127")
    assert (unreached.passed, unreached.error) == (
        False,
        "the HEAD of https://archive.ubuntu.com/ubuntu/ from the pod namespace exited 1",
    )


_WITNESS_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_witness"
_WITNESS_PATH = Path("livespec_dev_tooling/fleet/_docker_engine_guard_witness.py")
_NETSTATE_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_netstate"

# The five watched values as gmktec reports them before the install
# (design, measured state 2026-10-15): forwarding on for both families,
# bridge-netfilter on for iptables and ip6tables, off for arptables.
_SYSCTLS_BEFORE = {
    "net.bridge.bridge-nf-call-arptables": "0",
    "net.bridge.bridge-nf-call-ip6tables": "1",
    "net.bridge.bridge-nf-call-iptables": "1",
    "net.ipv4.ip_forward": "1",
    "net.ipv6.conf.all.forwarding": "1",
}


def _sysctl_snapshot(*, root: Path, values: dict[str, str] = _SYSCTLS_BEFORE) -> Path:
    """A recorded `before/` directory holding the five watched sysctls."""
    netstate = importlib.import_module(_NETSTATE_MODULE)
    root.mkdir(parents=True, exist_ok=True)
    _ = (root / netstate.SYSCTL_SNAPSHOT).write_text(
        json.dumps(values, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return root


def _sysctl_bus(*, values: dict[str, str]) -> _Commands:
    """A bus answering `sysctl -n` for each watched value."""
    return _Commands(
        answers={("sysctl", "-n", name): _lines(value) for name, value in values.items()}
    )


def test_the_sysctl_probe_requires_the_five_watched_values_to_equal_the_snapshot(
    tmp_path: Path,
) -> None:
    """All five, against the snapshot taken before the first package step.

    A Docker install flips several of these, and a flipped one that
    survives is how k3s's pod network silently stops forwarding -- so
    the probe compares every sample against the recorded baseline
    rather than against what the value ought to be, because the
    baseline is the only record of what this host was.
    """
    assert _WITNESS_PATH.is_file()
    witness = importlib.import_module(_WITNESS_MODULE)
    snapshot = _sysctl_snapshot(root=tmp_path / "before")

    unchanged = witness.sysctl_probe(runner=_sysctl_bus(values=_SYSCTLS_BEFORE), snapshot=snapshot)
    assert (unchanged.name, unchanged.passed, unchanged.error) == (
        witness.SYSCTL_PROBE,
        True,
        "",
    )

    flipped = dict(_SYSCTLS_BEFORE)
    flipped["net.bridge.bridge-nf-call-iptables"] = "0"
    moved = witness.sysctl_probe(runner=_sysctl_bus(values=flipped), snapshot=snapshot)
    assert (moved.passed, moved.error) == (
        False,
        "net.bridge.bridge-nf-call-iptables 1 -> 0",
    )


@dataclass(kw_only=True)
class _ScriptedProbe:
    """A probe answering a recorded verdict per call, and counting its calls."""

    verdicts: list[bool]
    calls: int = 0

    def __call__(self) -> Any:
        sample_module = importlib.import_module(_SAMPLE_MODULE)
        passed = self.verdicts[self.calls]
        self.calls += 1
        return sample_module.ProbeResult(
            name="dns",
            passed=passed,
            error="" if passed else f"attempt {self.calls} saw no answer",
        )


def test_a_failed_probe_is_re_run_once_and_counts_as_failed_only_when_it_fails_twice() -> None:
    """One immediate retry, and BOTH errors recorded when the retry fails too.

    A single failed request is not evidence that Docker broke anything:
    this host runs a CI pool whose pods come and go, CoreDNS restarts,
    and a fifteen-second sampling interval will catch one of those
    moments sooner or later. A window that rolled back on the first
    one would never confirm an install. Both attempts' errors are
    recorded, because "it failed twice the same way" and "it failed
    twice differently" point an operator at different causes.
    """
    assert "run_probe" in importlib.import_module(_SAMPLE_MODULE).__all__
    sample_module = importlib.import_module(_SAMPLE_MODULE)

    first_time = _ScriptedProbe(verdicts=[True, True])
    assert sample_module.run_probe(probe=first_time).passed is True
    assert first_time.calls == 1

    retried = _ScriptedProbe(verdicts=[False, True])
    recovered = sample_module.run_probe(probe=retried)
    assert (recovered.passed, recovered.error) == (True, "")
    assert retried.calls == 2

    twice = _ScriptedProbe(verdicts=[False, False])
    failed = sample_module.run_probe(probe=twice)
    assert (failed.name, failed.passed) == ("dns", False)
    assert failed.error == "attempt 1 saw no answer; then attempt 2 saw no answer"
    assert twice.calls == 2


def test_every_probe_failure_is_recorded_with_its_probe_name_and_its_error() -> None:
    """One sample record: every result, every failure named, one `passed` verdict.

    The failure list is what an operator has after a rolled-back run,
    and it is the only thing that tells "Docker broke the pod network"
    from "CoreDNS restarted" -- so each entry carries the probe's own
    name and its own error rather than a count. The record also carries
    whether the sample counts toward confirmation, which is NOT the
    same as whether it passed: a same-node DNS placement passes and
    proves nothing.
    """
    assert "build_sample" in importlib.import_module(_SAMPLE_MODULE).__all__
    sample_module = importlib.import_module(_SAMPLE_MODULE)

    def _passing() -> Any:
        return sample_module.ProbeResult(name="services", passed=True)

    def _failing() -> Any:
        return sample_module.ProbeResult(name="dns", passed=False, error="no answer")

    def _uncounted() -> Any:
        return sample_module.ProbeResult(
            name="dns-placement", passed=True, counts_toward_confirmation=False
        )

    whole = sample_module.build_sample(probes=(_passing, _uncounted))
    assert whole[sample_module.PASSED_KEY] is True
    assert whole[sample_module.COUNTS_KEY] is False
    assert whole[sample_module.PROBES_KEY] == (
        {"name": "services", "passed": True, "error": "", "counts_toward_confirmation": True},
        {
            "name": "dns-placement",
            "passed": True,
            "error": "",
            "counts_toward_confirmation": False,
        },
    )
    assert whole[sample_module.FAILURES_KEY] == ()

    broken = sample_module.build_sample(probes=(_passing, _failing))
    assert broken[sample_module.PASSED_KEY] is False
    assert broken[sample_module.COUNTS_KEY] is True
    assert broken[sample_module.FAILURES_KEY] == (
        {"probe": "dns", "error": "no answer; then no answer"},
    )


def _proc_tree(*, root: Path, cgroups: dict[str, str]) -> Path:
    """A recorded `/proc` holding one `cgroup` file per named process."""
    for pid, line in cgroups.items():
        directory = root / pid
        directory.mkdir(parents=True, exist_ok=True)
        _ = (directory / "cgroup").write_text(_lines(line), encoding="utf-8")
    return root


# `pgrep --exact containerd` once the install has run: Docker's own
# containerd, a PID that has since exited, and k3s's. Only the last one
# is the witness, and the first is the reason the cgroup is read at all
# -- after the install there are two processes with this exact name.
_CONTAINERD_PIDS = _lines("991", "40001", "512")
_CONTAINERD_CGROUPS = {
    "991": "0::/system.slice/containerd.service",
    "512": "0::/system.slice/k3s-agent.service",
}


def test_the_k3s_witness_fails_a_sample_when_the_pid_moved_or_a_path_is_missing(
    tmp_path: Path,
) -> None:
    """k3s-agent's own containerd PID, and its two shim directories.

    Design F8 drops the shim-survival assertion -- CI pods legitimately
    come and go -- and asserts instead what Docker CLEANUP could
    actually damage: the containerd k3s runs keeps its PID across the
    window, and the two directories its shims keep sockets and runc
    state in still exist. The PID is found through the process's own
    cgroup and not by name, because after the install there are TWO
    processes called `containerd` on this host and killing the wrong
    one is the lockout the guard exists to prevent.
    """
    assert "k3s_witness_probe" in importlib.import_module(_WITNESS_MODULE).__all__
    witness = importlib.import_module(_WITNESS_MODULE)
    proc = _proc_tree(root=tmp_path / "proc", cgroups=_CONTAINERD_CGROUPS)
    running = _Commands(answers={witness.PGREP_CONTAINERD_ARGV: _CONTAINERD_PIDS})
    assert witness.containerd_pid(runner=running, proc_root=proc) == "512"
    assert tuple(running.argvs) == (witness.PGREP_CONTAINERD_ARGV,)
    assert witness.containerd_pid(runner=_Commands(), proc_root=proc) == ""

    snapshot = tmp_path / "before"
    witness.write_witness_snapshot(destination=snapshot, runner=running, proc_root=proc)
    shims = _proc_tree(root=tmp_path / "shims", cgroups={})
    for directory in ("s", "runc/k8s.io"):
        (shims / directory).mkdir(parents=True, exist_ok=True)
    present = (shims / "s", shims / "runc/k8s.io")

    unmoved = witness.k3s_witness_probe(
        runner=_Commands(answers={witness.PGREP_CONTAINERD_ARGV: _CONTAINERD_PIDS}),
        snapshot=snapshot,
        proc_root=proc,
        containerd_paths=present,
    )
    assert (unmoved.name, unmoved.passed, unmoved.error) == (
        witness.K3S_WITNESS_PROBE,
        True,
        "",
    )

    restarted = _proc_tree(
        root=tmp_path / "restarted",
        cgroups={"777": "0::/system.slice/k3s-agent.service"},
    )
    moved = witness.k3s_witness_probe(
        runner=_Commands(answers={witness.PGREP_CONTAINERD_ARGV: _lines("777")}),
        snapshot=snapshot,
        proc_root=restarted,
        containerd_paths=present,
    )
    assert (moved.passed, moved.error) == (
        False,
        "k3s-agent's containerd PID moved from 512 to 777",
    )

    gone = witness.k3s_witness_probe(
        runner=_Commands(answers={witness.PGREP_CONTAINERD_ARGV: _CONTAINERD_PIDS}),
        snapshot=snapshot,
        proc_root=proc,
        containerd_paths=(shims / "s", shims / "runc" / "absent"),
    )
    assert (gone.passed, gone.error) == (
        False,
        f"these k3s containerd paths are missing: ('{shims / 'runc' / 'absent'}',)",
    )


_SCOPE_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_scope"
_SCOPE_PATH = Path("livespec_dev_tooling/fleet/_docker_engine_guard_scope.py")

# What `systemctl show -p ControlGroup fabro-sandbox.slice` answers on
# this fleet: the slice is NESTED under `fabro.slice`, which is why the
# path is resolved rather than written down (design R8).
_SANDBOX_CONTROL_GROUP = "/fabro.slice/fabro-sandbox.slice"


def test_the_canarys_cgroup_is_resolved_through_the_sandbox_slices_control_group(
    tmp_path: Path,
) -> None:
    """Through `systemctl show -p ControlGroup`, never against a literal path.

    The sandbox slice is NESTED on this fleet -- its control group is
    `/fabro.slice/fabro-sandbox.slice` -- so a probe comparing the
    canary's cgroup with a hand-written `/fabro-sandbox.slice` would
    fail every sample of a correctly-configured host, and one comparing
    with a bare suffix would pass a container the daemon had placed
    somewhere else entirely.
    """
    assert _SCOPE_PATH.is_file()
    scope = importlib.import_module(_SCOPE_MODULE)
    assert scope.CONTROL_GROUP_ARGV == (
        "systemctl",
        "show",
        "-p",
        "ControlGroup",
        "--value",
        "fabro-sandbox.slice",
    )
    pid_argv = scope.canary_pid_argv(canary="docker-engine-guard-canary")
    assert pid_argv == (
        "docker",
        "inspect",
        "--format",
        "{{.State.Pid}}",
        "docker-engine-guard-canary",
    )

    def _bus() -> _Commands:
        return _Commands(
            answers={
                scope.CONTROL_GROUP_ARGV: _lines(_SANDBOX_CONTROL_GROUP),
                pid_argv: _lines("7211"),
            }
        )

    inside = _proc_tree(
        root=tmp_path / "inside",
        cgroups={"7211": f"0::{_SANDBOX_CONTROL_GROUP}/docker-abc123.scope"},
    )
    placed = scope.canary_cgroup_probe(
        runner=_bus(), canary="docker-engine-guard-canary", proc_root=inside
    )
    assert (placed.name, placed.passed, placed.error) == (scope.CANARY_CGROUP_PROBE, True, "")

    outside = _proc_tree(
        root=tmp_path / "outside",
        cgroups={"7211": "0::/system.slice/docker.service/docker-abc123.scope"},
    )
    misplaced = scope.canary_cgroup_probe(
        runner=_bus(), canary="docker-engine-guard-canary", proc_root=outside
    )
    assert (misplaced.passed, misplaced.error) == (
        False,
        "the canary's cgroup is 0::/system.slice/docker.service/docker-abc123.scope, "
        f"not under {_SANDBOX_CONTROL_GROUP}",
    )

    unread = scope.canary_cgroup_probe(
        runner=_bus(), canary="docker-engine-guard-canary", proc_root=tmp_path / "empty"
    )
    assert (unread.passed, unread.error) == (
        False,
        f"the canary's cgroup is unreadable, not under {_SANDBOX_CONTROL_GROUP}",
    )


def test_a_sample_fails_on_any_container_or_network_outside_the_guarded_scope() -> None:
    """Only the canary, and only Docker's three built-in networks.

    Design R9 admits the Docker API to nobody but the guard until the
    commit point, so a second container or a fourth network means
    something else reached the socket. It matters because the
    rollback's cleanup is `docker0`-only: anything outside that scope
    survives a rollback that would otherwise report a complete
    recovery, so the sample fails and the run records that its cleanup
    may not cover what it found.
    """
    assert "exclusive_scope_probe" in importlib.import_module(_SCOPE_MODULE).__all__
    scope = importlib.import_module(_SCOPE_MODULE)
    assert scope.CONTAINER_LIST_ARGV == (
        "docker",
        "ps",
        "--all",
        "--no-trunc",
        "--format",
        "{{.Names}}",
    )
    assert scope.NETWORK_LIST_ARGV == ("docker", "network", "ls", "--format", "{{.Name}}")

    def _bus(*, containers: tuple[str, ...], networks: tuple[str, ...]) -> _Commands:
        return _Commands(
            answers={
                scope.CONTAINER_LIST_ARGV: _lines(*containers),
                scope.NETWORK_LIST_ARGV: _lines(*networks),
            }
        )

    alone = _bus(containers=("docker-engine-guard-canary",), networks=("bridge", "host", "none"))
    exclusive = scope.exclusive_scope_probe(runner=alone, canary="docker-engine-guard-canary")
    assert (exclusive.name, exclusive.passed, exclusive.error) == (
        scope.EXCLUSIVE_SCOPE_PROBE,
        True,
        "",
    )
    assert tuple(alone.argvs) == (scope.CONTAINER_LIST_ARGV, scope.NETWORK_LIST_ARGV)

    crowded = _bus(
        containers=("docker-engine-guard-canary", "fabro-sandbox-01M5"),
        networks=("bridge", "host", "none", "fabro_default"),
    )
    shared = scope.exclusive_scope_probe(runner=crowded, canary="docker-engine-guard-canary")
    assert (shared.passed, shared.error) == (
        False,
        "containers other than the canary exist: ('fabro-sandbox-01M5',); "
        "Docker networks beyond the built-in three exist: ('fabro_default',)",
    )


# `ip -o link show` on the host before the install: k3s's own bridge and
# flannel link are in it, which is why the comparison is against the
# RECORDED set and not against a list of names the guard knows.
_LINKS_BEFORE = _lines(
    "1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN",
    "2: enp2s0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc mq state UP",
    "3: tailscale0: <POINTOPOINT,MULTICAST,NOARP,UP,LOWER_UP> mtu 1280 state UNKNOWN",
    "4: cni0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1450 qdisc noqueue state UP",
    "5: flannel.1: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1450 state UNKNOWN",
    "6: vethf00d01@if3: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1450 master cni0 state UP",
)

# The same read during the window: Docker's bridge and the canary's one
# veth pair have appeared, and nothing else.
_LINKS_WITH_CANARY = _LINKS_BEFORE + _lines(
    "11: docker0: <NO-CARRIER,BROADCAST,MULTICAST,UP> mtu 1500 qdisc noqueue state DOWN",
    "12: veth9f0c1d@if2: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 master docker0 state UP",
)

# And the same read on a host where something else made an interface
# during the window -- outside the `docker0`-only cleanup entirely.
_LINKS_WITH_INTRUDER = _LINKS_WITH_CANARY + _lines(
    "13: br-lab: <NO-CARRIER,BROADCAST,MULTICAST,UP> mtu 1500 qdisc noqueue state DOWN",
)

# The same read on a CI node whose pods start during the window: every
# pod adds a veth on `cni0`, k3s's bridge, which the pre-install read
# above already recorded. Measured 2026-10-18 on gmktec-xubuntu, where
# EIGHTEEN of these appeared inside one window and rolled the run back
# (gate 20261018T030444Z-3778031, run r2026101803080120e0).
_LINKS_WITH_POD_VETHS = _LINKS_WITH_CANARY + _lines(
    "14: veth13671da9@if3: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1450 master cni0 state UP",
    "15: veth1c9e020c@if3: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1450 master cni0 state UP",
)

# And the same read with a SECOND veth on `docker0`: a Docker-side
# endpoint that is not the canary's, which is the thing the probe is for.
_LINKS_WITH_SECOND_DOCKER_VETH = _LINKS_WITH_POD_VETHS + _lines(
    "16: veth4d2b17c8@if9: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 master docker0 state UP",
)

# And with a bridge something else made while the pods churned: not a
# veth, mastered by nothing, outside the `docker0`-only cleanup entirely.
_LINKS_WITH_POD_VETHS_AND_BRIDGE = _LINKS_WITH_POD_VETHS + _lines(
    "17: br-lab: <NO-CARRIER,BROADCAST,MULTICAST,UP> mtu 1500 qdisc noqueue state DOWN",
)

# The canary's OWN view of its namespace: its `eth0` names the host-side
# index of its veth pair after `@if`, which is how the pair is
# identified by the canary's endpoint rather than guessed from a name.
_CANARY_LINKS = _lines(
    "1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN",
    "2: eth0@if12: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 state UP",
)


def test_a_sample_fails_on_an_interface_that_appeared_outside_the_guarded_pair(
    tmp_path: Path,
) -> None:
    """`docker0` and the canary's ONE veth pair are expected; anything else is not.

    The pair is identified by the canary's own endpoint -- its `eth0`
    names the host-side index after `@if` -- because a veth's host-side
    name is random and a name-prefix match would either miss it or
    sweep in `flannel.1` and `vethf00d01`, links k3s's pod network runs
    over.
    """
    assert "interface_probe" in importlib.import_module(_WITNESS_MODULE).__all__
    witness = importlib.import_module(_WITNESS_MODULE)
    scope = importlib.import_module(_SCOPE_MODULE)
    netstate = importlib.import_module(_NETSTATE_MODULE)

    inside = _Commands(
        answers={
            tuple(scope.canary_link_argv(pid="7211")): _CANARY_LINKS,
        }
    )
    assert scope.canary_veth_index(runner=inside, pid="7211") == "12"
    assert scope.canary_veth_index(runner=_Commands(), pid="7211") == ""

    snapshot = tmp_path / "before"
    witness.write_interface_snapshot(
        destination=snapshot, runner=_Commands(answers={netstate.LINK_SHOW_ARGV: _LINKS_BEFORE})
    )

    expected = witness.interface_probe(
        runner=_Commands(answers={netstate.LINK_SHOW_ARGV: _LINKS_WITH_CANARY}),
        snapshot=snapshot,
        canary_veth_index="12",
    )
    assert (expected.name, expected.passed, expected.error) == (
        witness.INTERFACE_PROBE,
        True,
        "",
    )

    unidentified = witness.interface_probe(
        runner=_Commands(answers={netstate.LINK_SHOW_ARGV: _LINKS_WITH_CANARY}),
        snapshot=snapshot,
        canary_veth_index="",
    )
    assert (unidentified.passed, unidentified.error) == (
        False,
        "these interfaces appeared since the snapshot: ('veth9f0c1d',)",
    )

    intruded = witness.interface_probe(
        runner=_Commands(answers={netstate.LINK_SHOW_ARGV: _LINKS_WITH_INTRUDER}),
        snapshot=snapshot,
        canary_veth_index="12",
    )
    assert (intruded.passed, intruded.error) == (
        False,
        "these interfaces appeared since the snapshot: ('br-lab',)",
    )


# Every interface name the pre-install read above carries, which is what
# the snapshot records and all it records: the master is read live at
# sample time and compared with these NAMES, so the recorded file needs
# no new field and no format change.
_SNAPSHOT_NAMES = ["cni0", "enp2s0", "flannel.1", "lo", "tailscale0", "vethf00d01"]


def test_the_interface_reader_records_each_interface_s_master(tmp_path: Path) -> None:
    """The reader carries the `master` column; the snapshot still carries names only.

    The master is what tells a veth k3s's pod network made from one
    Docker made: both appear during the window and only the second is
    the guard's to find. It is carried on the READ rather than written
    into the snapshot because the question a sample asks is about the
    master an interface has NOW -- "is it a bridge this host already
    had" -- which the recorded names answer on their own.
    """
    witness = importlib.import_module(_WITNESS_MODULE)
    netstate = importlib.import_module(_NETSTATE_MODULE)
    assert "HostLink" in witness.__all__

    links = witness.read_links(runner=_Commands(answers={netstate.LINK_SHOW_ARGV: _LINKS_BEFORE}))
    assert {index: (link.name, link.master) for index, link in links.items()} == {
        "1": ("lo", ""),
        "2": ("enp2s0", ""),
        "3": ("tailscale0", ""),
        "4": ("cni0", ""),
        "5": ("flannel.1", ""),
        "6": ("vethf00d01", "cni0"),
    }

    snapshot = tmp_path / "before"
    witness.write_interface_snapshot(
        destination=snapshot, runner=_Commands(answers={netstate.LINK_SHOW_ARGV: _LINKS_BEFORE})
    )
    recorded = json.loads((snapshot / witness.INTERFACE_SNAPSHOT).read_text(encoding="utf-8"))
    assert recorded == _SNAPSHOT_NAMES


def test_a_sample_ignores_pod_veths_on_a_bridge_the_snapshot_recorded(tmp_path: Path) -> None:
    """A veth that joined a RECORDED bridge is k3s's churn; one on `docker0` is not.

    This is the interface counterpart of the firewall comparison's
    `KUBE-*` / `FLANNEL-*` carve-out: a CI node admits pods while the
    window runs and each one adds a veth to `cni0`, so a rule that
    failed on any new interface failed EVERY window on the only kind of
    host the guard is for -- measured on gmktec-xubuntu, where 18 pod
    veths rolled a clean install back.

    The bridge is attested by the RECORDED NAME and nothing else: a
    master this host already had is a subsystem that was already
    running, while `docker0` is absent from every snapshot the preflight
    takes, so Docker's own veths keep failing the sample and keep being
    named. A new interface mastered by nothing -- a bridge, another
    subsystem's link -- is outside the `docker0`-only cleanup entirely
    and still fails.
    """
    witness = importlib.import_module(_WITNESS_MODULE)
    netstate = importlib.import_module(_NETSTATE_MODULE)

    snapshot = tmp_path / "before"
    witness.write_interface_snapshot(
        destination=snapshot, runner=_Commands(answers={netstate.LINK_SHOW_ARGV: _LINKS_BEFORE})
    )

    churning = witness.interface_probe(
        runner=_Commands(answers={netstate.LINK_SHOW_ARGV: _LINKS_WITH_POD_VETHS}),
        snapshot=snapshot,
        canary_veth_index="12",
    )
    assert (churning.name, churning.passed, churning.error) == (
        witness.INTERFACE_PROBE,
        True,
        "",
    )

    docker_side = witness.interface_probe(
        runner=_Commands(answers={netstate.LINK_SHOW_ARGV: _LINKS_WITH_SECOND_DOCKER_VETH}),
        snapshot=snapshot,
        canary_veth_index="12",
    )
    assert (docker_side.passed, docker_side.error) == (
        False,
        "these interfaces appeared since the snapshot: ('veth4d2b17c8',)",
    )

    unmastered = witness.interface_probe(
        runner=_Commands(answers={netstate.LINK_SHOW_ARGV: _LINKS_WITH_POD_VETHS_AND_BRIDGE}),
        snapshot=snapshot,
        canary_veth_index="12",
    )
    assert (unmastered.passed, unmastered.error) == (
        False,
        "these interfaces appeared since the snapshot: ('br-lab',)",
    )


_FIREWALL_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_sample_firewall"
_FIREWALL_PATH = Path("livespec_dev_tooling/fleet/_docker_engine_guard_sample_firewall.py")
_ACTIONS_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_firewall_actions"

# The guarded host's `filter` table before the install: Tailscale's two
# chains and a kube-proxy chain, each with contents of its own.
_FILTER_BEFORE = _lines(
    "*filter",
    ":INPUT ACCEPT [0:0]",
    ":FORWARD DROP [0:0]",
    ":OUTPUT ACCEPT [0:0]",
    ":KUBE-SERVICES - [0:0]",
    ":ts-forward - [0:0]",
    ":ts-input - [0:0]",
    "-A INPUT -j ts-input",
    "-A INPUT -j KUBE-SERVICES",
    "-A FORWARD -j ts-forward",
    "-A ts-input -i tailscale0 -j ACCEPT",
    "-A KUBE-SERVICES -d 10.43.0.1/32 -j ACCEPT",
    "COMMIT",
)

# The same table during a HEALTHY window. Docker's own chains and rules
# are there, and so is one further rule kube-proxy added INSIDE its own
# chain -- the reconciler churn R4 says must never be mistaken for a
# fault.
_FILTER_HEALTHY = _lines(
    "*filter",
    ":INPUT ACCEPT [0:0]",
    ":FORWARD DROP [0:0]",
    ":OUTPUT ACCEPT [0:0]",
    ":KUBE-SERVICES - [0:0]",
    ":ts-forward - [0:0]",
    ":ts-input - [0:0]",
    ":DOCKER - [0:0]",
    ":DOCKER-USER - [0:0]",
    "-A INPUT -j ts-input",
    "-A INPUT -j KUBE-SERVICES",
    "-A FORWARD -j ts-forward",
    "-A FORWARD -o docker0 -j DOCKER",
    "-A FORWARD -i docker0 ! -o docker0 -j ACCEPT",
    "-A DOCKER-USER -j RETURN",
    "-A ts-input -i tailscale0 -j ACCEPT",
    "-A KUBE-SERVICES -d 10.43.0.1/32 -j ACCEPT",
    "-A KUBE-SERVICES -d 10.43.0.17/32 -j ACCEPT",
    "COMMIT",
)

# And during a window that went wrong in all three in-scope ways: a
# built-in policy moved, a rule appeared in a built-in chain that is
# not Docker's, and a Tailscale chain lost one of its own.
_FILTER_FAULTY = _lines(
    "*filter",
    ":INPUT ACCEPT [0:0]",
    ":FORWARD ACCEPT [0:0]",
    ":OUTPUT ACCEPT [0:0]",
    ":KUBE-SERVICES - [0:0]",
    ":ts-forward - [0:0]",
    ":ts-input - [0:0]",
    ":DOCKER - [0:0]",
    "-A INPUT -j ts-input",
    "-A INPUT -j KUBE-SERVICES",
    "-A INPUT -p tcp -m tcp --dport 2375 -j ACCEPT",
    "-A FORWARD -j ts-forward",
    "-A FORWARD -o docker0 -j DOCKER",
    "-A KUBE-SERVICES -d 10.43.0.1/32 -j ACCEPT",
    "COMMIT",
)

_NAT_BEFORE = _lines(
    "*nat",
    ":PREROUTING ACCEPT [0:0]",
    ":POSTROUTING ACCEPT [0:0]",
    ":KUBE-POSTROUTING - [0:0]",
    "-A POSTROUTING -s 10.42.0.0/16 -j MASQUERADE",
    "COMMIT",
)
_NAT_HEALTHY = _lines(
    "*nat",
    ":PREROUTING ACCEPT [0:0]",
    ":POSTROUTING ACCEPT [0:0]",
    ":KUBE-POSTROUTING - [0:0]",
    ":DOCKER - [0:0]",
    "-A POSTROUTING -s 10.42.0.0/16 -j MASQUERADE",
    "-A POSTROUTING -s 172.17.0.0/16 ! -o docker0 -j MASQUERADE",
    "-A PREROUTING -m addrtype --dst-type LOCAL -j DOCKER",
    "COMMIT",
)
_IPV6_FILTER = _lines(
    "*filter",
    ":INPUT ACCEPT [0:0]",
    ":FORWARD ACCEPT [0:0]",
    ":OUTPUT ACCEPT [0:0]",
    "COMMIT",
)
_IPV6_NAT = _lines(
    "*nat",
    ":PREROUTING ACCEPT [0:0]",
    ":POSTROUTING ACCEPT [0:0]",
    "COMMIT",
)


def _firewall_snapshot(*, root: Path) -> Path:
    """A recorded `before/` directory holding both families' two tables."""
    firewall = importlib.import_module("livespec_dev_tooling.fleet._docker_engine_guard_firewall")
    root.mkdir(parents=True, exist_ok=True)
    recorded = {
        ("ipv4", "filter"): _FILTER_BEFORE,
        ("ipv4", "nat"): _NAT_BEFORE,
        ("ipv6", "filter"): _IPV6_FILTER,
        ("ipv6", "nat"): _IPV6_NAT,
    }
    for (family, table), dump in recorded.items():
        _ = (root / firewall.snapshot_name(family=family, table=table)).write_text(
            dump, encoding="utf-8"
        )
    return root


def _firewall_bus(*, ipv4_filter: str) -> _Commands:
    """A bus answering each family's two `*-save` reads."""
    firewall = importlib.import_module("livespec_dev_tooling.fleet._docker_engine_guard_firewall")
    return _Commands(
        answers={
            firewall.save_argv(family="ipv4", table="filter"): ipv4_filter,
            firewall.save_argv(family="ipv4", table="nat"): _NAT_HEALTHY,
            firewall.save_argv(family="ipv6", table="filter"): _IPV6_FILTER,
            firewall.save_argv(family="ipv6", table="nat"): _IPV6_NAT,
        }
    )


def test_the_sample_firewall_comparison_covers_the_scope_r4_fixed_and_no_more(
    tmp_path: Path,
) -> None:
    """Built-in policies, the five built-in chains' rules, `ts-*` contents -- and no more.

    R4 scopes the comparison so a reconciler's healthy churn is never
    mistaken for a fault: kube-router and kube-proxy rewrite the
    contents of their own `KUBE-*` and `FLANNEL-*` chains per pod, so a
    comparison covering those would fail on every sample of a perfectly
    healthy host. Docker's OWN footprint is excluded too -- the engine
    is expected to be running during the window -- so what is left is
    exactly what nobody should have changed.
    """
    assert _FIREWALL_PATH.is_file()
    sample_firewall = importlib.import_module(_FIREWALL_MODULE)
    actions = importlib.import_module(_ACTIONS_MODULE)
    snapshot = _firewall_snapshot(root=tmp_path / "before")

    healthy = _firewall_bus(ipv4_filter=_FILTER_HEALTHY)
    passing = sample_firewall.firewall_probe(runner=healthy, snapshot=snapshot)
    assert (passing.name, passing.passed, passing.error) == (
        sample_firewall.FIREWALL_PROBE,
        True,
        "",
    )
    assert set(healthy.timeouts) == {actions.FIREWALL_TIMEOUT_SECONDS}
    assert healthy.argvs_with(flag="-c") == ()

    faulty = _firewall_bus(ipv4_filter=_FILTER_FAULTY)
    failing = sample_firewall.firewall_probe(runner=faulty, snapshot=snapshot)
    assert failing.passed is False
    assert failing.error == (
        "ipv4 filter policy FORWARD: DROP -> ACCEPT; "
        "ipv4 filter appeared -A INPUT -p tcp -m tcp --dport 2375 -j ACCEPT; "
        "ipv4 filter disappeared -A ts-input -i tailscale0 -j ACCEPT"
    )


_PROBE_SET_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_probe_set"
_PROBE_SET_PATH = Path("livespec_dev_tooling/fleet/_docker_engine_guard_probe_set.py")

# The probe parameters the controller uploads into the run's own inputs
# directory, and that `publish` installs into place.
_PROBE_PARAMETERS = {
    "api_address": "10.43.0.1",
    "api_port": 443,
    "canary": "docker-engine-guard-canary",
    "dns_name": "kubernetes.default.svc.cluster.local",
    "k3s_server": "poweredge-xubuntu",
    "kube_dns_address": "10.43.0.10",
    "must_stay_running": ["local-homelab-llama-server.service", "k3s-agent.service"],
    "node": "gmktec-xubuntu",
}

_RUN = "run-a"


def _before_bus() -> _Commands:
    """Every read the preflight snapshot takes, on the host before the install."""
    firewall = importlib.import_module("livespec_dev_tooling.fleet._docker_engine_guard_firewall")
    netstate = importlib.import_module(_NETSTATE_MODULE)
    witness = importlib.import_module(_WITNESS_MODULE)
    answers: dict[tuple[str, ...], str] = {
        firewall.save_argv(family="ipv4", table="filter"): _FILTER_BEFORE,
        firewall.save_argv(family="ipv4", table="nat"): _NAT_BEFORE,
        firewall.save_argv(family="ipv6", table="filter"): _IPV6_FILTER,
        firewall.save_argv(family="ipv6", table="nat"): _IPV6_NAT,
        netstate.LINK_SHOW_ARGV: _LINKS_BEFORE,
        witness.PGREP_CONTAINERD_ARGV: _CONTAINERD_PIDS,
    }
    answers.update(
        {("sysctl", "-n", name): _lines(value) for name, value in _SYSCTLS_BEFORE.items()}
    )
    return _Commands(answers=answers)


def _sample_bus(
    *, sysctls: dict[str, str] = _SYSCTLS_BEFORE, k3s_server_argv: Sequence[str] = ()
) -> _Commands:
    """Every read ONE sample takes, on the host during a healthy window."""
    firewall = importlib.import_module("livespec_dev_tooling.fleet._docker_engine_guard_firewall")
    netstate = importlib.import_module(_NETSTATE_MODULE)
    witness = importlib.import_module(_WITNESS_MODULE)
    cluster = importlib.import_module(_CLUSTER_MODULE)
    pod_probes = importlib.import_module(_POD_MODULE)
    scope = importlib.import_module(_SCOPE_MODULE)
    answers: dict[tuple[str, ...], str] = {
        cluster.node_status_argv(node="gmktec-xubuntu"): _NODE_STATUS_READY,
        cluster.coredns_placement_argv(
            server="poweredge-xubuntu", k3s_server_argv=k3s_server_argv
        ): (_KUBE_SYSTEM_WIDE_CROSS_NODE),
        pod_probes.POD_LIST_ARGV: _READY_PODS,
        pod_probes.inspect_pod_argv(sandbox="svclb0001"): _HOST_NETWORK_POD,
        pod_probes.inspect_pod_argv(sandbox="cijob0002"): _POD_NETWORK_POD,
        pod_probes.resolve_argv(host=pod_probes.UBUNTU_ARCHIVE_HOST): _ARCHIVE_ADDRESSES,
        witness.PGREP_CONTAINERD_ARGV: _CONTAINERD_PIDS,
        scope.CONTROL_GROUP_ARGV: _lines(_SANDBOX_CONTROL_GROUP),
        scope.canary_pid_argv(canary="docker-engine-guard-canary"): _lines("7211"),
        scope.CONTAINER_LIST_ARGV: _lines("docker-engine-guard-canary"),
        scope.NETWORK_LIST_ARGV: _lines("bridge", "host", "none"),
        tuple(scope.canary_link_argv(pid="7211")): _CANARY_LINKS,
        netstate.LINK_SHOW_ARGV: _LINKS_WITH_CANARY,
        firewall.save_argv(family="ipv4", table="filter"): _FILTER_HEALTHY,
        firewall.save_argv(family="ipv4", table="nat"): _NAT_HEALTHY,
        firewall.save_argv(family="ipv6", table="filter"): _IPV6_FILTER,
        firewall.save_argv(family="ipv6", table="nat"): _IPV6_NAT,
    }
    answers.update(
        {
            _active_state_argv(unit=unit): _lines("active")
            for unit in ("k3s-agent.service", "tailscaled.service", *_MUST_STAY_RUNNING)
        }
    )
    answers.update({("sysctl", "-n", name): _lines(value) for name, value in sysctls.items()})
    return _Commands(answers=answers)


def _guarded_tree(
    *,
    root: Path,
    proc: Path,
    shims: tuple[Path, ...],
    parameters: dict[str, Any] = _PROBE_PARAMETERS,
) -> Any:
    """A reserved run with its probe parameters and its preflight snapshot."""
    paths = _guard_paths(root=root)
    paths.state_root.mkdir(parents=True, exist_ok=True)
    _ = paths.reservation.write_text(_lines(_RUN), encoding="utf-8")
    inputs = paths.inputs_dir(run=_RUN)
    inputs.mkdir(parents=True, exist_ok=True)
    _ = (inputs / "probes.json").write_text(json.dumps(parameters), encoding="utf-8")
    host = _real_host(root=root, commands=_before_bus(), proc_root=proc, containerd_paths=shims)
    host.take_snapshot(destination=paths.snapshot_dir(run=_RUN))
    host.record_preflight(destination=paths.snapshot_dir(run=_RUN))
    return paths


def test_the_real_hosts_sample_composes_every_probe_against_recorded_output(
    tmp_path: Path,
) -> None:
    """`HostOps.sample` IS the probe set, assembled from this run's own records.

    The observer reads one record per sample and treats anything that
    is not exactly `passed` as the window's failure, so this seam is
    where every probe, the retry rule and the failure record meet. It
    reads the run from the host's own reservation and its baseline from
    that run's `before/` directory, because a sample compared against
    some other run's snapshot would be comparing this host with a
    different one.
    """
    assert _PROBE_SET_PATH.is_file()
    proc = _proc_tree(
        root=tmp_path / "proc",
        cgroups={
            **_CONTAINERD_CGROUPS,
            "7211": f"0::{_SANDBOX_CONTROL_GROUP}/docker-abc123.scope",
        },
    )
    shims = (tmp_path / "containerd" / "s", tmp_path / "containerd" / "runc" / "k8s.io")
    for directory in shims:
        directory.mkdir(parents=True, exist_ok=True)
    root = tmp_path / "guard"
    _ = _guarded_tree(root=root, proc=proc, shims=shims)

    sample_module = importlib.import_module(_SAMPLE_MODULE)
    host = _real_host(root=root, commands=_sample_bus(), proc_root=proc, containerd_paths=shims)
    healthy = host.sample()

    assert healthy[sample_module.PASSED_KEY] is True
    assert healthy[sample_module.COUNTS_KEY] is True
    assert healthy[sample_module.FAILURES_KEY] == ()
    recorded = healthy[sample_module.PROBES_KEY]
    assert isinstance(recorded, tuple)
    assert tuple(str(probe["name"]) for probe in recorded) == (
        "services",
        "node-ready",
        "dns-placement",
        "dns",
        "api",
        "https",
        "sysctls",
        "k3s-witness",
        "canary-cgroup",
        "exclusive-scope",
        "interfaces",
        "firewall",
    )

    flipped = dict(_SYSCTLS_BEFORE)
    flipped["net.ipv4.ip_forward"] = "0"
    broken = _real_host(
        root=root,
        commands=_sample_bus(sysctls=flipped),
        proc_root=proc,
        containerd_paths=shims,
    ).sample()
    assert broken[sample_module.PASSED_KEY] is False
    assert broken[sample_module.FAILURES_KEY] == (
        {
            "probe": "sysctls",
            "error": "net.ipv4.ip_forward 1 -> 0; then net.ipv4.ip_forward 1 -> 0",
        },
    )


# The same declared parameters, plus the route this fleet reaches its k3s
# server by. It is a LIST in the recorded file because that is what JSON
# has; the parameters carry it as a tuple.
_PROBE_PARAMETERS_ROUTED: dict[str, Any] = {
    **_PROBE_PARAMETERS,
    "k3s_server_argv": list(_DECLARED_K3S_SERVER_ROUTE),
}


def test_the_declared_k3s_server_route_carries_from_probes_json_into_the_sample(
    tmp_path: Path,
) -> None:
    """A run's declared route reaches the placement read, and only it.

    The route is a fact about the FLEET, so it arrives the way every
    other cluster fact does: declared in the run's own `probes.json`,
    read into the parameters, and bound to the one probe that delegates
    to the k3s server. Nothing else in the sample changes, which is why
    both halves below drive the same recorded bus: a run that declares
    no route emits exactly the argv it emitted before the route was a
    parameter, and a run that declares one emits that prefix instead.
    """
    probe_set = importlib.import_module(_PROBE_SET_MODULE)
    assert "k3s_server_argv" in {declared.name for declared in fields(probe_set.ProbeParameters)}
    cluster = importlib.import_module(_CLUSTER_MODULE)
    sample_module = importlib.import_module(_SAMPLE_MODULE)

    proc = _proc_tree(
        root=tmp_path / "proc",
        cgroups={
            **_CONTAINERD_CGROUPS,
            "7211": f"0::{_SANDBOX_CONTROL_GROUP}/docker-abc123.scope",
        },
    )
    shims = (tmp_path / "containerd" / "s", tmp_path / "containerd" / "runc" / "k8s.io")
    for directory in shims:
        directory.mkdir(parents=True, exist_ok=True)

    for name, declared, route in (
        ("routed", _PROBE_PARAMETERS_ROUTED, _DECLARED_K3S_SERVER_ROUTE),
        ("undeclared", _PROBE_PARAMETERS, ()),
    ):
        root = tmp_path / name
        paths = _guarded_tree(root=root, proc=proc, shims=shims, parameters=declared)
        assert probe_set.read_probe_parameters(paths=paths, run=_RUN).k3s_server_argv == route

        bus = _sample_bus(k3s_server_argv=route)
        taken = _real_host(root=root, commands=bus, proc_root=proc, containerd_paths=shims).sample()
        assert taken[sample_module.PASSED_KEY] is True
        assert (
            cluster.coredns_placement_argv(server="poweredge-xubuntu", k3s_server_argv=route)
            in bus.argvs
        )


# Every shape a declared route can be wrong in, and each is wrong in its
# own way: an empty list reads as "no route declared" and silently
# restores the prefix the declaration exists to replace, a bare string is
# iterated character by character into one-letter words, a non-string
# word is not a command argument at all, and an EMPTY word builds an argv
# `ssh` reads as a host named "".
_MALFORMED_K3S_SERVER_ROUTES: tuple[Any, ...] = (
    [],
    "sudo -u cwoolley -H ssh poweredge-xubuntu sudo",
    ["ssh", "poweredge-xubuntu", 7],
    ["ssh", "", "poweredge-xubuntu"],
    None,
)

# What the refusal has to SAY, because the operator who wrote the
# declaration is the one who has to fix it.
_ROUTE_REFUSAL = "k3s_server_argv must be a non-empty list of non-empty strings"


def test_reading_the_probe_parameters_refuses_an_unusable_k3s_server_route(
    tmp_path: Path,
) -> None:
    """A declared route that cannot be RUN is refused where it is read.

    Every malformed shape above would otherwise fail once per sample on
    the one host nobody can reach by hand, and three of the four would
    fail SILENTLY -- an empty list by quietly restoring the default, a
    string by becoming one-letter words, an empty word by naming a host
    called "". So the read refuses, which puts the failure in front of
    the operator who wrote the declaration rather than inside the
    observation window.
    """
    probe_set = importlib.import_module(_PROBE_SET_MODULE)
    for index, malformed in enumerate(_MALFORMED_K3S_SERVER_ROUTES):
        paths = _guard_paths(root=tmp_path / str(index))
        inputs = paths.inputs_dir(run=_RUN)
        inputs.mkdir(parents=True, exist_ok=True)
        _ = (inputs / "probes.json").write_text(
            json.dumps({**_PROBE_PARAMETERS, "k3s_server_argv": malformed}), encoding="utf-8"
        )
        with pytest.raises(ValueError, match=_ROUTE_REFUSAL) as refused:
            _ = probe_set.read_probe_parameters(paths=paths, run=_RUN)
        assert str(inputs / "probes.json") in str(refused.value)
