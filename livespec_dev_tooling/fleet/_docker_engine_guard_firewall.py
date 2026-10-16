"""Reading and canonicalizing the guarded host's two firewall families.

Governing design: `docs/docker-engine-guard-design.md` Mechanism 4
("removing exactly Docker's firewall footprint") and R4's scoping rules.
Governing specification: `SPECIFICATION/non-functional-requirements.md`
section "Docker engine install guard", "Host actions".

Nothing here touches the host: this module parses a `*-save` dump and
builds the argv another module runs. Keeping the PARSE and the PLAN pure
is what lets the footprint be decided against recorded output -- the only
way to test "exactly Docker's rules and nothing of k3s's" without a host
whose k3s rules a wrong answer would delete.

WHY TWO COMMAND SPELLINGS. The READS use `iptables-save` /
`ip6tables-save`: a save is not a change, and those are the names the
specification's snapshot clause and the design's probe clause both give.
The CHANGES use `iptables-nft` / `ip6tables-nft`, because the
specification requires firewall changes to use only the iptables-nft
commands and the acceptance host is iptables-1.8.11 on the nft backend
(design, measured state 2026-10-15), where the alternatives-managed
`iptables` IS that binary.

WHITESPACE IS CANONICALIZED IDENTICALLY on both sides (R4): hp shows a
double space inside an `nfacct` rule, and an unnormalized compare would
report that rule as new on every single run.

Stdlib only, Python 3.10 syntax.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

__all__: list[str] = [
    "CHANGE_COMMAND",
    "FAMILIES",
    "FORWARD_POLICY_SNAPSHOT",
    "SAVE_COMMAND",
    "SNAPSHOT_TABLES",
    "FirewallTable",
    "parse_table",
    "save_argv",
    "snapshot_name",
]

# The two address families, in the order every action walks them, so a
# report reads the same way twice.
FAMILIES: Final[tuple[str, ...]] = ("ipv4", "ipv6")

# The tables Docker writes, and so the tables the snapshot has to hold:
# `filter` for the FORWARD gate and the isolation chains, `nat` for the
# masquerade and the port publishing. Both carry a `DOCKER` chain of
# their own, which is why the footprint is planned per TABLE and not per
# family (design Mechanism 4).
SNAPSHOT_TABLES: Final[tuple[str, ...]] = ("filter", "nat")

SAVE_COMMAND: Final[Mapping[str, str]] = {
    "ipv4": "iptables-save",
    "ipv6": "ip6tables-save",
}

CHANGE_COMMAND: Final[Mapping[str, str]] = {
    "ipv4": "iptables-nft",
    "ipv6": "ip6tables-nft",
}

# Where the snapshot records each family's FORWARD policy. It is derived
# from the family's own `filter` dump rather than read with a second
# command, so the policy and the rules it governs can never come from two
# different instants.
FORWARD_POLICY_SNAPSHOT: Final[str] = "forward-policy.json"


@dataclass(frozen=True, kw_only=True)
class FirewallTable:
    """One family's one table: its chains, their policies, its rules.

    `rules` are canonical `-A <chain> <specification>` lines, which is
    the form a `-D` needs: the specification requires each deletion to
    carry the rule's FULL specification and never a position, because a
    reconciler inserting a rule between the read and the delete would
    otherwise make the guard remove k3s's rule instead of Docker's.
    """

    chains: tuple[str, ...]
    policies: Mapping[str, str]
    rules: tuple[str, ...]


def save_argv(*, family: str, table: str) -> tuple[str, ...]:
    """The read of one family's one table. No `-c`: counters are not state."""
    return (SAVE_COMMAND[family], "-t", table)


def snapshot_name(*, family: str, table: str) -> str:
    """The snapshot file holding that read's output, named after the command."""
    return f"{SAVE_COMMAND[family]}.{table}"


def parse_table(*, dump: str) -> FirewallTable:
    """Parse one `*-save` dump into canonical chains, policies and rules."""
    chains: list[str] = []
    policies: dict[str, str] = {}
    rules: list[str] = []
    for raw in dump.splitlines():
        line = " ".join(raw.split())
        if line.startswith(":"):
            name, _, rest = line[1:].partition(" ")
            policy, _, _ = rest.partition(" ")
            chains.append(name)
            policies[name] = policy
        elif line.startswith("-A "):
            rules.append(line)
    return FirewallTable(chains=tuple(chains), policies=policies, rules=tuple(rules))
