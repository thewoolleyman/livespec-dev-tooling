"""What the Docker engine install guard's preflight REFUSES on, before any run.

Governing specification: `SPECIFICATION/non-functional-requirements.md`
section "Docker engine install guard", "Preflight" (this repository).
Governing design: `docs/docker-engine-guard-design.md` F7 ("admission and
collision checks").

Every answer here is a refusal REASON rather than a bool, and an empty
tuple is the pass. The reasons are what an operator reads on a machine
reachable only over Tailscale: "the preflight refused" says nothing a
person can act on, while "172.17.0.0/16 overlaps the route
172.17.0.0/16 in a routing table" names the thing to change.

WHY THE OVERLAP CHECK IS FOUR READS AND NOT ONE. Docker's default bridge
takes `172.17.0.0/16` and masquerades it outward, so a range already
carrying traffic is not merely double-booked: the install silently
shadows it. The four places such a range can already live are an address
on an interface, a route in ANY routing table (tailscaled's policy
tables 52xx and table 52 are exactly such a place on this host), the
tailnet range, and the cluster's pod and service CIDRs. The first two are
READ from the host; the last two are DECLARED, because they are facts
about the tailnet and the cluster rather than about this machine.

Stdlib only, Python 3.10 syntax, for the reason the model module records.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from ipaddress import IPv4Network, ip_network
from typing import TYPE_CHECKING, Final

from livespec_dev_tooling.fleet._docker_engine_guard_firewall import DOCKER_SUBNET, FAMILIES

if TYPE_CHECKING:
    from livespec_dev_tooling.fleet._docker_engine_guard_runner import GuardCommandRunner

__all__: list[str] = [
    "ADDRESS_SHOW_ARGV",
    "DOCKER_GROUP",
    "GETENT_GROUP_ARGV",
    "GETENT_PASSWD_ARGV",
    "PREFLIGHT_TIMEOUT_SECONDS",
    "ROUTE_SHOW_ARGV",
    "ROUTE_TYPES",
    "docker_group_accounts",
    "overlapping_addresses",
    "overlapping_declared_ranges",
    "overlapping_routes",
    "subnet_overlaps",
]

_IP_COMMAND: Final[str] = "ip"

# `-o` puts each address on ONE line, so the interface name and the
# prefix it carries are fields of the same row; the default multi-line
# form puts them on separate lines and a row-wise scan would attribute a
# prefix to the wrong interface.
ADDRESS_SHOW_ARGV: Final[tuple[str, ...]] = (_IP_COMMAND, "-o", "addr", "show")

# `table all` is load-bearing: the specification says "a route in ANY
# routing table", and tailscaled's own routes live in policy table 52 on
# this host, which the default `ip route show` never reports. Both
# families are read because `ip route show` alone reports only IPv4.
ROUTE_SHOW_ARGV: Final[Mapping[str, tuple[str, ...]]] = {
    "ipv4": (_IP_COMMAND, "route", "show", "table", "all"),
    "ipv6": (_IP_COMMAND, "-6", "route", "show", "table", "all"),
}

# A kernel read with no lock to wait on. The bound exists to cap a wedged
# netlink socket, not a slow answer.
PREFLIGHT_TIMEOUT_SECONDS: Final[int] = 15

# The route TYPES `ip route show table all` prints BEFORE the
# destination. Every host's `local` table carries `local` and
# `broadcast` rows, so a parse that read field zero blindly would try
# the word `local` as an address and quietly find no overlap at all.
ROUTE_TYPES: Final[frozenset[str]] = frozenset(
    {
        "anycast",
        "blackhole",
        "broadcast",
        "local",
        "multicast",
        "nat",
        "prohibit",
        "throw",
        "unicast",
        "unreachable",
    }
)

_DOCKER_NETWORK: Final[IPv4Network] = IPv4Network(DOCKER_SUBNET)

# The token an `ip -o addr show` row puts BEFORE an IPv4 prefix. An
# `inet6` row carries a different one and so is skipped by this parse
# rather than by a rule of its own.
_INET: Final[str] = "inet"

# The group `docker.socket` is owned by (design R9). It does not exist
# before the install creates it, which is why the group read below
# tolerates an empty answer instead of requiring a row.
DOCKER_GROUP: Final[str] = "docker"

_GETENT: Final[str] = "getent"

# Both tables are read through `getent` rather than from `/etc/group` and
# `/etc/passwd` directly, so an account that reaches this host through
# LDAP, SSSD or any other NSS source is seen too: a file-only read would
# pass a host whose directory-supplied CI account is in the group.
GETENT_GROUP_ARGV: Final[tuple[str, ...]] = (_GETENT, "group", DOCKER_GROUP)
GETENT_PASSWD_ARGV: Final[tuple[str, ...]] = (_GETENT, "passwd")

# The colon-separated positions each table carries: `getent group` is
# `name:password:gid:members` and `getent passwd` is
# `name:password:uid:gid:…`.
_GROUP_GID: Final[int] = 2
_GROUP_MEMBERS: Final[int] = 3
_PASSWD_NAME: Final[int] = 0
_PASSWD_GID: Final[int] = 3

# Padding appended before a row's fields are indexed, so a short or
# empty row answers empty strings instead of needing a length guard --
# and a guard no recorded output can reach is a line no test can cover.
_FIELD_PADDING: Final[tuple[str, ...]] = ("", "", "", "", "")


def _ipv4_network(*, text: str) -> IPv4Network | None:
    """`text` as an IPv4 network, or NOTHING when it is not one.

    `strict=False` so a bare host address (`192.168.1.42`, as a `local`
    route carries) reads as its own /32 rather than raising. An IPv6
    answer returns `None` rather than being compared: `IPv6Network`
    refuses to be compared with an IPv4 one, and Docker's default subnet
    is IPv4.
    """
    try:
        candidate = ip_network(text, strict=False)
    except ValueError:
        return None
    return candidate if isinstance(candidate, IPv4Network) else None


def _overlaps(*, text: str) -> bool:
    """Whether `text` names a range sharing an address with Docker's subnet."""
    network = _ipv4_network(text=text)
    return network is not None and network.overlaps(_DOCKER_NETWORK)


def _row_prefixes(*, fields: Sequence[str]) -> tuple[str, ...]:
    """Every IPv4 prefix one `ip -o addr show` row carries.

    A prefix is the token FOLLOWING `inet`, found by a one-element SLICE
    of the preceding position rather than by an index comparison: a slice
    of position zero is empty and so matches nothing, which is what makes
    a row too short to carry a prefix answer nothing without a length
    guard of its own -- and a guard no recorded output can reach is a
    line no test can cover.
    """
    return tuple(
        value for index, value in enumerate(fields) if list(fields[index - 1 : index]) == [_INET]
    )


def overlapping_addresses(*, runner: GuardCommandRunner) -> tuple[str, ...]:
    """Every interface address that shares an address with Docker's subnet."""
    answer = runner(argv=ADDRESS_SHOW_ARGV, timeout_seconds=PREFLIGHT_TIMEOUT_SECONDS)
    found: list[str] = []
    for raw in answer.stdout.splitlines():
        fields = raw.split()
        found.extend(
            f"{DOCKER_SUBNET} overlaps the address {value} on {fields[1].rstrip(':')}"
            for value in _row_prefixes(fields=fields)
            if _overlaps(text=value)
        )
    return tuple(found)


def _route_destinations(*, fields: Sequence[str]) -> Sequence[str]:
    """The one destination of a route row, or nothing when it has none.

    `ip route show table all` prints a route TYPE before the destination
    on the `local` and `broadcast` rows every host's `local` table
    carries, so the destination is the SECOND field there and the first
    everywhere else. Both answers are one-element SLICES, so a row with
    no fields at all yields nothing and needs no guard of its own.
    """
    return fields[1:2] if fields[:1] and fields[0] in ROUTE_TYPES else fields[:1]


def overlapping_routes(*, runner: GuardCommandRunner) -> tuple[str, ...]:
    """Every route in any table of either family that overlaps Docker's subnet."""
    found: list[str] = []
    for family in FAMILIES:
        answer = runner(argv=ROUTE_SHOW_ARGV[family], timeout_seconds=PREFLIGHT_TIMEOUT_SECONDS)
        for raw in answer.stdout.splitlines():
            found.extend(
                f"{DOCKER_SUBNET} overlaps the route {destination} in a routing table"
                for destination in _route_destinations(fields=raw.split())
                if _overlaps(text=destination)
            )
    return tuple(found)


def overlapping_declared_ranges(*, declared: Mapping[str, str]) -> tuple[str, ...]:
    """Every declared range -- tailnet, pod CIDR, service CIDR -- that overlaps.

    Sorted by the declaration's LABEL so the refusal reads the same way
    twice whatever order the mapping was built in.
    """
    return tuple(
        f"{DOCKER_SUBNET} overlaps the declared {label} {declared[label]}"
        for label in sorted(declared)
        if _overlaps(text=declared[label])
    )


def _fields(*, row: str, table: tuple[int, ...]) -> tuple[str, ...]:
    """The named positions of one colon-separated row, padded so none is missing."""
    padded = (*row.split(":"), *_FIELD_PADDING)
    return tuple(padded[position] for position in table)


def docker_group_accounts(*, runner: GuardCommandRunner) -> tuple[str, ...]:
    """Every account the `docker` group admits, by either kind of membership.

    TWO reads, because the two kinds of membership live in two different
    tables and neither table holds the other's. A supplementary member
    is named in the group's own member list; an account whose PRIMARY
    group is `docker` is named nowhere in that list and is only visible
    as a passwd row whose gid is the group's. A check that read the
    member list alone would pass a host whose CI builder has `docker`
    as its login group -- and that account can reach the Docker API the
    moment the socket appears.

    Sorted and de-duplicated, so the refusal an operator reads names
    each account once and in the same order twice.
    """
    group = runner(argv=GETENT_GROUP_ARGV, timeout_seconds=PREFLIGHT_TIMEOUT_SECONDS)
    rows = tuple(
        _fields(row=row, table=(_GROUP_GID, _GROUP_MEMBERS)) for row in group.stdout.splitlines()
    )
    gids = {gid for gid, _ in rows}
    admitted = {name for _, members in rows for name in members.split(",") if name}
    passwd = runner(argv=GETENT_PASSWD_ARGV, timeout_seconds=PREFLIGHT_TIMEOUT_SECONDS)
    admitted.update(
        name
        for name, gid in (
            _fields(row=row, table=(_PASSWD_NAME, _PASSWD_GID))
            for row in passwd.stdout.splitlines()
        )
        if gid in gids
    )
    return tuple(sorted(admitted))


def subnet_overlaps(*, runner: GuardCommandRunner, declared: Mapping[str, str]) -> tuple[str, ...]:
    """Every reason Docker's default subnet is already taken on this host."""
    return (
        *overlapping_addresses(runner=runner),
        *overlapping_routes(runner=runner),
        *overlapping_declared_ranges(declared=declared),
    )
