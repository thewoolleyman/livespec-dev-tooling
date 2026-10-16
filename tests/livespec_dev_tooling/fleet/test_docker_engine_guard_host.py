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
_RUNNER_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_runner"
_RUNNER_PATH = Path("livespec_dev_tooling/fleet/_docker_engine_guard_runner.py")
_FIREWALL_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_firewall"
_FIREWALL_PATH = Path("livespec_dev_tooling/fleet/_docker_engine_guard_firewall.py")
_ACTIONS_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_firewall_actions"
_ACTIONS_PATH = Path("livespec_dev_tooling/fleet/_docker_engine_guard_firewall_actions.py")
_NETSTATE_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_netstate"
_NETSTATE_PATH = Path("livespec_dev_tooling/fleet/_docker_engine_guard_netstate.py")
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
    """A run's `before/` directory holding the pre-Docker dumps."""
    snapshot = root / "var" / "runs" / "run-a" / "before"
    snapshot.mkdir(parents=True, exist_ok=True)
    for (command, table), lines in _before_tables().items():
        _ = (snapshot / f"{command}.{table}").write_text("\n".join(lines) + "\n", encoding="utf-8")
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
