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
import os
import shutil
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

__all__: list[str] = []

_RUNNER_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_runner"
_PREFLIGHT_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_preflight"
_RESYNC_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_resync"
_NETSTATE_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_netstate"
_WITNESS_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_witness"
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


def test_the_preflight_command_line_is_silent_and_exits_zero_on_a_clear_host(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """The pass, which is what makes the refusal above mean anything.

    The exit code is the ONLY verdict channel the role's step has, so a
    command line that exited non-zero whatever the host said would be
    indistinguishable from the refusal arm -- and the install would
    never run on a host that is perfectly ready for it. The silence is
    asserted for the mirror reason: a line on a clear host is a reason
    an operator would go looking for and never find.

    The host driven here is clear of all three refusal families at
    once: no interface address or route inside Docker's subnet, no
    declared range containing it, an EMPTY `docker` group, and k3s's
    own configuration carrying no interval above the ceiling -- the
    effective intervals are then the component defaults, which the
    ceiling admits.
    """
    cli = _cli()
    ordinary = _k3s_tree(root=tmp_path / "k3s", dropins={})
    declared = _declared_file(path=tmp_path / "declared.json", declared=_DECLARED_CLEAR)
    bus = _preflight_bus()

    with caplog.at_level("ERROR"):
        code = cli.main(
            argv=["refusals", "--declared", str(declared)],
            runner=bus,
            config=ordinary["config"],
            dropins=ordinary["dropins"],
        )

    assert code == 0
    assert caplog.records == []


# The run the role reserves on the acceptance host, and the file name
# `k3s_witness_probe` reads every sample -- spelled out rather than read
# from the witness module, because the FileNotFoundError that sent this
# work item to the factory named this exact path.
_RUN = "run-a"
_WITNESS_FILE = "k3s-witness.json"

# `pgrep --exact containerd` before the install: a containerd that is
# not k3s's, and k3s's own. The first is why the witness identifies its
# process by CGROUP rather than by name -- after the install there are
# two processes answering to this exact name, and only one of them must
# survive the window.
_CONTAINERD_PIDS = _lines("991", "512")
_CONTAINERD_CGROUPS = {
    "991": "0::/system.slice/containerd.service",
    "512": "0::/system.slice/k3s-agent.service",
}

# `ip -o link show` on the pre-Docker host: the loopback, the wired
# interface, the tailnet device, k3s's bridge and VXLAN device, and one
# of k3s's own veths -- whose `@if3` peer suffix must be stripped, so
# the record names what a deletion would take.
_LINKS_BEFORE = _lines(
    "1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN",
    "2: enp2s0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc mq state UP",
    "3: tailscale0: <POINTOPOINT,MULTICAST,NOARP,UP,LOWER_UP> mtu 1280 state UNKNOWN",
    "4: cni0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1450 qdisc noqueue state UP",
    "5: flannel.1: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1450 state UNKNOWN",
    "6: vethf00d01@if3: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1450 master cni0 state UP",
)


def _proc_tree(*, root: Path, cgroups: dict[str, str]) -> Path:
    """A recorded `/proc` holding one `cgroup` file per named process."""
    for pid, line in cgroups.items():
        directory = root / pid
        directory.mkdir(parents=True, exist_ok=True)
        _ = (directory / "cgroup").write_text(_lines(line), encoding="utf-8")
    return root


def _witness_bus() -> _Commands:
    """A bus answering both reads the preflight RECORD takes."""
    netstate = importlib.import_module(_NETSTATE_MODULE)
    witness = importlib.import_module(_WITNESS_MODULE)
    return _Commands(
        answers={
            witness.PGREP_CONTAINERD_ARGV: _CONTAINERD_PIDS,
            netstate.LINK_SHOW_ARGV: _LINKS_BEFORE,
        }
    )


def test_the_preflight_command_line_records_the_k3s_witness_and_the_interfaces(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Both baselines a sample compares against, into THIS run's own `before/`.

    This is the assertion the failure that filed this work item was
    about. `observe` on a real host raised FileNotFoundError on
    `<state root>/runs/<run>/before/k3s-witness.json` because nothing
    the role could invoke reached `RealHost.record_preflight`, so the
    file the witness probe reads every sample was never written. The
    subcommand is asserted to be ON the command line first -- an entry
    the role cannot name is exactly the gap that was found -- and then
    to write both records.

    Both are taken before the first package step, which is why they
    belong to the preflight rather than to an operation: a baseline
    taken afterwards would already carry what it exists to detect.

    The witness PID is the one identified by its CGROUP and not the
    other containerd on the host, and the interface record carries the
    veth's name with its `@if3` peer suffix stripped -- the name a
    deletion would take.
    """
    cli = _cli()

    with pytest.raises(SystemExit) as helped:
        _ = cli.main(argv=["--help"])

    assert helped.value.code == 0
    assert "record" in capsys.readouterr().out

    netstate = importlib.import_module(_NETSTATE_MODULE)
    witness = importlib.import_module(_WITNESS_MODULE)
    proc = _proc_tree(root=tmp_path / "proc", cgroups=_CONTAINERD_CGROUPS)
    state_root = tmp_path / "var"
    bus = _witness_bus()

    code = cli.main(
        argv=["record", "--state-root", str(state_root), "--run", _RUN],
        runner=bus,
        proc_root=proc,
    )

    assert code == 0
    before = state_root / "runs" / _RUN / "before"
    assert witness.WITNESS_SNAPSHOT == _WITNESS_FILE
    assert json.loads((before / _WITNESS_FILE).read_text(encoding="utf-8")) == {
        "containerd_pid": "512"
    }
    assert json.loads((before / witness.INTERFACE_SNAPSHOT).read_text(encoding="utf-8")) == [
        "cni0",
        "enp2s0",
        "flannel.1",
        "lo",
        "tailscale0",
        "vethf00d01",
    ]
    assert set(bus.timeouts) == {witness.WITNESS_TIMEOUT_SECONDS, netstate.LINK_TIMEOUT_SECONDS}


# The sibling the isolated arm below DELETES from the installed copy.
# It is the one this module imports directly, so its absence from the
# copy is what tells "the siblings resolved from the installed tree"
# from "they resolved from somewhere else on the interpreter's path".
_HOST_MODULE_FILE = "_docker_engine_guard_host.py"


def _installed_tree(*, root: Path) -> Path:
    """The guard tree as the role installs it; answers the module path inside it.

    A COPY rather than this checkout, because the claim under test is
    about the INSTALLED tree: the module has to find its siblings
    there, and a run against the checkout would prove only that the
    checkout is importable from a process that already has it on its
    path.
    """
    package = root / "livespec_dev_tooling"
    package.mkdir(parents=True, exist_ok=True)
    _ = shutil.copy(Path("livespec_dev_tooling/__init__.py"), package / "__init__.py")
    _ = shutil.copytree(
        Path("livespec_dev_tooling/fleet"),
        package / "fleet",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    return package / "fleet" / _CLI_PATH.name


def _isolated(*, module: Path, cwd: Path, args: Sequence[str]) -> subprocess.CompletedProcess[str]:
    """`python3 -I -B <module> …`, exactly as the role runs the guard's helpers.

    `-I` is the whole point of the invocation and not a tidiness flag:
    it ignores `PYTHONPATH` and the user site directory, so nothing
    this process's environment carries can put the guard's package root
    on the child's import path -- only the module's own preamble can.
    `-B` keeps the installed tree free of `__pycache__` directories the
    role never put there.

    A real child is the only way to assert this at all, since `-I`
    changes interpreter STARTUP: by the time any in-process test could
    look, this process's path is already built. The coverage variables
    are scrubbed from its environment because a child that
    self-instruments writes a `.coverage.*` that races the parallel
    runner's own data file.
    """
    environment = {name: value for name, value in os.environ.items() if not name.startswith("COV")}
    _ = environment.pop("PYTHONPATH", None)
    return subprocess.run(
        [sys.executable, "-I", "-B", str(module), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )


def test_the_preflight_command_line_runs_from_the_installed_tree_under_isolated_python(
    tmp_path: Path,
) -> None:
    """The invocation the role actually makes, with no import path but its own tree.

    The guarded host has no virtual environment and no third-party
    package: the guard tree is copied onto it and run against the
    host's own bare interpreter. So this module is reached the way the
    apt-lock helper already is -- `python3 -I -B <module>` -- and under
    those flags nothing on the interpreter's path resolves the
    package-qualified sibling imports every guard module uses. The
    module's own `sys.path` preamble is what makes them resolve, and it
    is the only thing that can.

    THE SECOND ARM IS WHAT MAKES THE FIRST MEAN ANYTHING. A tree that
    merely RAN proves nothing about where its siblings came from: this
    test process has the repository importable, so a module with no
    preamble at all would resolve them from the checkout and exit zero
    just the same. Deleting one sibling from the INSTALLED COPY
    discriminates: the invocation fails only if the copy is the tree
    the imports were served from.
    """
    _ = _cli()
    root = tmp_path / "libexec"
    module = _installed_tree(root=root)

    helped = _isolated(module=module, cwd=tmp_path, args=["--help"])

    assert helped.returncode == 0, helped.stderr
    assert "refusals" in helped.stdout
    assert "record" in helped.stdout

    (module.parent / _HOST_MODULE_FILE).unlink()

    without = _isolated(module=module, cwd=tmp_path, args=["--help"])

    assert without.returncode != 0
    assert _HOST_MODULE_FILE.removesuffix(".py") in without.stderr
