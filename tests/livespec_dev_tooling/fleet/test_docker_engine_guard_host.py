"""Tests for the Docker engine install guard's real host actions (child 3a).

Governing specification: `SPECIFICATION/non-functional-requirements.md`
section "Docker engine install guard", "Host actions". Governing design:
`docs/docker-engine-guard-design.md`: Mechanism 4 (footprint), R4, F5 and
G6 (effective conditions), and rider points 1, 2, 6, 7 and the
`--collect` half of 9.

Every action is driven against RECORDED command output -- `iptables-save`,
`ip6tables-save`, `ip link`, `systemctl list-jobs`, `busctl` -- handed
back by the one injectable runner, and each assertion reads the ARGV the
action emitted. No real host is touched and no process is spawned, which
is what makes a host layer that kills cgroups and deletes firewall rules
testable at all.

The modules under test are reached through `importlib` inside each test
body rather than imported at the top, and the recorded-command bus below
is annotated `Any` for the same reason: a top-level import of a module a
Red moment has not created yet makes that Red a COLLECTION error instead
of a genuine assertion failure. This is the pattern the sibling lifecycle
tests already use.
"""

from __future__ import annotations

import importlib
import json
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

__all__: list[str] = []

_MODEL_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_model"
_HOSTOPS_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_hostops"
_RUNNER_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_runner"
_RUNNER_PATH = Path("livespec_dev_tooling/fleet/_docker_engine_guard_runner.py")
_FIREWALL_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_firewall"
_FIREWALL_PATH = Path("livespec_dev_tooling/fleet/_docker_engine_guard_firewall.py")
_ACTIONS_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_firewall_actions"
_ACTIONS_PATH = Path("livespec_dev_tooling/fleet/_docker_engine_guard_firewall_actions.py")
_NETSTATE_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_netstate"
_NETSTATE_PATH = Path("livespec_dev_tooling/fleet/_docker_engine_guard_netstate.py")
_UNITS_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_units"
_UNITS_PATH = Path("livespec_dev_tooling/fleet/_docker_engine_guard_units.py")
_CONDITIONS_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_conditions"
_CONDITIONS_PATH = Path("livespec_dev_tooling/fleet/_docker_engine_guard_conditions.py")
_POSTCONDITIONS_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_postconditions"
_POSTCONDITIONS_PATH = Path("livespec_dev_tooling/fleet/_docker_engine_guard_postconditions.py")
_CLOCK_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_clock"
_CLOCK_PATH = Path("livespec_dev_tooling/fleet/_docker_engine_guard_clock.py")
_PERMISSION_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_permission"
_PERMISSION_PATH = Path("livespec_dev_tooling/fleet/_docker_engine_guard_permission.py")
_UNIT_STATE_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_unit_state"
_UNIT_STATE_PATH = Path("livespec_dev_tooling/fleet/_docker_engine_guard_unit_state.py")
_DAEMON_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_daemon"
_DAEMON_PATH = Path("livespec_dev_tooling/fleet/_docker_engine_guard_daemon.py")
_HOST_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_host"

# What the guarded host's two address families look like BEFORE any Docker
# package exists: the k3s and Tailscale rule sets the snapshot has to
# preserve, and the FORWARD policies a rollback has to put back.
_IPV4_FILTER_BEFORE = (
    "*filter",
    ":INPUT ACCEPT [0:0]",
    ":FORWARD DROP [0:0]",
    ":OUTPUT ACCEPT [0:0]",
    ":ts-forward - [0:0]",
    ":ts-input - [0:0]",
    "-A INPUT -j ts-input",
    "-A FORWARD -j ts-forward",
    "COMMIT",
)
_IPV4_NAT_BEFORE = (
    "*nat",
    ":PREROUTING ACCEPT [0:0]",
    ":POSTROUTING ACCEPT [0:0]",
    "-A POSTROUTING -s 10.42.0.0/16 -j MASQUERADE",
    "COMMIT",
)
_IPV6_FILTER_BEFORE = (
    "*filter",
    ":INPUT ACCEPT [0:0]",
    ":FORWARD ACCEPT [0:0]",
    ":OUTPUT ACCEPT [0:0]",
    "COMMIT",
)
_IPV6_NAT_BEFORE = (
    "*nat",
    ":PREROUTING ACCEPT [0:0]",
    ":POSTROUTING ACCEPT [0:0]",
    "COMMIT",
)

# Each family's FORWARD policy on the pre-Docker host. They DIFFER on
# purpose: a restore that put one family's policy on both would pass a
# fixture where they matched and open the other family's forwarding on
# the real one.
_FORWARD_POLICIES_BEFORE = {"ipv4": "DROP", "ipv6": "ACCEPT"}

# The five watched values as gmktec reports them (design, measured state
# 2026-10-15): forwarding on for both families, bridge-netfilter on for
# iptables and ip6tables and off for arptables.
_SYSCTL_BEFORE = {
    "net.bridge.bridge-nf-call-arptables": "0",
    "net.bridge.bridge-nf-call-ip6tables": "1",
    "net.bridge.bridge-nf-call-iptables": "1",
    "net.ipv4.ip_forward": "1",
    "net.ipv6.conf.all.forwarding": "1",
}


# Which `*-save` dump a change command's edits are visible in, so the bus
# can answer a re-read with the effect of the delete that preceded it --
# the whole point of the footprint's repeat passes.
_SAVE_OF_CHANGE = {
    "iptables-nft": "iptables-save",
    "ip6tables-nft": "ip6tables-save",
}


def _result(*, argv: tuple[str, ...], returncode: int, stdout: str) -> Any:
    """One `GuardCommandResult`, built through the module the Red moment creates."""
    runner_module = importlib.import_module(_RUNNER_MODULE)
    return runner_module.GuardCommandResult(argv=argv, returncode=returncode, stdout=stdout)


@dataclass(kw_only=True)
class _Commands:
    """A recorded command bus standing in for the guard's one timed runner.

    `tables` holds each `(save command, table)` dump as a list of lines and
    is MUTATED by the change commands the bus sees, so a RE-READ observes
    the effect of the delete that preceded it exactly as the real host
    would; `answers` holds every other command's recorded reply.
    `undeletable` is the one lever a test needs that a real host has no
    switch for -- a rule the host will not drop, which is the only way to
    reach residual reporting at all. Each call is recorded with the
    timeout it carried, which is how "every command is bounded" is
    asserted.
    """

    answers: dict[tuple[str, ...], str] = field(default_factory=dict)
    tables: dict[tuple[str, str], list[str]] = field(default_factory=dict)
    undeletable: tuple[str, ...] = ()
    argvs: list[tuple[str, ...]] = field(default_factory=list)
    timeouts: list[int] = field(default_factory=list)

    def __call__(self, *, argv: Sequence[str], timeout_seconds: int) -> Any:
        key = tuple(argv)
        self.argvs.append(key)
        self.timeouts.append(timeout_seconds)
        return _result(argv=key, returncode=0, stdout=self._answer(key=key))

    def _answer(self, *, key: tuple[str, ...]) -> str:
        if key[0].endswith("-save"):
            return "\n".join(self.tables.get((key[0], key[2]), [])) + "\n"
        if key[0] in _SAVE_OF_CHANGE:
            self._apply(key=key)
            return ""
        return self.answers.get(key, "")

    def _apply(self, *, key: tuple[str, ...]) -> None:
        slot = (_SAVE_OF_CHANGE[key[0]], key[2])
        lines = self.tables.get(slot, [])
        verb = key[3]
        rest = list(key[4:])
        rule = "-A " + " ".join(rest)
        if verb == "-D" and rule not in self.undeletable:
            self.tables[slot] = [line for line in lines if line != rule]
        if verb == "-F":
            self.tables[slot] = [line for line in lines if not line.startswith(f"-A {rest[0]} ")]
        if verb == "-X":
            self.tables[slot] = [line for line in lines if not line.startswith(f":{rest[0]} ")]

    def argvs_with(self, *, flag: str) -> tuple[tuple[str, ...], ...]:
        """Every recorded argv carrying `flag`, in the order it was emitted."""
        return tuple(argv for argv in self.argvs if flag in argv)


def _before_tables() -> dict[tuple[str, str], list[str]]:
    """The four recorded dumps of a host that has never seen Docker."""
    return {
        ("iptables-save", "filter"): list(_IPV4_FILTER_BEFORE),
        ("iptables-save", "nat"): list(_IPV4_NAT_BEFORE),
        ("ip6tables-save", "filter"): list(_IPV6_FILTER_BEFORE),
        ("ip6tables-save", "nat"): list(_IPV6_NAT_BEFORE),
    }


def _sysctl_answers() -> dict[tuple[str, ...], str]:
    """The recorded `sysctl -n` reply for each watched value."""
    return {("sysctl", "-n", name): f"{value}\n" for name, value in _SYSCTL_BEFORE.items()}


def _bus() -> _Commands:
    """A recorded bus carrying the pre-Docker dumps and the watched sysctls."""
    return _Commands(answers=_sysctl_answers(), tables=_before_tables())


def _real_host(*, root: Path, commands: _Commands) -> Any:
    """The real host rooted under `root`, with every command on the recorded bus."""
    model = importlib.import_module(_MODEL_MODULE)
    host_module = importlib.import_module(_HOST_MODULE)
    paths = model.GuardPaths(state_root=root / "var", runtime_root=root / "run")
    return host_module.build_real_host(paths=paths, runner=commands)


def test_the_one_runner_carries_an_explicit_timeout_to_every_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every external command the guard runs goes through one timed runner.

    A host layer that kills cgroups and deletes firewall rules on a machine
    reachable only over Tailscale cannot have an unbounded command in it:
    one `iptables` blocked on the xtables lock would hold the rollback past
    its own budget and leave the host mid-teardown. So the timeout is a
    required argument of the single seam, and a command that exceeds it
    reports `timeout(1)`'s own exit code rather than raising.
    """
    assert _RUNNER_PATH.is_file()
    runner_module = importlib.import_module(_RUNNER_MODULE)
    seen: dict[str, Any] = {}

    def _fake_run(argv: list[str], **kwargs: Any) -> Any:
        seen.update({"argv": argv, **kwargs})
        return subprocess.CompletedProcess(args=argv, returncode=0, stdout="ok\n", stderr="")

    monkeypatch.setattr(runner_module.subprocess, "run", _fake_run)
    answer = runner_module.run_command(argv=("systemctl", "is-active"), timeout_seconds=7)

    assert answer.argv == ("systemctl", "is-active")
    assert answer.returncode == 0
    assert answer.stdout == "ok\n"
    assert seen["timeout"] == 7

    def _time_out(argv: list[str], **_kwargs: Any) -> Any:
        raise subprocess.TimeoutExpired(cmd=argv, timeout=7)

    monkeypatch.setattr(runner_module.subprocess, "run", _time_out)
    expired = runner_module.run_command(argv=("iptables-nft", "-L"), timeout_seconds=7)

    assert expired.returncode == runner_module.TIMEOUT_RETURNCODE
    assert expired.stdout == ""


def test_the_snapshot_action_stores_both_families_rules_policies_and_sysctls(
    tmp_path: Path,
) -> None:
    """The snapshot is what a rollback compares against, so it holds all three.

    `iptables-save` and `ip6tables-save` per table WITHOUT counters (no
    `-c`, so a rule's bytes do not move between snapshot and current and
    make an unchanged rule read as new), both FORWARD policies, and the
    five watched forwarding and bridge-netfilter values -- all in the run's
    `before/` directory, which is the only copy a rollback ever reads.
    """
    assert _ACTIONS_PATH.is_file()
    assert _NETSTATE_PATH.is_file()
    commands = _bus()
    host = _real_host(root=tmp_path, commands=commands)
    destination = tmp_path / "var" / "runs" / "run-a" / "before"

    host.take_snapshot(destination=destination)

    firewall = importlib.import_module(_FIREWALL_MODULE)
    assert commands.argvs_with(flag="-c") == ()
    assert tuple(commands.argvs[:4]) == (
        ("iptables-save", "-t", "filter"),
        ("iptables-save", "-t", "nat"),
        ("ip6tables-save", "-t", "filter"),
        ("ip6tables-save", "-t", "nat"),
    )
    assert (destination / "iptables-save.filter").read_text(encoding="utf-8") == (
        "\n".join(_IPV4_FILTER_BEFORE) + "\n"
    )
    assert (destination / "ip6tables-save.nat").read_text(encoding="utf-8") == (
        "\n".join(_IPV6_NAT_BEFORE) + "\n"
    )
    assert json.loads(
        (destination / firewall.FORWARD_POLICY_SNAPSHOT).read_text(encoding="utf-8")
    ) == {"ipv4": "DROP", "ipv6": "ACCEPT"}

    netstate = importlib.import_module(_NETSTATE_MODULE)
    assert (
        json.loads((destination / netstate.SYSCTL_SNAPSHOT).read_text(encoding="utf-8"))
        == _SYSCTL_BEFORE
    )
    actions = importlib.import_module(_ACTIONS_MODULE)
    assert set(commands.timeouts) == {
        actions.FIREWALL_TIMEOUT_SECONDS,
        netstate.SYSCTL_TIMEOUT_SECONDS,
    }


# The same family and table once the Docker packages have run: the two
# `DOCKER*` chains, the four FORWARD rules and the isolation rule Docker
# adds -- and ONE rule a reconciler added in the same window
# (`-A ts-forward -i tailscale0 ...`), which is present now, absent from
# the snapshot, and MUST NOT be mistaken for Docker's.
_IPV4_FILTER_AFTER = (
    "*filter",
    ":INPUT ACCEPT [0:0]",
    ":FORWARD DROP [0:0]",
    ":OUTPUT ACCEPT [0:0]",
    ":DOCKER - [0:0]",
    ":DOCKER-ISOLATION-STAGE-1 - [0:0]",
    ":ts-forward - [0:0]",
    ":ts-input - [0:0]",
    "-A INPUT -j ts-input",
    "-A FORWARD -j ts-forward",
    "-A FORWARD -j DOCKER-ISOLATION-STAGE-1",
    "-A FORWARD -o docker0 -j DOCKER",
    "-A FORWARD -o docker0 -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT",
    "-A FORWARD -i docker0 ! -o docker0 -j ACCEPT",
    "-A DOCKER-ISOLATION-STAGE-1 -i docker0 ! -o docker0 -j RETURN",
    "-A ts-forward -i tailscale0 -j MARK --set-xmark 0x40000/0xff0000",
    "COMMIT",
)

_IPV4_FILTER_DOCKER_RULES = (
    "-A FORWARD -j DOCKER-ISOLATION-STAGE-1",
    "-A FORWARD -o docker0 -j DOCKER",
    "-A FORWARD -o docker0 -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT",
    "-A FORWARD -i docker0 ! -o docker0 -j ACCEPT",
    "-A DOCKER-ISOLATION-STAGE-1 -i docker0 ! -o docker0 -j RETURN",
)


def _table(*, module: Any, lines: tuple[str, ...]) -> Any:
    """One parsed table, from recorded `*-save` lines."""
    return module.parse_table(dump="\n".join(lines) + "\n")


def test_the_footprint_planner_selects_exactly_the_rules_docker_added() -> None:
    """Docker's footprint is a THREE-part test, and every part is load-bearing.

    A rule belongs to it only when it is present now, absent from the
    snapshot, AND references `docker0`, `172.17.0.0/16` or a chain absent
    from the snapshot whose name starts with `DOCKER`. Dropping the last
    part would make the guard delete the `ts-forward` rule Tailscale's
    reconciler added inside the same window, and dropping the "absent from
    the snapshot" part is what the next assertion is about. The scope is
    the default bridge only, which is why the marks are exactly those two
    literals plus the chain set.
    """
    firewall = importlib.import_module(_FIREWALL_MODULE)
    assert hasattr(firewall, "plan_footprint")

    plan = firewall.plan_footprint(
        current=_table(module=firewall, lines=_IPV4_FILTER_AFTER),
        snapshot=_table(module=firewall, lines=_IPV4_FILTER_BEFORE),
    )

    assert plan.delete_rules == _IPV4_FILTER_DOCKER_RULES
    assert plan.delete_chains == ("DOCKER", "DOCKER-ISOLATION-STAGE-1")


# A baseline that ALREADY carries a `docker0` rule and a `DOCKER`-prefixed
# chain of its own -- an operator's, or a previously confirmed run's. They
# are in the snapshot, so they are the host's state and not this run's
# footprint, and a rollback that removed them would take away something it
# never installed.
_IPV4_FILTER_BRIDGED_BEFORE = (
    "*filter",
    ":INPUT ACCEPT [0:0]",
    ":FORWARD DROP [0:0]",
    ":OUTPUT ACCEPT [0:0]",
    ":DOCKER-USER - [0:0]",
    ":ts-input - [0:0]",
    "-A INPUT -j ts-input",
    "-A FORWARD -j DOCKER-USER",
    "-A FORWARD -o docker0 -j ACCEPT",
    "COMMIT",
)
_IPV4_FILTER_BRIDGED_AFTER = (
    "*filter",
    ":INPUT ACCEPT [0:0]",
    ":FORWARD DROP [0:0]",
    ":OUTPUT ACCEPT [0:0]",
    ":DOCKER - [0:0]",
    ":DOCKER-ISOLATION-STAGE-1 - [0:0]",
    ":DOCKER-USER - [0:0]",
    ":ts-input - [0:0]",
    "-A INPUT -j ts-input",
    "-A FORWARD -j DOCKER-USER",
    "-A FORWARD -o docker0 -j ACCEPT",
    "-A FORWARD -o docker0 -j DOCKER",
    "COMMIT",
)


def test_the_planned_deletion_set_excludes_everything_the_snapshot_holds() -> None:
    """ "Absent from the snapshot" is a SEPARATE filter from "looks like Docker's".

    The two are easy to conflate and the cost of conflating them is
    asymmetric: a rule or chain the snapshot already holds is the HOST's,
    and removing it is damage the rollback cannot undo, because the
    snapshot is the only record of what the host looked like and it does
    not say who put each line there. So the snapshot's own rules survive
    even when they reference `docker0`, and its own `DOCKER`-prefixed
    chains survive even though their names match.
    """
    firewall = importlib.import_module(_FIREWALL_MODULE)
    snapshot = _table(module=firewall, lines=_IPV4_FILTER_BRIDGED_BEFORE)

    plan = firewall.plan_footprint(
        current=_table(module=firewall, lines=_IPV4_FILTER_BRIDGED_AFTER),
        snapshot=snapshot,
    )

    assert plan.delete_rules == ("-A FORWARD -o docker0 -j DOCKER",)
    assert plan.delete_chains == ("DOCKER", "DOCKER-ISOLATION-STAGE-1")
    assert set(plan.delete_rules).isdisjoint(snapshot.rules)
    assert set(plan.delete_chains).isdisjoint(snapshot.chains)


# The `nat` table and the second family once Docker has run. `ip6tables`'
# `nat` table is UNCHANGED, which is the "this table has nothing of
# Docker's in it" path every removal pass has to walk without acting.
_IPV4_NAT_AFTER = (
    "*nat",
    ":PREROUTING ACCEPT [0:0]",
    ":POSTROUTING ACCEPT [0:0]",
    ":DOCKER - [0:0]",
    "-A PREROUTING -m addrtype --dst-type LOCAL -j DOCKER",
    "-A POSTROUTING -s 10.42.0.0/16 -j MASQUERADE",
    "-A POSTROUTING -s 172.17.0.0/16 ! -o docker0 -j MASQUERADE",
    "COMMIT",
)
_IPV6_FILTER_AFTER = (
    "*filter",
    ":INPUT ACCEPT [0:0]",
    ":FORWARD ACCEPT [0:0]",
    ":OUTPUT ACCEPT [0:0]",
    ":DOCKER - [0:0]",
    "-A FORWARD -o docker0 -j DOCKER",
    "COMMIT",
)

# Every `-D` the removal must issue, in the order the two families and
# their two tables are walked. Each carries the rule's FULL specification
# and never a position: a reconciler inserting a rule between the read and
# the delete would otherwise make the guard remove k3s's rule instead.
_EXPECTED_DELETES = (
    ("iptables-nft", "-t", "filter", "-D", "FORWARD", "-j", "DOCKER-ISOLATION-STAGE-1"),
    ("iptables-nft", "-t", "filter", "-D", "FORWARD", "-o", "docker0", "-j", "DOCKER"),
    (
        "iptables-nft",
        "-t",
        "filter",
        "-D",
        "FORWARD",
        "-o",
        "docker0",
        "-m",
        "conntrack",
        "--ctstate",
        "RELATED,ESTABLISHED",
        "-j",
        "ACCEPT",
    ),
    (
        "iptables-nft",
        "-t",
        "filter",
        "-D",
        "FORWARD",
        "-i",
        "docker0",
        "!",
        "-o",
        "docker0",
        "-j",
        "ACCEPT",
    ),
    (
        "iptables-nft",
        "-t",
        "filter",
        "-D",
        "DOCKER-ISOLATION-STAGE-1",
        "-i",
        "docker0",
        "!",
        "-o",
        "docker0",
        "-j",
        "RETURN",
    ),
    (
        "iptables-nft",
        "-t",
        "nat",
        "-D",
        "PREROUTING",
        "-m",
        "addrtype",
        "--dst-type",
        "LOCAL",
        "-j",
        "DOCKER",
    ),
    (
        "iptables-nft",
        "-t",
        "nat",
        "-D",
        "POSTROUTING",
        "-s",
        "172.17.0.0/16",
        "!",
        "-o",
        "docker0",
        "-j",
        "MASQUERADE",
    ),
    ("ip6tables-nft", "-t", "filter", "-D", "FORWARD", "-o", "docker0", "-j", "DOCKER"),
)

_EXPECTED_CHAIN_TARGETS = (
    ("iptables-nft", "filter", "DOCKER"),
    ("iptables-nft", "filter", "DOCKER-ISOLATION-STAGE-1"),
    ("iptables-nft", "nat", "DOCKER"),
    ("ip6tables-nft", "filter", "DOCKER"),
)


def _after_tables() -> dict[tuple[str, str], list[str]]:
    """The four recorded dumps of a host the Docker packages have run on."""
    return {
        ("iptables-save", "filter"): list(_IPV4_FILTER_AFTER),
        ("iptables-save", "nat"): list(_IPV4_NAT_AFTER),
        ("ip6tables-save", "filter"): list(_IPV6_FILTER_AFTER),
        ("ip6tables-save", "nat"): list(_IPV6_NAT_BEFORE),
    }


def _write_snapshot(*, root: Path) -> Path:
    """A run's `before/` directory holding the pre-Docker dumps and policies."""
    snapshot = root / "var" / "runs" / "run-a" / "before"
    snapshot.mkdir(parents=True, exist_ok=True)
    for (command, table), lines in _before_tables().items():
        _ = (snapshot / f"{command}.{table}").write_text("\n".join(lines) + "\n", encoding="utf-8")
    _ = (snapshot / "forward-policy.json").write_text(
        json.dumps(_FORWARD_POLICIES_BEFORE), encoding="utf-8"
    )
    return snapshot


def test_footprint_removal_deletes_each_rule_then_flushes_and_deletes_each_chain(
    tmp_path: Path,
) -> None:
    """`-D` per rule, then `-F` per chain, then `-X` -- and the order is forced.

    A chain cannot be deleted while a rule still jumps to it, and cannot
    be deleted while it holds rules of its own, so a removal that deleted
    chains first would simply fail and leave the footprint in place. Both
    address families are driven, because Docker's ip6tables rules are as
    capable of cutting the tailnet as its ipv4 ones.
    """
    actions = importlib.import_module(_ACTIONS_MODULE)
    assert hasattr(actions, "remove_footprint")
    snapshot = _write_snapshot(root=tmp_path)
    commands = _Commands(tables=_after_tables())
    host = _real_host(root=tmp_path, commands=commands)

    _ = host.remove_firewall_footprint(snapshot=snapshot)

    assert commands.argvs_with(flag="-D") == _EXPECTED_DELETES
    assert commands.argvs_with(flag="-F") == tuple(
        (command, "-t", table, "-F", chain) for command, table, chain in _EXPECTED_CHAIN_TARGETS
    )
    assert commands.argvs_with(flag="-X") == tuple(
        (command, "-t", table, "-X", chain) for command, table, chain in _EXPECTED_CHAIN_TARGETS
    )
    emitted = commands.argvs
    assert emitted.index(_EXPECTED_DELETES[4]) < emitted.index(
        ("iptables-nft", "-t", "filter", "-F", "DOCKER")
    )
    assert emitted.index(("iptables-nft", "-t", "filter", "-F", "DOCKER-ISOLATION-STAGE-1")) < (
        emitted.index(("iptables-nft", "-t", "filter", "-X", "DOCKER"))
    )


def test_footprint_removal_repeats_at_most_three_passes_and_reports_the_residue(
    tmp_path: Path,
) -> None:
    """Deleting a rule can fail, and a rollback that says nothing about it lies.

    A delete races every reconciler on the host, so the removal re-reads
    and repeats -- but BOUNDED, because a rule that will not go will not
    go, and an unbounded retry would hold the rollback phase until its own
    `timeout -k 10` killed it mid-teardown. A host that gives everything
    up stops after the pass that finds nothing; a host that keeps one rule
    exhausts the three passes and the rule is REPORTED, named with its
    family and table, so the driver can write `rollback-partial` instead
    of a false `rolled-back`.
    """
    actions = importlib.import_module(_ACTIONS_MODULE)
    assert hasattr(actions, "FOOTPRINT_PASSES")
    assert actions.FOOTPRINT_PASSES == 3

    clean_root = tmp_path / "clean"
    clean = _Commands(tables=_after_tables())
    clean_host = _real_host(root=clean_root, commands=clean)

    assert clean_host.remove_firewall_footprint(snapshot=_write_snapshot(root=clean_root)) == ()
    assert clean.argvs_with(flag="-D") == _EXPECTED_DELETES

    stuck_root = tmp_path / "stuck"
    # Unique to the ipv4 `filter` table, so the residue report is pinned to
    # one family -- the bus refuses a rule by its TEXT, and the DOCKER jump
    # rule is spelled identically in both.
    stubborn = "-A FORWARD -i docker0 ! -o docker0 -j ACCEPT"
    stuck = _Commands(tables=_after_tables(), undeletable=(stubborn,))
    stuck_host = _real_host(root=stuck_root, commands=stuck)

    residue = stuck_host.remove_firewall_footprint(snapshot=_write_snapshot(root=stuck_root))

    assert residue == (f"ipv4 filter {stubborn}",)
    assert stuck.argvs.count(_EXPECTED_DELETES[3]) == actions.FOOTPRINT_PASSES
    assert len(stuck.argvs_with(flag="-D")) == len(_EXPECTED_DELETES) + 2


def test_forward_restore_puts_each_family_s_recorded_policy_back(tmp_path: Path) -> None:
    """One `-P FORWARD` per family, with the policy the SNAPSHOT recorded.

    The policy is read from the snapshot rather than inferred, and that is
    the whole point: Docker sets FORWARD to DROP and adds the rules that
    make its own traffic work, so a rollback that removed the rules and
    left the policy would leave k3s's pod traffic dropped by a chain with
    nothing in it. Each family carries its own recorded value -- they
    differ on this host -- so neither is restored from the other's.
    """
    actions = importlib.import_module(_ACTIONS_MODULE)
    assert hasattr(actions, "restore_forward_policy")
    snapshot = _write_snapshot(root=tmp_path)
    commands = _Commands(tables=_after_tables())
    host = _real_host(root=tmp_path, commands=commands)

    host.restore_forward_policy(snapshot=snapshot)

    assert tuple(commands.argvs) == (
        ("iptables-nft", "-t", "filter", "-P", "FORWARD", "DROP"),
        ("ip6tables-nft", "-t", "filter", "-P", "FORWARD", "ACCEPT"),
    )
    assert set(commands.timeouts) == {actions.FIREWALL_TIMEOUT_SECONDS}


# `systemctl list-jobs` as the real tool prints it: four columns, leading
# whitespace, and a footer line that is NOT a job. The k3s row is the
# control -- cancelling it would stop the very agent the guard exists to
# protect.
_LIST_JOBS = (
    "  11 docker.service     start waiting\n"
    "  12 k3s-agent.service  start running\n"
    "  13 containerd.service start waiting\n"
    "  14 docker.socket      start waiting\n"
    "\n"
    "4 jobs listed.\n"
)

_LIST_JOBS_ARGV = ("systemctl", "list-jobs", "--no-legend", "--no-pager")


def _unit_bus(*, answers: dict[tuple[str, ...], str] | None = None) -> _Commands:
    """A recorded bus answering the unit reads this host performs."""
    return _Commands(answers={_LIST_JOBS_ARGV: _LIST_JOBS, **(answers or {})})


def test_job_cancellation_names_only_the_guarded_units_queued_job_ids(
    tmp_path: Path,
) -> None:
    """`systemctl cancel` with ids, never bare, and never k3s's id.

    A bare `systemctl cancel` cancels the WHOLE queue, which on this host
    includes `k3s-agent.service` -- the unit whose death is the lockout the
    guard exists to prevent. So the ids are read from the live queue and
    intersected with the guarded units, and a cancellation with nothing to
    cancel issues no command at all rather than a bare one.
    """
    assert _UNITS_PATH.is_file()
    commands = _unit_bus()
    host = _real_host(root=tmp_path, commands=commands)

    assert host.queued_jobs() == tuple(
        importlib.import_module(_HOSTOPS_MODULE).QueuedJob(job_id=job_id, unit=unit)
        for job_id, unit in (
            ("11", "docker.service"),
            ("12", "k3s-agent.service"),
            ("13", "containerd.service"),
            ("14", "docker.socket"),
        )
    )

    host.cancel_jobs(job_ids=("11", "12", "13", "14", "15"))

    assert tuple(commands.argvs) == (
        _LIST_JOBS_ARGV,
        _LIST_JOBS_ARGV,
        ("systemctl", "cancel", "11", "13", "14"),
    )

    quiet = _unit_bus()
    _real_host(root=tmp_path, commands=quiet).cancel_jobs(job_ids=("12",))

    assert tuple(quiet.argvs) == (_LIST_JOBS_ARGV,)


def test_the_docker_stop_action_stops_the_socket_before_the_service(
    tmp_path: Path,
) -> None:
    """Socket first, and rider point 1 is why the order is load-bearing.

    A `Restart=` respawn does NOT re-evaluate `ConditionPathExists` on
    systemd 259 -- an auto-restart maps to `activating` and `unit_start`
    skips the condition test there -- so a listening `docker.socket` left
    up would keep re-triggering starts of a service the guard has just
    revoked permission for, and the condition gate would not stop them.
    """
    units = importlib.import_module(_UNITS_MODULE)
    assert hasattr(units, "stop_docker")
    commands = _Commands()

    units.stop_docker(runner=commands)

    assert tuple(commands.argvs) == (
        ("systemctl", "stop", "docker.socket"),
        ("systemctl", "stop", "docker.service"),
    )
    assert set(commands.timeouts) == {units.UNIT_ACTION_TIMEOUT_SECONDS}

    one = _Commands()
    _real_host(root=tmp_path, commands=one).stop_unit(unit="containerd.service", timeout_seconds=42)

    assert tuple(one.argvs) == (("systemctl", "stop", "containerd.service"),)
    assert one.timeouts == [42]


def test_the_cgroup_kill_names_only_the_two_daemons_and_the_sandbox_slice(
    tmp_path: Path,
) -> None:
    """SIGKILL the whole control group, then stop it -- and reach nothing else.

    A container holding the Docker API open survives a plain stop, so the
    kill is by CGROUP. That makes the TARGET SET the only thing standing
    between this action and a stopped `k3s-agent.service`: every k3s shim
    on this host lives in that unit and in the kubepods slices, so the set
    is fixed at the two Docker daemons plus the Fabro sandbox slice, and a
    caller naming anything else is narrowed away rather than obeyed.
    """
    units = importlib.import_module(_UNITS_MODULE)
    assert hasattr(units, "kill_cgroup")
    commands = _Commands()
    host = _real_host(root=tmp_path, commands=commands)

    host.kill_cgroup(
        units=(
            "docker.service",
            "containerd.service",
            "fabro-sandbox.slice",
            "k3s-agent.service",
        )
    )

    assert tuple(commands.argvs) == (
        ("systemctl", "kill", "--kill-whom=all", "--signal=SIGKILL", "docker.service"),
        ("systemctl", "kill", "--kill-whom=all", "--signal=SIGKILL", "containerd.service"),
        ("systemctl", "kill", "--kill-whom=all", "--signal=SIGKILL", "fabro-sandbox.slice"),
        ("systemctl", "stop", "docker.service"),
        ("systemctl", "stop", "containerd.service"),
        ("systemctl", "stop", "fabro-sandbox.slice"),
        ("systemctl", "stop", "docker.socket"),
    )
    assert commands.argvs_with(flag="k3s-agent.service") == ()

    narrow = _Commands()
    units.kill_cgroup(runner=narrow, units=("containerd.service",))

    assert tuple(narrow.argvs) == (
        ("systemctl", "kill", "--kill-whom=all", "--signal=SIGKILL", "containerd.service"),
        ("systemctl", "stop", "containerd.service"),
        ("systemctl", "stop", "docker.socket"),
    )


def test_the_disable_action_disables_exactly_the_three_guarded_units(
    tmp_path: Path,
) -> None:
    """One `disable` per guarded unit, and the set is fixed, not the caller's.

    Disabling is what stops the next BOOT from starting what this rollback
    just stopped -- the start permission lives on tmpfs and is gone by
    then, but a `WantedBy` is durable. One command per unit rather than
    one carrying all three, so a unit whose disable fails does not take
    the other two down with it.
    """
    units = importlib.import_module(_UNITS_MODULE)
    assert hasattr(units, "disable_units")
    commands = _Commands()
    host = _real_host(root=tmp_path, commands=commands)

    host.disable_units(units=("docker.service", "docker.socket", "containerd.service"))

    assert tuple(commands.argvs) == (
        ("systemctl", "disable", "containerd.service"),
        ("systemctl", "disable", "docker.service"),
        ("systemctl", "disable", "docker.socket"),
    )

    narrow = _Commands()
    units.disable_units(runner=narrow, units=("docker.socket", "k3s-agent.service"))

    assert tuple(narrow.argvs) == (("systemctl", "disable", "docker.socket"),)


# `ip -o link show` on the host mid-install: the loopback and the physical
# link (neither Docker's), the tailnet and k3s links (which a wrong answer
# would take the host off the network with), `docker0`, and two veths
# mastered by it.
_LINK_SHOW = (
    "1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 state UNKNOWN\\    link/loopback\n"
    "2: enp2s0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 state UP\\    link/ether\n"
    "3: tailscale0: <POINTOPOINT,MULTICAST,NOARP,UP> mtu 1280 state UNKNOWN\\    link/none\n"
    "4: flannel.1: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1450 master cni0 state UNKNOWN\n"
    "5: docker0: <NO-CARRIER,BROADCAST,MULTICAST,UP> mtu 1500 state DOWN\\    link/ether\n"
    "7: veth1a2b3c@if6: <BROADCAST,MULTICAST,UP> mtu 1500 master docker0 state UP\n"
    "9: veth4d5e6f@if8: <BROADCAST,MULTICAST,UP> mtu 1500 master docker0 state UP\n"
    "\n"
)

_LINK_SHOW_ARGV = ("ip", "-o", "link", "show")


def test_the_interface_action_deletes_docker0_and_every_veth_mastered_by_it(
    tmp_path: Path,
) -> None:
    """The bridge and its veths go, and nothing the host needs to stay up does.

    `docker0` is deleted LAST, after the links mastered by it, so no veth
    is left orphaned if the pass stops part way. The selection is by
    `master docker0` rather than by a name prefix, because a veth's name is
    random and `flannel.1` -- mastered by `cni0` -- is exactly the shape a
    prefix or substring match would get wrong.
    """
    netstate = importlib.import_module(_NETSTATE_MODULE)
    assert hasattr(netstate, "delete_bridge_interfaces")
    commands = _Commands(answers={_LINK_SHOW_ARGV: _LINK_SHOW})
    host = _real_host(root=tmp_path, commands=commands)

    deleted = host.delete_bridge_interfaces()

    assert deleted == ("veth1a2b3c", "veth4d5e6f", "docker0")
    assert tuple(commands.argvs) == (
        _LINK_SHOW_ARGV,
        ("ip", "link", "delete", "veth1a2b3c"),
        ("ip", "link", "delete", "veth4d5e6f"),
        ("ip", "link", "delete", "docker0"),
    )
    assert commands.argvs_with(flag="tailscale0") == ()
    assert commands.argvs_with(flag="flannel.1") == ()


def _write_sysctl_snapshot(*, root: Path) -> Path:
    """A run's `before/` directory holding only the five recorded sysctls."""
    snapshot = root / "var" / "runs" / "run-a" / "before"
    snapshot.mkdir(parents=True, exist_ok=True)
    _ = (snapshot / "sysctl.json").write_text(json.dumps(_SYSCTL_BEFORE), encoding="utf-8")
    return snapshot


def test_the_sysctl_action_reports_each_watched_value_that_moved(
    tmp_path: Path,
) -> None:
    """Five values compared with the snapshot, and every difference named.

    A flipped `bridge-nf-call-iptables` or a cleared `ip_forward` is
    exactly the kind of damage that is invisible until a pod on another
    node stops answering, so the comparison reports BOTH the recorded and
    the current value: an operator reading `rollback-partial` needs to
    know which way the value moved to put it back. Values that match are
    silent -- a report that named all five every time would bury the one
    that matters.
    """
    netstate = importlib.import_module(_NETSTATE_MODULE)
    assert hasattr(netstate, "compare_sysctls")
    snapshot = _write_sysctl_snapshot(root=tmp_path)
    moved = dict(_SYSCTL_BEFORE)
    moved["net.ipv4.ip_forward"] = "0"
    moved["net.bridge.bridge-nf-call-iptables"] = "0"
    commands = _Commands(
        answers={("sysctl", "-n", name): f"{value}\n" for name, value in moved.items()}
    )
    host = _real_host(root=tmp_path, commands=commands)

    assert host.compare_sysctls(snapshot=snapshot) == (
        "net.bridge.bridge-nf-call-iptables 1 -> 0",
        "net.ipv4.ip_forward 1 -> 0",
    )

    quiet = _Commands(answers=_sysctl_answers())

    assert _real_host(root=tmp_path, commands=quiet).compare_sysctls(snapshot=snapshot) == ()


_GUARD_OWN_UNITS = (
    "docker-engine-guard-observe.service",
    "docker-engine-guard-start.service",
)


@dataclass(kw_only=True)
class _Sleeps:
    """A recorded sleeper, so a bounded wait is asserted without one."""

    seconds: list[float] = field(default_factory=list)

    def __call__(self, *, seconds: float) -> None:
        self.seconds.append(seconds)


def _active_state_argv(*, unit: str) -> tuple[str, ...]:
    """The read of one unit's `ActiveState`."""
    return ("systemctl", "show", "--property", "ActiveState", "--value", unit)


def test_the_unit_stop_action_kills_the_observer_and_starter_then_waits() -> None:
    """The observer and the starter go first, and the rollback WAITS for them.

    Design H2: a still-running observer has a Docker API request it may
    yet submit, so revoking the start permission before it is gone leaves
    a sample that can touch a later run's daemon. `systemctl stop` is
    bounded at ten seconds and followed by a control-group SIGKILL
    because the observer may be blocked inside that very request, and the
    wait is BOUNDED too -- a unit that will not go inactive is reported so
    the driver can write `rollback-partial` instead of hanging.
    """
    units = importlib.import_module(_UNITS_MODULE)
    assert hasattr(units, "stop_guard_units")
    assert units.GUARD_OWN_UNITS == _GUARD_OWN_UNITS

    gone = _Commands(
        answers={_active_state_argv(unit=unit): "inactive\n" for unit in _GUARD_OWN_UNITS}
    )
    patient = _Sleeps()

    assert units.stop_guard_units(runner=gone, sleep=patient) == ()
    assert tuple(gone.argvs) == (
        ("systemctl", "stop", _GUARD_OWN_UNITS[0]),
        ("systemctl", "kill", "--kill-whom=all", "--signal=SIGKILL", _GUARD_OWN_UNITS[0]),
        ("systemctl", "stop", _GUARD_OWN_UNITS[1]),
        ("systemctl", "kill", "--kill-whom=all", "--signal=SIGKILL", _GUARD_OWN_UNITS[1]),
        _active_state_argv(unit=_GUARD_OWN_UNITS[0]),
        _active_state_argv(unit=_GUARD_OWN_UNITS[1]),
    )
    assert gone.timeouts[:4] == [units.GUARD_UNIT_SIGKILL_SECONDS] * 4
    assert gone.timeouts[4:] == [units.UNIT_READ_TIMEOUT_SECONDS] * 2
    assert patient.seconds == []

    stuck = _Commands(
        answers={
            _active_state_argv(unit=_GUARD_OWN_UNITS[0]): "active\n",
            _active_state_argv(unit=_GUARD_OWN_UNITS[1]): "inactive\n",
        }
    )
    waited = _Sleeps()

    assert units.stop_guard_units(runner=stuck, sleep=waited) == (_GUARD_OWN_UNITS[0],)
    assert waited.seconds == [units.GUARD_UNIT_POLL_SECONDS] * units.GUARD_UNIT_WAIT_POLLS


_SS_ARGV = ("ss", "-lx", "--no-header")
_SS_WITHOUT_DOCKER = "u_str LISTEN 0 4096 /run/systemd/private 12345 * 0\n"
_SS_WITH_DOCKER = _SS_WITHOUT_DOCKER + "u_str LISTEN 0 4096 /run/docker.sock 54321 * 0\n"

_ONLY_K3S_JOB = "  12 k3s-agent.service  start running\n\n1 jobs listed.\n"

_LINK_SHOW_WITHOUT_BRIDGE = (
    "1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 state UNKNOWN\\    link/loopback\n"
    "3: tailscale0: <POINTOPOINT,MULTICAST,NOARP,UP> mtu 1280 state UNKNOWN\\    link/none\n"
)


def _tasks_argv(*, unit: str) -> tuple[str, ...]:
    """The read of one unit's current control-group task count."""
    return ("systemctl", "show", "--property", "TasksCurrent", "--value", unit)


def _postcondition_answers(
    *, tasks: str, sockets: str, jobs: str, links: str
) -> dict[tuple[str, ...], str]:
    """The recorded replies every postcondition read needs."""
    answers = {
        _SS_ARGV: sockets,
        _LIST_JOBS_ARGV: jobs,
        _LINK_SHOW_ARGV: links,
    }
    for unit in ("containerd.service", "docker.service", "docker.socket"):
        answers[_tasks_argv(unit=unit)] = tasks
    return answers


def test_the_postcondition_read_reports_all_eight_facts_as_one_record(
    tmp_path: Path,
) -> None:
    """One record, read after every stop phase, naming each postcondition.

    ONE record and not eight calls, because the driver writes
    `rolled-back` only when EVERY postcondition holds and names each
    failing one otherwise -- a partial answer assembled from separate
    reads could report a host as clean while a later read was still
    pending. The eight are the specification's own set: the permission,
    the socket, the processes, the queued jobs, both FORWARD policies, the
    Docker rules, `docker0`, and the watched sysctls.
    """
    assert _POSTCONDITIONS_PATH.is_file()
    clean_root = tmp_path / "clean"
    snapshot = _write_snapshot(root=clean_root)
    _ = (snapshot / "sysctl.json").write_text(json.dumps(_SYSCTL_BEFORE), encoding="utf-8")
    clean = _Commands(
        answers={
            **_sysctl_answers(),
            **_postcondition_answers(
                tasks="0",
                sockets=_SS_WITHOUT_DOCKER,
                jobs=_ONLY_K3S_JOB,
                links=_LINK_SHOW_WITHOUT_BRIDGE,
            ),
        },
        tables=_before_tables(),
    )

    assert _real_host(root=clean_root, commands=clean).read_postconditions(snapshot=snapshot) == {
        "no_start_permission": True,
        "no_docker_socket": True,
        "no_guarded_process": True,
        "no_queued_job": True,
        "forward_policies_restored": True,
        "no_docker_rule": True,
        "no_docker0": True,
        "sysctls_restored": True,
    }

    dirty_root = tmp_path / "dirty"
    dirty_snapshot = _write_snapshot(root=dirty_root)
    _ = (dirty_snapshot / "sysctl.json").write_text(json.dumps(_SYSCTL_BEFORE), encoding="utf-8")
    (dirty_root / "run").mkdir(parents=True, exist_ok=True)
    _ = (dirty_root / "run" / "allow-start").write_text("run-a\n", encoding="utf-8")
    opened = dict(_after_tables())
    opened[("iptables-save", "filter")] = [
        line.replace(":FORWARD DROP", ":FORWARD ACCEPT") for line in _IPV4_FILTER_AFTER
    ]
    dirty = _Commands(
        answers={
            **{("sysctl", "-n", name): "0\n" for name in _SYSCTL_BEFORE},
            **_postcondition_answers(
                tasks="7",
                sockets=_SS_WITH_DOCKER,
                jobs=_LIST_JOBS,
                links=_LINK_SHOW,
            ),
        },
        tables=opened,
    )

    assert _real_host(root=dirty_root, commands=dirty).read_postconditions(
        snapshot=dirty_snapshot
    ) == {
        "no_start_permission": False,
        "no_docker_socket": False,
        "no_guarded_process": False,
        "no_queued_job": False,
        "forward_policies_restored": False,
        "no_docker_rule": False,
        "no_docker0": False,
        "sysctls_restored": False,
    }


# The three guarded units mapped to their systemd D-Bus object paths. The
# escaping is the product's job, so the paths are written out here rather
# than computed: a test that recomputed them would pass against the same
# mistake it was meant to catch.
_UNIT_OBJECT_PATHS = {
    "containerd.service": "containerd_2eservice",
    "docker.service": "docker_2eservice",
    "docker.socket": "docker_2esocket",
}


def _conditions_argv(*, unit: str) -> tuple[str, ...]:
    """The `busctl` read of one unit's effective `Conditions` property."""
    return (
        "busctl",
        "--json=short",
        "get-property",
        "org.freedesktop.systemd1",
        f"/org/freedesktop/systemd1/unit/{_UNIT_OBJECT_PATHS[unit]}",
        "org.freedesktop.systemd1.Unit",
        "Conditions",
    )


def _conditions_json(*, rows: list[list[object]]) -> str:
    """`busctl --json=short` as it renders an `a(sbbsi)` property."""
    return json.dumps({"type": "a(sbbsi)", "data": rows})


def _guard_conditions(*, root: Path) -> list[list[object]]:
    """The guard's own two OR'd path conditions, in the shape busctl reports."""
    return [
        ["ConditionPathExists", True, False, str(root / "run" / "allow-start"), 0],
        ["ConditionPathExists", True, False, str(root / "var" / "confirmed"), 0],
    ]


def _conditions_bus(*, root: Path, overrides: dict[str, str] | None = None) -> _Commands:
    """A bus answering each guarded unit's condition read, with overrides."""
    answers = {
        _conditions_argv(unit=unit): _conditions_json(rows=_guard_conditions(root=root))
        for unit in _UNIT_OBJECT_PATHS
    }
    for unit, payload in (overrides or {}).items():
        answers[_conditions_argv(unit=unit)] = payload
    return _Commands(answers=answers)


def test_the_condition_check_passes_only_on_exactly_the_two_or_path_conditions(
    tmp_path: Path,
) -> None:
    """Effective conditions, read through busctl, and nothing else accepted.

    Rider point 6: the conditions are read from the service manager's own
    parsed list over D-Bus, because `systemctl show -p Conditions` renders
    unprintable on gmktec's systemd 259 -- so a text scrape would compare
    against garbage and pass. EXACTLY two is the requirement in both
    directions: a third condition could admit a start the guard never
    permitted, and a missing one means the OR has only one way to be
    satisfied. An unreadable answer fails CLOSED, because "no conditions
    reported" and "no conditions configured" are indistinguishable.
    """
    assert _CONDITIONS_PATH.is_file()
    passing = _conditions_bus(root=tmp_path)

    assert _real_host(root=tmp_path, commands=passing).condition_check_passed() is True
    assert tuple(passing.argvs) == tuple(_conditions_argv(unit=unit) for unit in _UNIT_OBJECT_PATHS)

    extra = _guard_conditions(root=tmp_path)
    extra.append(["ConditionPathExists", True, False, "/run/somebody-elses-flag", 0])
    third = _conditions_bus(
        root=tmp_path, overrides={"docker.socket": _conditions_json(rows=extra)}
    )

    assert _real_host(root=tmp_path, commands=third).condition_check_passed() is False

    only_one = _conditions_bus(
        root=tmp_path,
        overrides={"docker.service": _conditions_json(rows=_guard_conditions(root=tmp_path)[:1])},
    )

    assert _real_host(root=tmp_path, commands=only_one).condition_check_passed() is False

    unreadable = _conditions_bus(root=tmp_path, overrides={"containerd.service": ""})

    assert _real_host(root=tmp_path, commands=unreadable).condition_check_passed() is False


# The two drop-in filenames the guarded host is allowed to carry, written
# out rather than imported for the same reason the object paths above are:
# a test that read them from the module under test would accept whatever
# that module happened to say.
_GUARD_DROPIN = "50-docker-engine-guard.conf"
_SANDBOX_STORAGE_DROPIN = "10-requires-sandbox-storage.conf"


def _dropin_tree(*, root: Path, dropins: dict[str, tuple[str, ...]]) -> Path:
    """A `/etc/systemd/system` holding exactly `dropins` for each named unit."""
    unit_directory = root / "etc" / "systemd" / "system"
    for unit, names in dropins.items():
        directory = unit_directory / f"{unit}.d"
        directory.mkdir(parents=True, exist_ok=True)
        for name in names:
            _ = (directory / name).write_text("[Unit]\n", encoding="utf-8")
    return unit_directory


def test_the_dropin_check_accepts_the_guards_own_and_the_sandbox_storage_dropins(
    tmp_path: Path,
) -> None:
    """Design G6 plus rider point 7: the sanctioned set, on both real hosts.

    G6 has the role refuse any drop-in other than its own, because a
    pre-existing override is exactly how the condition gate would be
    defeated -- a drop-in loaded after the guard's can add a start path the
    guard never granted. Rider point 7 then carves out the one override
    the fleet itself installs: `sandbox_storage` writes
    `RequiresMountsFor` for `containerd.service` and `docker.service`, and
    refusing on it would make this guard unusable on hp.

    BOTH real hosts have to pass, which is why the second half asserts the
    bare tree: the sandbox drop-ins are present on hp and ABSENT on
    gmktec, so a check that required them would refuse the very host the
    guard was written for.
    """
    conditions = importlib.import_module(_CONDITIONS_MODULE)
    assert hasattr(conditions, "unexpected_dropins")

    hp = _dropin_tree(
        root=tmp_path / "hp",
        dropins={
            "containerd.service": (_GUARD_DROPIN, _SANDBOX_STORAGE_DROPIN),
            "docker.service": (_GUARD_DROPIN, _SANDBOX_STORAGE_DROPIN),
            "docker.socket": (_GUARD_DROPIN,),
        },
    )

    assert conditions.unexpected_dropins(unit_directory=hp) == ()

    gmktec = _dropin_tree(
        root=tmp_path / "gmktec",
        dropins={
            "containerd.service": (_GUARD_DROPIN,),
            "docker.service": (_GUARD_DROPIN,),
            "docker.socket": (_GUARD_DROPIN,),
        },
    )

    assert conditions.unexpected_dropins(unit_directory=gmktec) == ()

    # A host whose drop-in directories do not exist at all: the read is a
    # survey, so nothing to survey is not a finding.
    assert conditions.unexpected_dropins(unit_directory=tmp_path / "absent") == ()


def test_the_dropin_check_refuses_a_dropin_outside_that_set(tmp_path: Path) -> None:
    """Design G6: anything but the sanctioned set is refused, and NAMED.

    This is the other half of the start-condition proof. The two OR'd
    conditions only hold while nothing else edits these units: a drop-in
    that systemd loads after the guard's can add a start path the guard
    never granted, and the condition read would still report exactly two
    because the addition is not a condition. So an unknown drop-in is
    refused on sight, before any package is installed.

    `docker.socket` is the discriminating case. It mounts no store, so
    `sandbox_storage` never writes a drop-in for it -- a sandbox drop-in
    there was installed by something else and is refused even though the
    SAME FILENAME is sanctioned on the two services. A check that held one
    flat filename allow-list would miss it.

    The refusal NAMES each offender because "a drop-in is unexpected" is
    not something an operator can act on at 2am.
    """
    conditions = importlib.import_module(_CONDITIONS_MODULE)
    assert hasattr(conditions, "dropin_check_passed")

    tampered = _dropin_tree(
        root=tmp_path / "tampered",
        dropins={
            "containerd.service": (_GUARD_DROPIN, _SANDBOX_STORAGE_DROPIN),
            "docker.service": (_GUARD_DROPIN, "99-operator-override.conf"),
            "docker.socket": (_GUARD_DROPIN, _SANDBOX_STORAGE_DROPIN),
        },
    )

    assert conditions.dropin_check_passed(unit_directory=tampered) is False
    assert conditions.unexpected_dropins(unit_directory=tampered) == (
        "docker.service.d/99-operator-override.conf",
        f"docker.socket.d/{_SANDBOX_STORAGE_DROPIN}",
    )

    # The sanctioned tree still passes the verdict, not just the survey.
    sanctioned = _dropin_tree(
        root=tmp_path / "sanctioned",
        dropins={
            "containerd.service": (_GUARD_DROPIN, _SANDBOX_STORAGE_DROPIN),
            "docker.service": (_GUARD_DROPIN, _SANDBOX_STORAGE_DROPIN),
            "docker.socket": (_GUARD_DROPIN,),
        },
    )

    assert conditions.dropin_check_passed(unit_directory=sanctioned) is True

    # A file systemd does not load from a `.d` directory is not a drop-in:
    # refusing on a leftover `.conf.bak` would block the install on
    # something that cannot affect a start at all.
    ignored = _dropin_tree(
        root=tmp_path / "ignored",
        dropins={
            "containerd.service": (_GUARD_DROPIN, "99-disabled.conf.bak"),
            "docker.service": (_GUARD_DROPIN,),
            "docker.socket": (_GUARD_DROPIN,),
        },
    )

    assert conditions.dropin_check_passed(unit_directory=ignored) is True


def test_the_dead_man_recipe_reaches_systemd_run_with_collect_and_both_budgets(
    tmp_path: Path,
) -> None:
    """Rider points 2 and 9: `--collect`, `AccuracySec=1s`, `TimeoutStartSec=900`.

    Each of the three is a measured fix, not a default worth restating:

    - `--collect` (rider 9) because a transient unit that FAILED stays
      loaded in `failed` state, and the next `arm` for the same run then
      collides with the corpse of the last one instead of creating the
      timer. Admission classifies a failed dead-man, and `--collect` is
      what stops it accumulating.
    - `TimeoutStartSec=900` (rider 2) because the dead-man's own service
      has to outlive the whole rollback budget. At the previous 600 s the
      service manager would SIGKILL the primary rollback path before its
      final postcondition check -- a rollback cut off mid-teardown, which
      is the one state this guard exists to avoid.
    - `AccuracySec=1s` because systemd's default timer accuracy is a
      MINUTE, and a dead-man that may fire up to a minute late is a
      deadline the run can overrun.

    Asserted on the argv the host actually EMITTED rather than on the
    recipe builder's return value: the recipe is only worth anything if it
    reaches `systemd-run` unaltered, through the same bounded runner every
    other host action uses.
    """
    model = importlib.import_module(_MODEL_MODULE)
    units = importlib.import_module(_UNITS_MODULE)
    recipe = model.deadman_argv(run="run-a", on_active_seconds=360)
    commands = _Commands()

    _real_host(root=tmp_path, commands=commands).systemd_run(argv=recipe)

    assert tuple(commands.argvs) == (recipe,)
    emitted = commands.argvs[0]
    assert emitted[0] == "systemd-run"
    assert "--collect" in emitted
    assert "--timer-property=AccuracySec=1s" in emitted
    assert "--property=TimeoutStartSec=900" in emitted
    assert "--unit=docker-engine-deadman-run-a" in emitted
    assert "--on-active=360" in emitted
    assert emitted[-2:] == ("rollback", "run-a")
    assert commands.timeouts == [units.UNIT_ACTION_TIMEOUT_SECONDS]


def test_the_real_host_declares_every_seam_the_host_protocol_names() -> None:
    """`RealHost` stays a complete `HostOps` as siblings widen the protocol.

    Children 1b and 2 added post-commit, reconfigure and rollback-phase
    seams to `HostOps` while this host was being built, so a real host
    missing any of them is no longer the `HostOps` the guard's entry
    point promises. A seam no child has built yet still has to EXIST and
    raise, so the guard fails loudly at that seam rather than at import.
    """
    hostops = importlib.import_module(_HOSTOPS_MODULE)
    host_module = importlib.import_module(_HOST_MODULE)
    declared = {name for name in dir(hostops.HostOps) if not name.startswith("_")}

    assert declared - set(dir(host_module.RealHost)) == set()


_BOOT_ID = "6f0d2b1e-9d4c-4a9f-8f8e-2f1b7c0a5d33"
_BOOT_ID_RELATIVE = Path("sys/kernel/random/boot_id")


def _proc_tree(*, root: Path, boot_id: str = f"{_BOOT_ID}\n") -> Path:
    """A recorded `/proc` carrying this boot's id exactly as the kernel writes it."""
    proc_root = root / "proc"
    (proc_root / _BOOT_ID_RELATIVE.parent).mkdir(parents=True, exist_ok=True)
    _ = (proc_root / _BOOT_ID_RELATIVE).write_text(boot_id, encoding="utf-8")
    return proc_root


def _host_on(*, root: Path, commands: _Commands, proc_root: Path) -> Any:
    """The real host rooted under `root`, reading a RECORDED `/proc` tree."""
    model = importlib.import_module(_MODEL_MODULE)
    host_module = importlib.import_module(_HOST_MODULE)
    paths = model.GuardPaths(state_root=root / "var", runtime_root=root / "run")
    return host_module.build_real_host(paths=paths, runner=commands, proc_root=proc_root)


def test_the_clock_reads_monotonic_seconds_this_boots_id_and_waits_when_asked(
    tmp_path: Path,
) -> None:
    """A deadline is a boot id AND a monotonic instant, and neither is a command.

    The wall clock is not either half, on purpose: it steps under NTP
    and means nothing across a reboot, so a deadline recorded against
    it would be a deadline that an administrator could move. The boot
    id comes from the kernel's own `/proc/sys/kernel/random/boot_id`
    and is STRIPPED, because the kernel ends it with a newline and a
    deadline comparison is a string comparison -- an unstripped id
    matches nothing, so every recorded deadline would read as belonging
    to another boot and every run would be out of time the moment it
    was armed.

    The `/proc` root is a FIELD on the host for exactly the reason the
    runner is: it is what makes the boot-id read drivable against a
    recorded tree rather than against this machine's own boot.
    """
    assert _CLOCK_PATH.is_file()
    clock = importlib.import_module(_CLOCK_MODULE)
    commands = _Commands()
    host = _host_on(root=tmp_path, commands=commands, proc_root=_proc_tree(root=tmp_path))

    assert host.boot_id() == _BOOT_ID

    before = host.monotonic()
    host.sleep(seconds=0.01)
    after = host.monotonic()

    assert isinstance(before, float)
    assert after >= before + 0.01
    assert clock.monotonic_seconds() >= after
    # Reading a clock and waiting are not external commands, so neither
    # reaches the one timed runner and neither can be bounded by it.
    assert commands.argvs == []


def _guard_paths(*, root: Path) -> Any:
    """The same `GuardPaths` the recorded host below is rooted at."""
    model = importlib.import_module(_MODEL_MODULE)
    return model.GuardPaths(state_root=root / "var", runtime_root=root / "run")


def test_the_start_permission_is_created_removed_and_its_directory_root_owned(
    tmp_path: Path,
) -> None:
    """The one file between an unguarded host and a Docker daemon, and its directory.

    Three properties, and each is the one a careless implementation
    loses:

    - The grant leaves NO temporary beside the permission. The guarded
      units read it with `ConditionPathExists`, so a half-written file
      under the final name would admit a start the guard has not
      authorised; the write therefore lands under another name and is
      RENAMED, and the directory holds exactly one entry afterwards.
    - The revoke succeeds when the permission is already absent. It is
      the FIRST act of every rollback, and a rollback re-fired by the
      dead-man every sixty seconds meets an already-revoked permission
      on all but its first firing -- raising there would abort the
      teardown at step one, forever.
    - Neither reaches the runner. They are filesystem acts on tmpfs, so
      there is no command to bound; the ownership of the directory IS a
      command, because the guard cannot change a file's owner without
      leaving its own process.
    """
    assert _PERMISSION_PATH.is_file()
    permission = importlib.import_module(_PERMISSION_MODULE)
    paths = _guard_paths(root=tmp_path)
    commands = _Commands()
    host = _real_host(root=tmp_path, commands=commands)

    host.revoke_start_permission()

    assert not paths.permission.exists()

    host.grant_start_permission()

    assert paths.permission.is_file()
    assert sorted(entry.name for entry in paths.runtime_root.iterdir()) == [paths.permission.name]

    host.grant_start_permission()

    assert paths.permission.is_file()

    host.revoke_start_permission()

    assert not paths.permission.exists()
    assert commands.argvs == []

    host.set_owner_root(path=paths.runtime_root)

    assert tuple(commands.argvs) == (("chown", "root:root", str(paths.runtime_root)),)
    assert commands.timeouts == [permission.OWNERSHIP_TIMEOUT_SECONDS]


# The three globs the admission read asks the service manager to expand:
# the guard's own fixed-identity units and any other
# `docker-engine-guard-*.service`, plus the dead-man's timer and the
# service it triggers (design I1).
_GUARD_SHOW_ARGV = (
    "systemctl",
    "show",
    "--property",
    "Id",
    "--property",
    "ActiveState",
    "docker-engine-guard-*.service",
    "docker-engine-deadman-*.service",
    "docker-engine-deadman-*.timer",
)

# What that read answers on a host mid-run: the observer quiet, the
# starter FAILED -- not inactive, and admission has to name it -- and
# this run's dead-man in the air. Records are separated by a blank line
# and each opens with the `Id=` the read asked for first.
_GUARD_SHOW = (
    "Id=docker-engine-guard-observe.service\n"
    "ActiveState=inactive\n"
    "\n"
    "Id=docker-engine-guard-start.service\n"
    "ActiveState=failed\n"
    "\n"
    "Id=docker-engine-deadman-run-a.timer\n"
    "ActiveState=active\n"
)

# Enablement and running state are INDEPENDENT facts, so the recorded
# tree makes them disagree: the socket is installed but not enabled,
# which a reader conflating the two would report as fine.
_ENABLED_STATES = {
    "containerd.service": "enabled",
    "docker.service": "enabled",
    "docker.socket": "disabled",
}

_DEADMAN_TIMER = "docker-engine-deadman-run-a.timer"
_OTHER_DEADMAN_TIMER = "docker-engine-deadman-run-b.timer"

_INVOKING_CGROUP = "0::/system.slice/docker-engine-guard-start.service\n"


def _enabled_state_argv(*, unit: str) -> tuple[str, ...]:
    """The read of one unit's `UnitFileState`."""
    return ("systemctl", "show", "--property", "UnitFileState", "--value", unit)


def _load_state_argv(*, unit: str) -> tuple[str, ...]:
    """The read of whether the service manager has one unit loaded at all."""
    return ("systemctl", "show", "--property", "LoadState", "--value", unit)


def _with_cgroup(*, proc_root: Path, text: str) -> Path:
    """The same recorded `/proc`, carrying this invocation's own cgroup line."""
    (proc_root / "self").mkdir(parents=True, exist_ok=True)
    _ = (proc_root / "self" / "cgroup").write_text(text, encoding="utf-8")
    return proc_root


def test_the_admission_reads_name_every_guard_unit_its_state_and_this_invocation(
    tmp_path: Path,
) -> None:
    """Design I1's four reads, and each one's trap.

    - The guard units are ENUMERATED by glob, never listed. The set
      includes the dead-man units of whatever run holds the host, whose
      names carry a run id this invocation does not know, so a fixed
      list would be blind to exactly the unit that says an earlier run
      is still being torn down.
    - `failed` is reported as itself. It is not `inactive`, and a read
      that folded the two together would admit a reservation beside a
      dead-man service that tried to roll a host back and could not.
    - Enablement is read SEPARATELY from running state and they are
      allowed to disagree: enabling carries the engine across the next
      boot and running carries it across this one, and neither implies
      the other.
    - This invocation's own unit comes from its cgroup, because it is
      necessarily active while it runs and every admission check has to
      exclude it. A `/proc/self/cgroup` with no unified line names no
      unit at all rather than guessing one.
    """
    assert _UNIT_STATE_PATH.is_file()
    unit_state = importlib.import_module(_UNIT_STATE_MODULE)
    units = importlib.import_module(_UNITS_MODULE)
    commands = _Commands(
        answers={
            _GUARD_SHOW_ARGV: _GUARD_SHOW,
            _load_state_argv(unit=_DEADMAN_TIMER): "loaded\n",
            _active_state_argv(unit=_DEADMAN_TIMER): "active\n",
            _load_state_argv(unit=_OTHER_DEADMAN_TIMER): "not-found\n",
            _active_state_argv(unit=_OTHER_DEADMAN_TIMER): "inactive\n",
            **{
                _enabled_state_argv(unit=unit): f"{state}\n"
                for unit, state in _ENABLED_STATES.items()
            },
        }
    )
    host = _host_on(
        root=tmp_path,
        commands=commands,
        proc_root=_with_cgroup(proc_root=_proc_tree(root=tmp_path), text=_INVOKING_CGROUP),
    )

    assert host.guard_unit_states() == {
        "docker-engine-guard-observe.service": "inactive",
        "docker-engine-guard-start.service": "failed",
        _DEADMAN_TIMER: "active",
    }
    assert host.unit_enabled_states() == _ENABLED_STATES
    assert host.invoking_unit() == "docker-engine-guard-start.service"
    assert host.deadman_timer_exists(run="run-a") is True
    assert host.deadman_timer_active(run="run-a") is True
    assert host.deadman_timer_exists(run="run-b") is False
    assert host.deadman_timer_active(run="run-b") is False
    assert commands.argvs[0] == _GUARD_SHOW_ARGV
    assert set(commands.timeouts) == {units.UNIT_READ_TIMEOUT_SECONDS}

    legacy = _with_cgroup(
        proc_root=_proc_tree(root=tmp_path / "legacy"),
        text="1:name=systemd:/user.slice/user-1000.slice\n",
    )

    assert unit_state.invoking_unit(proc_root=legacy) == ""


def test_the_start_and_enable_actions_reach_only_the_guarded_units(
    tmp_path: Path,
) -> None:
    """Starting carries the engine across THIS boot; enabling across the next.

    Rider point 9: the post-commit steps issue both, because neither
    implies the other -- an enabled-but-stopped Docker on a committed
    host is an engine that only comes back at a reboot, and a started
    one that was never enabled is an engine the next boot loses.

    The enable is narrowed to the guarded set and issues ONE command
    per unit, for the two reasons the disable beside it is: a caller
    that named `k3s-agent.service` -- by defect, by a mis-parsed read,
    or by a later refactor -- still cannot reach it, and a unit whose
    enable fails does not take the other two down with it. The start
    carries the CALLER's timeout rather than the module's, because the
    bound on a unit start is the lifecycle's budget to set.
    """
    units = importlib.import_module(_UNITS_MODULE)
    assert hasattr(units, "start_unit")
    assert hasattr(units, "enable_units")
    commands = _Commands()

    _real_host(root=tmp_path, commands=commands).start_unit(
        unit="containerd.service", timeout_seconds=42
    )

    assert tuple(commands.argvs) == (("systemctl", "start", "containerd.service"),)
    assert commands.timeouts == [42]

    enabling = _Commands()

    _real_host(root=tmp_path, commands=enabling).enable_units(
        units=("docker.service", "k3s-agent.service", "docker.socket", "containerd.service")
    )

    assert tuple(enabling.argvs) == (
        ("systemctl", "enable", "containerd.service"),
        ("systemctl", "enable", "docker.service"),
        ("systemctl", "enable", "docker.socket"),
    )
    assert set(enabling.timeouts) == {units.UNIT_ACTION_TIMEOUT_SECONDS}

    # A guarded unit the caller did NOT name stays unenabled: the
    # narrowing bounds what may be reached, and the caller's set still
    # decides what is.
    partial = _Commands()

    _real_host(root=tmp_path, commands=partial).enable_units(units=("docker.service",))

    assert tuple(partial.argvs) == (("systemctl", "enable", "docker.service"),)


# A daemon configuration this role does NOT own, plus one owned key
# carrying a stale value. Both halves matter: the foreign keys prove the
# write is a merge, and the stale owned key proves the merge is not an
# append.
_FOREIGN_DAEMON_KEYS = {
    "insecure-registries": [],
    "log-driver": "journald",
}
_STALE_OWNED_KEYS = {"cgroup-parent": "a-previous-run.slice"}

_OWNED_DAEMON_KEYS = {
    "cgroup-parent": "fabro-sandbox.slice",
    "live-restore": True,
}


def _configuring_host(*, root: Path, commands: _Commands, config: Path, marker: Path) -> Any:
    """The real host with its daemon configuration and restart marker redirected."""
    model = importlib.import_module(_MODEL_MODULE)
    host_module = importlib.import_module(_HOST_MODULE)
    paths = model.GuardPaths(state_root=root / "var", runtime_root=root / "run")
    return host_module.build_real_host(
        paths=paths, runner=commands, daemon_config=config, restart_marker=marker
    )


def test_the_reconfigure_seams_merge_the_owned_keys_and_only_record_a_restart(
    tmp_path: Path,
) -> None:
    """Keys this role does not own survive, and nothing is restarted.

    Two properties, and both are the specification's rather than this
    module's taste:

    - Only the OWNED keys are written. A key this role did not write
      belongs to whoever did, and the digest the commit marker carries
      covers the owned set alone -- so a write that replaced the file
      would make a foreign key's disappearance read as a guarded
      reconfiguration on the next converge. An owned key already in the
      file is OVERWRITTEN, which is the whole point of reconfiguring.
    - The restart is RECORDED, never performed. After the commit point
      the host is running sandbox containers under this very daemon, so
      an immediate restart would kill the work the host exists to do;
      the marker is the `docker_sandbox_slice` role's own deferred-
      restart mechanism, and the operator who opens the drained window
      is not necessarily the one who ran the converge.

    The two real locations are asserted by value, because they are
    shared with an Ansible role: the configuration is
    `/etc/docker/daemon.json` and the marker is that role's
    `docker_sandbox_slice_pending_restart_marker` default. A host
    writing either one somewhere else would leave the role's own
    converge reading a file nothing updates.
    """
    assert _DAEMON_PATH.is_file()
    daemon = importlib.import_module(_DAEMON_MODULE)

    assert Path("/etc/docker/daemon.json") == daemon.DAEMON_CONFIG
    assert Path("/var/lib/docker-sandbox-slice/restart-pending") == daemon.PENDING_RESTART_MARKER

    config = tmp_path / "etc" / "docker" / "daemon.json"
    marker = tmp_path / "var-lib" / "docker-sandbox-slice" / "restart-pending"
    config.parent.mkdir(parents=True)
    _ = config.write_text(
        json.dumps({**_FOREIGN_DAEMON_KEYS, **_STALE_OWNED_KEYS}), encoding="utf-8"
    )
    commands = _Commands()
    host = _configuring_host(root=tmp_path, commands=commands, config=config, marker=marker)

    host.write_daemon_keys(keys=_OWNED_DAEMON_KEYS)

    assert json.loads(config.read_text(encoding="utf-8")) == {
        **_FOREIGN_DAEMON_KEYS,
        **_OWNED_DAEMON_KEYS,
    }

    host.record_pending_drained_restart(unit="docker.service")

    assert "docker.service" in marker.read_text(encoding="utf-8")
    assert commands.argvs == []

    fresh_config = tmp_path / "fresh" / "daemon.json"
    fresh = _configuring_host(
        root=tmp_path / "fresh-root",
        commands=commands,
        config=fresh_config,
        marker=marker,
    )

    fresh.write_daemon_keys(keys=_OWNED_DAEMON_KEYS)

    assert json.loads(fresh_config.read_text(encoding="utf-8")) == _OWNED_DAEMON_KEYS
