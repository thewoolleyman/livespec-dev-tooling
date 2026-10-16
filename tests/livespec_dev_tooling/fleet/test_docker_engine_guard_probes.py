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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

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


def _real_host(*, root: Path, commands: _Commands) -> Any:
    """The guard's REAL host, rooted under `root` and driven by `commands`.

    The same object the guard's command line builds, so what is asserted
    is the host layer the factory actually runs -- not a second
    implementation standing in for it.
    """
    host_module = importlib.import_module(_HOST_MODULE)
    model = importlib.import_module(_MODEL_MODULE)
    paths = model.GuardPaths(state_root=root / "var", runtime_root=root / "run")
    return host_module.build_real_host(paths=paths, runner=commands)


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
