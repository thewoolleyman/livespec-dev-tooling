"""A sample's firewall comparison, scoped so healthy churn is never a fault.

Governing specification: `SPECIFICATION/non-functional-requirements.md`
section "Docker engine install guard", "Probes" -- "Firewall".
Governing design: `docs/docker-engine-guard-design.md` R4's comparison
scope, as Mechanism 3 item 4 applies it to each sample.

WHY THE SCOPE IS NARROWED, AND IN WHICH DIRECTION. k3s's reconcilers
rewrite the CONTENTS of their own chains continuously -- kube-proxy per
service, kube-router per pod -- on a host that is also a CI pool agent
creating and deleting pods all day. A comparison covering those contents
would fail on every sample of a perfectly healthy machine, and a probe
that always fails is a probe nobody can act on. So the comparison covers
the built-in chain POLICIES, the five built-in chains' OWN rules, and
the contents of the `ts-*` chains -- the three places a change means
either Docker or a fault, and the last of which is the host's only
remote access path.

WHY DOCKER'S OWN FOOTPRINT IS EXCLUDED. The engine is RUNNING during the
window; its bridge rules are the expected result of the install, not a
regression. They are identified by the same pure planner the rollback
removes them with, so the sample and the cleanup agree on what Docker's
footprint is by construction rather than by two lists kept in step.

Stdlib only, Python 3.10 syntax.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from livespec_dev_tooling.fleet._docker_engine_guard_firewall import (
    FAMILIES,
    SNAPSHOT_TABLES,
    FirewallTable,
    plan_footprint,
)
from livespec_dev_tooling.fleet._docker_engine_guard_firewall_actions import (
    read_current_table,
    read_snapshot_table,
)
from livespec_dev_tooling.fleet._docker_engine_guard_sample import ProbeResult

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from livespec_dev_tooling.fleet._docker_engine_guard_runner import GuardCommandRunner

__all__: list[str] = [
    "BUILT_IN_CHAINS",
    "FIREWALL_PROBE",
    "RECONCILER_PREFIXES",
    "TAILSCALE_PREFIX",
    "compared_chains",
    "compared_policies",
    "compared_rules",
    "firewall_differences",
    "firewall_probe",
]

# The five chains the kernel provides, whose policies and own rules are
# compared. They are the chains Docker writes DIRECTLY into (raw
# per-container drops, the nat POSTROUTING masquerade), and the chains
# every packet traverses whatever else exists.
BUILT_IN_CHAINS: Final[frozenset[str]] = frozenset(
    {
        "FORWARD",
        "INPUT",
        "OUTPUT",
        "POSTROUTING",
        "PREROUTING",
    }
)

# tailscaled's own chains. Their contents ARE compared, because they
# carry the host's only remote access path: a change there is the one
# change that could lock the machine out, so it is reported fail-closed
# without claiming Docker caused it.
TAILSCALE_PREFIX: Final[str] = "ts-"

# The chains a reconciler owns and rewrites per service and per pod.
# Recorded as a constant, and NOT consulted by the scope below, which is
# an allow-list: a new reconciler prefix would otherwise have to be
# added here before the probe stopped failing on it. They are named
# anyway because the specification names them, and because a reader has
# to be able to see that leaving them out was a decision.
RECONCILER_PREFIXES: Final[tuple[str, ...]] = (
    "FLANNEL-",
    "KUBE-",
)

FIREWALL_PROBE: Final[str] = "firewall"

# Where a canonical `-A <chain> …` rule carries its chain.
_RULE_CHAIN: Final[int] = 1


def compared_chains(*, table: FirewallTable) -> frozenset[str]:
    """The chains whose CONTENTS this comparison covers, and no others."""
    return frozenset(
        chain
        for chain in table.chains
        if chain in BUILT_IN_CHAINS or chain.startswith(TAILSCALE_PREFIX)
    )


def compared_policies(*, table: FirewallTable) -> Mapping[str, str]:
    """The built-in chains' policies, which are the only chains that have one."""
    return {chain: table.policies[chain] for chain in table.chains if chain in BUILT_IN_CHAINS}


def compared_rules(*, table: FirewallTable) -> frozenset[str]:
    """Every in-scope rule: one that lives in a compared chain."""
    covered = compared_chains(table=table)
    return frozenset(rule for rule in table.rules if rule.split()[_RULE_CHAIN] in covered)


def _policy_differences(
    *, family: str, table: str, current: FirewallTable, recorded: FirewallTable
) -> tuple[str, ...]:
    """Every built-in chain whose policy is not what the snapshot recorded."""
    now = compared_policies(table=current)
    before = compared_policies(table=recorded)
    return tuple(
        f"{family} {table} policy {chain}: "
        f"{before.get(chain, 'absent')} -> {now.get(chain, 'absent')}"
        for chain in sorted(set(before) | set(now))
        if before.get(chain) != now.get(chain)
    )


def _rule_differences(
    *,
    family: str,
    table: str,
    current: FirewallTable,
    recorded: FirewallTable,
    footprint: frozenset[str],
) -> tuple[str, ...]:
    """Every in-scope rule that appeared or disappeared, Docker's own aside.

    BOTH directions are reported. A rule that appeared is the obvious
    case; a rule that DISAPPEARED is the dangerous one -- a missing
    `ts-input` accept is how this host stops answering the only path
    anybody can reach it on.
    """
    now = compared_rules(table=current) - footprint
    before = compared_rules(table=recorded)
    return tuple(
        f"{family} {table} {movement} {rule}"
        for movement, rules in (
            ("appeared", sorted(now - before)),
            ("disappeared", sorted(before - now)),
        )
        for rule in rules
    )


def firewall_differences(*, runner: GuardCommandRunner, snapshot: Path) -> tuple[str, ...]:
    """Every in-scope change since the snapshot that is not Docker's own footprint."""
    found: tuple[str, ...] = ()
    for family in FAMILIES:
        for table in SNAPSHOT_TABLES:
            current = read_current_table(runner=runner, family=family, table=table)
            recorded = read_snapshot_table(snapshot=snapshot, family=family, table=table)
            footprint = frozenset(plan_footprint(current=current, snapshot=recorded).delete_rules)
            found += _policy_differences(
                family=family, table=table, current=current, recorded=recorded
            )
            found += _rule_differences(
                family=family,
                table=table,
                current=current,
                recorded=recorded,
                footprint=footprint,
            )
    return found


def firewall_probe(*, runner: GuardCommandRunner, snapshot: Path) -> ProbeResult:
    """Whether the in-scope firewall state is still what the snapshot recorded."""
    differences = firewall_differences(runner=runner, snapshot=snapshot)
    return ProbeResult(name=FIREWALL_PROBE, passed=not differences, error="; ".join(differences))
