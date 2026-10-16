"""Tests for the command line the Docker engine install guard's ROLE runs the preflight through.

Governing specification: `SPECIFICATION/non-functional-requirements.md`
section "Docker engine install guard", "Preflight" and "Probes" --
"k3s witness" and "Interfaces". Governing design:
`docs/docker-engine-guard-design.md` F7 (the admission and collision
checks) and F8 (the witness the preflight records).

WHY THIS SURFACE EXISTS AT ALL, recorded because the gap it closes was
found on a real host. `RealHost.preflight_refusals` and
`RealHost.record_preflight` are deliberately NOT `HostOps` seams: both
run before `reserve`, so there is no run for the dispatch table to
admit an operation on, and they are the role's own reads of the
machine. But the role reaches the guarded host only through the guard's
own command line and through the stdlib modules it runs as scripts, so
until this module existed NO invocation reached either method -- which
means no run on a real host recorded the k3s witness, and every real
`observe` died on a missing `k3s-witness.json`.

Every read is driven against RECORDED command output -- `ip -o addr
show`, `ip route show table all`, `getent`, `pgrep --exact containerd`,
`ip -o link show` -- handed back by the one injectable runner, and the
witness's `/proc` is a recorded tree. No real host is touched.

The module under test is reached through `importlib` inside each test
body, and the recorded-command bus below is annotated `Any`, for the
reason the sibling guard suites record: a top-level import of a module
a Red moment has not created yet makes that Red a COLLECTION error
instead of a genuine assertion failure.
"""

from __future__ import annotations

import importlib
import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

__all__: list[str] = []

_RUNNER_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_runner"
_PREFLIGHT_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_preflight"
_RESYNC_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_resync"
_CLI_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_preflight_cli"
_CLI_PATH = Path("livespec_dev_tooling/fleet/_docker_engine_guard_preflight_cli.py")


def _result(*, argv: tuple[str, ...], returncode: int, stdout: str) -> Any:
    """One `GuardCommandResult`, built through the guard's own runner module."""
    runner_module = importlib.import_module(_RUNNER_MODULE)
    return runner_module.GuardCommandResult(argv=argv, returncode=returncode, stdout=stdout)


@dataclass(kw_only=True)
class _Commands:
    """A recorded command bus standing in for the guard's one timed runner.

    `answers` maps a whole argv to the output a real host would hand
    back, and each call is recorded with the timeout it carried -- which
    is how "every command this command line runs is bounded" is
    asserted at all.
    """

    answers: dict[tuple[str, ...], str] = field(default_factory=dict)
    argvs: list[tuple[str, ...]] = field(default_factory=list)
    timeouts: list[int] = field(default_factory=list)

    def __call__(self, *, argv: Sequence[str], timeout_seconds: int) -> Any:
        key = tuple(argv)
        self.argvs.append(key)
        self.timeouts.append(timeout_seconds)
        return _result(argv=key, returncode=0, stdout=self.answers.get(key, ""))


def _lines(*rows: str) -> str:
    """Recorded command output, as a host writes it: one row per line."""
    return "".join(f"{row}\n" for row in rows)


def _cli() -> Any:
    """The command-line module, asserted to be on disk before it is imported.

    The file check comes first on purpose: at Red the module does not
    exist, and a bare top-level import would make the Red a collection
    error that proves only unimportability.
    """
    assert _CLI_PATH.is_file()
    return importlib.import_module(_CLI_MODULE)


# `ip -o addr show` on the guarded host before anything Docker-shaped
# exists: the wired interface, the tailnet address and k3s's own bridge,
# none of them anywhere near Docker's default subnet.
_ADDRESSES_CLEAR = _lines(
    "1: lo    inet 127.0.0.1/8 scope host lo",
    "2: enp2s0    inet 192.168.1.42/24 brd 192.168.1.255 scope global enp2s0",
    "3: tailscale0    inet 100.86.4.19/32 scope global tailscale0",
    "4: cni0    inet 10.42.2.1/24 brd 10.42.2.255 scope global cni0",
)

# The same read on a host that already carries a bridge inside
# 172.17.0.0/16 -- a hand-made lab bridge, which is exactly the shape
# that makes the Docker install steal an address range in use.
_ADDRESSES_OVERLAPPING = _ADDRESSES_CLEAR + _lines(
    "7: br-lab    inet 172.17.3.1/24 brd 172.17.3.255 scope global br-lab",
)

_ROUTES_CLEAR = _lines(
    "default via 192.168.1.1 dev enp2s0 proto dhcp src 192.168.1.42 metric 100",
    "10.42.2.0/24 dev cni0 proto kernel scope link src 10.42.2.1",
    "local 192.168.1.42 dev enp2s0 table local proto kernel scope host src 192.168.1.42",
)
_ROUTES6 = _lines("fe80::/64 dev enp2s0 proto kernel metric 256 pref medium")

# `getent group docker` on a host whose CI account is a supplementary
# member, and `getent passwd` carrying one account whose PRIMARY group
# is that same gid -- the membership a member-list read alone would miss.
_GROUP_WITH_MEMBERS = _lines("docker:x:999:bob,alice")
_PASSWD_TABLE = _lines(
    "root:x:0:0:root:/root:/bin/bash",
    "builder:x:1001:999:CI builder:/home/builder:/bin/bash",
    "chad:x:1000:1000:Chad:/home/chad:/bin/bash",
)

# The ranges the controller DECLARES for this host, as the role writes
# them into the file this command line reads: facts about the tailnet
# and the cluster rather than about the machine, so they are declared
# and never discovered.
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

# A drop-in setting the network-policy controller's sweep to seven
# minutes -- above the five-minute ceiling, so the whole install is
# refused rather than stretched to a window the dead-man cannot cover.
_K3S_DROPIN_SLOW = _lines(
    "kube-router-arg:",
    '  - "iptables-sync-period=7m"',
)


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


def _declared_file(*, path: Path, declared: dict[str, str]) -> Path:
    """The declared-ranges file, as the role uploads it beside this command line."""
    _ = path.write_text(json.dumps(declared, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _k3s_tree(*, root: Path, dropins: dict[str, str]) -> dict[str, Path]:
    """A recorded `/etc/rancher/k3s` holding a base file and named drop-ins."""
    directory = root / "config.yaml.d"
    directory.mkdir(parents=True, exist_ok=True)
    config = root / "config.yaml"
    _ = config.write_text(_lines("write-kubeconfig-mode: '0644'"), encoding="utf-8")
    for name, body in dropins.items():
        _ = (directory / name).write_text(body, encoding="utf-8")
    return {"config": config, "dropins": directory}


def test_the_preflight_command_line_prints_every_refusal_and_exits_non_zero(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """One refusal per line, and an exit code the role's step can read.

    The role runs this before `reserve`, so its only verdict channel is
    the exit code -- and its only ACTIONABLE output is the refusal text.
    Both halves are asserted here because a command line that refused
    without naming the reasons would leave an operator on a machine
    reachable only over Tailscale with nothing to fix, and one that
    named them while exiting zero would let the install proceed onto a
    host whose address range Docker is about to steal.

    All three refusal FAMILIES are driven at once -- an interface
    address inside Docker's subnet, a declared cluster CIDR containing
    it, accounts the `docker` group admits, and a resync interval above
    the ceiling -- because the preflight is ONE decision and the whole
    point of composing them is that an operator can fix the host in a
    single pass rather than one converge per reason.
    """
    cli = _cli()
    resync = importlib.import_module(_RESYNC_MODULE)
    slow = _k3s_tree(root=tmp_path / "k3s", dropins={"10-slow.yaml": _K3S_DROPIN_SLOW})
    declared = _declared_file(path=tmp_path / "declared.json", declared=_DECLARED_OVERLAPPING)
    bus = _preflight_bus(group=_GROUP_WITH_MEMBERS, addresses=_ADDRESSES_OVERLAPPING)

    with caplog.at_level("ERROR"):
        code = cli.main(
            argv=["refusals", "--declared", str(declared)],
            runner=bus,
            config=slow["config"],
            dropins=slow["dropins"],
        )

    assert code != 0
    assert [record.getMessage() for record in caplog.records] == [
        "172.17.0.0/16 overlaps the address 172.17.3.1/24 on br-lab",
        "172.17.0.0/16 overlaps the declared cluster pod CIDR 172.16.0.0/12",
        "these accounts are in the docker group and could reach the API: "
        "('alice', 'bob', 'builder')",
        f"kube-router-arg {resync.SYNC_PERIOD_ARGUMENT} is 420s in "
        f"{slow['dropins'] / '10-slow.yaml'}, above the {resync.MAX_RESYNC_SECONDS}s maximum",
    ]
    preflight = importlib.import_module(_PREFLIGHT_MODULE)
    assert set(bus.timeouts) == {preflight.PREFLIGHT_TIMEOUT_SECONDS}
