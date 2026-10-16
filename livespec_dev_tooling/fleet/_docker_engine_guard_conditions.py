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
from typing import TYPE_CHECKING, Final

from livespec_dev_tooling.fleet._docker_engine_guard_model import GUARDED_UNITS

if TYPE_CHECKING:
    from livespec_dev_tooling.fleet._docker_engine_guard_model import GuardPaths
    from livespec_dev_tooling.fleet._docker_engine_guard_runner import GuardCommandRunner

__all__: list[str] = [
    "CONDITIONS_PROPERTY",
    "CONDITION_PATH_EXISTS",
    "CONDITION_TIMEOUT_SECONDS",
    "UnitCondition",
    "condition_check_passed",
    "conditions_argv",
    "expected_conditions",
    "read_conditions",
    "unit_object_path",
]

_BUSCTL: Final[str] = "busctl"
_SYSTEMD_BUS: Final[str] = "org.freedesktop.systemd1"
_UNIT_INTERFACE: Final[str] = "org.freedesktop.systemd1.Unit"
_UNIT_PATH_PREFIX: Final[str] = "/org/freedesktop/systemd1/unit/"

CONDITIONS_PROPERTY: Final[str] = "Conditions"
CONDITION_PATH_EXISTS: Final[str] = "ConditionPathExists"
CONDITION_TIMEOUT_SECONDS: Final[int] = 15

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
