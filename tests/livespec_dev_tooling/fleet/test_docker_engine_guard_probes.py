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
