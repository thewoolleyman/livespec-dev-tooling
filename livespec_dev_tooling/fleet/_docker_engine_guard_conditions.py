"""The proof that the installed units cannot start: their EFFECTIVE conditions.

Governing specification: `SPECIFICATION/non-functional-requirements.md`
section "Docker engine install guard", "Start condition". Governing
design: `docs/docker-engine-guard-design.md` F5 and G6, and rider points
6 and 7.

This check is the gate the whole fail-closed design rests on, and it is
read over D-BUS rather than from text for a measured reason (rider point
6): `systemctl show -p Conditions` renders unprintable on gmktec's
systemd 259, so a text scrape would compare against garbage and PASS. The
manager's own parsed `Conditions` property carries the type, the trigger
flag and the path, which is exactly the three things "exactly two OR'd
`ConditionPathExists`" needs to assert.

The drop-in SURVEY below guards the same proof from the other side. The
conditions only hold while nothing else edits these units, and a drop-in
loaded after the guard's can add a start path the guard never granted --
so G6 refuses any drop-in but its own, and rider point 7 carves out the
one the fleet installs itself (`sandbox_storage`'s `RequiresMountsFor`,
present on hp, absent on gmktec, therefore tolerated and never required).

EXACTLY TWO is the requirement in both directions. A third condition
could admit a start the guard never permitted; a missing one leaves the
OR with only one way to be satisfied. And an answer that cannot be read
fails CLOSED, because "no conditions reported" and "no conditions
configured" are indistinguishable from here -- and the second one is a
Docker daemon free to start on its own.

Stdlib only, Python 3.10 syntax.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Final

from livespec_dev_tooling.fleet._docker_engine_guard_model import GUARDED_UNITS

if TYPE_CHECKING:
    from livespec_dev_tooling.fleet._docker_engine_guard_model import GuardPaths
    from livespec_dev_tooling.fleet._docker_engine_guard_runner import GuardCommandRunner

__all__: list[str] = [
    "CONDITIONS_PROPERTY",
    "CONDITION_PATH_EXISTS",
    "CONDITION_TIMEOUT_SECONDS",
    "DEFAULT_UNIT_DIRECTORY",
    "GUARD_DROPIN",
    "SANDBOX_STORAGE_DROPIN",
    "SANDBOX_STORAGE_UNITS",
    "UnitCondition",
    "condition_check_passed",
    "conditions_argv",
    "expected_conditions",
    "read_conditions",
    "sanctioned_dropins",
    "unexpected_dropins",
    "unit_object_path",
]

_BUSCTL: Final[str] = "busctl"
_SYSTEMD_BUS: Final[str] = "org.freedesktop.systemd1"
_UNIT_INTERFACE: Final[str] = "org.freedesktop.systemd1.Unit"
_UNIT_PATH_PREFIX: Final[str] = "/org/freedesktop/systemd1/unit/"

CONDITIONS_PROPERTY: Final[str] = "Conditions"
CONDITION_PATH_EXISTS: Final[str] = "ConditionPathExists"
CONDITION_TIMEOUT_SECONDS: Final[int] = 15

# Where systemd reads the drop-ins an administrator installs, and the
# only tree this survey walks: a packaged `/usr/lib` drop-in ships with
# the audited `.deb` files and is covered by the package audit instead.
DEFAULT_UNIT_DIRECTORY: Final[Path] = Path("/etc/systemd/system")

# The guard's own drop-in, carrying the two OR'd conditions, at mode 0644
# (design R5 step 2).
GUARD_DROPIN: Final[str] = "50-docker-engine-guard.conf"

# The ONE override the fleet installs itself (rider point 7): the
# `sandbox_storage` role's `RequiresMountsFor`, which refuses to start a
# daemon whose store is not mounted. Present on hp, absent on gmktec --
# so it is TOLERATED, never required.
SANDBOX_STORAGE_DROPIN: Final[str] = "10-requires-sandbox-storage.conf"

# Exactly the units that role writes it for. `docker.socket` is NOT among
# them: it mounts no store, so a sandbox drop-in there was installed by
# something else and is a finding like any other.
SANDBOX_STORAGE_UNITS: Final[tuple[str, ...]] = (
    "containerd.service",
    "docker.service",
)

# One row of the `a(sbbsi)` property, reduced to the four fields the check
# compares: the condition type, its TRIGGER flag (the `|` that makes it
# an OR rather than an AND), its NEGATE flag, and its path.
UnitCondition = tuple[str, bool, bool, str]


def unit_object_path(*, unit: str) -> str:
    """The D-Bus object path of `unit`, escaped the way systemd escapes it.

    Every character that is not alphanumeric becomes `_` plus its two hex
    digits, so `docker.service` is `docker_2eservice`. The guard's own
    unit names carry hyphens, which escape the same way.
    """
    escaped = "".join(
        character if character.isalnum() else f"_{ord(character):02x}" for character in unit
    )
    return f"{_UNIT_PATH_PREFIX}{escaped}"


def conditions_argv(*, unit: str) -> tuple[str, ...]:
    """The `busctl` read of one unit's effective `Conditions` property.

    `--json=short` because the human rendering of an `a(sbbsi)` is what
    rider point 6 found unparseable; the JSON form carries each field
    separately and typed.
    """
    return (
        _BUSCTL,
        "--json=short",
        "get-property",
        _SYSTEMD_BUS,
        unit_object_path(unit=unit),
        _UNIT_INTERFACE,
        CONDITIONS_PROPERTY,
    )


def read_conditions(*, runner: GuardCommandRunner, unit: str) -> tuple[UnitCondition, ...]:
    """One unit's effective conditions, or NOTHING when the read came back empty.

    An empty answer returns an empty tuple rather than raising, and the
    caller treats that as a failure: this is the fail-closed edge, so it
    must reach the verdict rather than the exception handler.
    """
    answer = runner(argv=conditions_argv(unit=unit), timeout_seconds=CONDITION_TIMEOUT_SECONDS)
    text = answer.stdout.strip()
    if not text:
        return ()
    rows = json.loads(text)["data"]
    return tuple((str(row[0]), bool(row[1]), bool(row[2]), str(row[3])) for row in rows)


def expected_conditions(*, paths: GuardPaths) -> tuple[UnitCondition, ...]:
    """The two OR'd path conditions every guarded unit must carry, and only those."""
    return (
        (CONDITION_PATH_EXISTS, True, False, str(paths.permission)),
        (CONDITION_PATH_EXISTS, True, False, str(paths.marker)),
    )


def condition_check_passed(*, runner: GuardCommandRunner, paths: GuardPaths) -> bool:
    """Whether all three guarded units carry exactly the guard's two conditions.

    Compared as SETS: the manager reports the conditions in the order it
    parsed the drop-in, which is not a property the guard should depend
    on, while "exactly these two" is.
    """
    wanted = set(expected_conditions(paths=paths))
    return all(set(read_conditions(runner=runner, unit=unit)) == wanted for unit in GUARDED_UNITS)


def sanctioned_dropins(*, unit: str) -> frozenset[str]:
    """Every drop-in filename `unit` is allowed to carry, and no other.

    The guard's own for all three units; the `sandbox_storage` override
    for the two that actually hold a store.
    """
    allowed = {GUARD_DROPIN}
    if unit in SANDBOX_STORAGE_UNITS:
        allowed.add(SANDBOX_STORAGE_DROPIN)
    return frozenset(allowed)


def unexpected_dropins(*, unit_directory: Path = DEFAULT_UNIT_DIRECTORY) -> tuple[str, ...]:
    """Every drop-in on the three guarded units outside the sanctioned set.

    An empty tuple is the PASS. This returns the OFFENDERS rather than a
    bool because a refusal has to name what it refused on -- "a drop-in is
    unexpected" is not something an operator can act on.

    Reported as `<unit>.d/<file>` and SORTED, so the refusal reads the
    same whatever order the filesystem hands the entries back. Only
    `*.conf` is surveyed, because that is the only suffix systemd loads
    from a `.d` directory, and a MISSING directory is nothing to survey
    rather than a finding: a host the role has not written to yet has
    none, and the condition check above is what catches a guard drop-in
    that is absent.
    """
    found: list[str] = []
    for unit in GUARDED_UNITS:
        allowed = sanctioned_dropins(unit=unit)
        directory = unit_directory / f"{unit}.d"
        if not directory.is_dir():
            continue
        found.extend(
            f"{unit}.d/{entry.name}"
            for entry in directory.glob("*.conf")
            if entry.name not in allowed
        )
    return tuple(sorted(found))
