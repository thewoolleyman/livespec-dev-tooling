"""What the service manager says about the guard's OWN units.

Governing specification: `SPECIFICATION/non-functional-requirements.md`
section "Docker engine install guard", "Host actions" (this
repository). Governing design: `docs/docker-engine-guard-design.md` I1
(admission of a new reservation), I3 (fixed unit identities) and rider
point 9 (the post-commit validation reads enablement AND running
state).

Every read here is a READ: nothing in this module starts, stops,
enables or disables anything, which is why it is a separate concern
from the unit CONTROL beside it in
`_docker_engine_guard_units.py`. What they share is the trap that
makes both fussy — a `systemctl` read that silently answers for the
wrong unit, or for no unit, is indistinguishable from a quiet host.

THE GUARD UNIT SET IS ENUMERATED, NOT LISTED, and that is the one
load-bearing decision in this module. Design I1 counts the dead-man
timer and its service among the units that must be quiescent before a
new reservation, and those names carry the run id of whatever run
currently holds the host — which the invocation asking the question
does not know. A hand-written list is therefore blind to exactly the
unit that says an earlier run is still being torn down, so the
question is put to the service manager as a set of GLOBS and the set
comes back from it.

Stdlib only, Python 3.10 syntax, for the reason
`_docker_engine_guard_model.py` records.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Final

from livespec_dev_tooling.fleet._docker_engine_guard_model import GUARDED_UNITS
from livespec_dev_tooling.fleet._docker_engine_guard_rollback import deadman_timer_unit
from livespec_dev_tooling.fleet._docker_engine_guard_units import (
    ACTIVE_STATE,
    SYSTEMCTL,
    UNIT_READ_TIMEOUT_SECONDS,
    unit_active_states,
    unit_property,
)
from livespec_dev_tooling.fleet._docker_engine_guard_witness import PROC_ROOT

if TYPE_CHECKING:
    from collections.abc import Mapping

    from livespec_dev_tooling.fleet._docker_engine_guard_runner import GuardCommandRunner

__all__: list[str] = [
    "ACTIVE",
    "GUARD_UNIT_PATTERNS",
    "LOADED",
    "LOAD_STATE",
    "SELF_CGROUP_RELATIVE_PATH",
    "UNIT_FILE_STATE",
    "deadman_timer_active",
    "deadman_timer_exists",
    "guard_unit_states",
    "guarded_unit_active_states",
    "invoking_unit",
    "unit_enabled_states",
]

# The guard units design I1 requires to be quiescent, as the globs the
# service manager expands them from. The dead-man's two units are
# matched by pattern for the reason the module docstring records: their
# names carry a run id the asking invocation does not have.
GUARD_UNIT_PATTERNS: Final[tuple[str, ...]] = (
    "docker-engine-guard-*.service",
    "docker-engine-deadman-*.service",
    "docker-engine-deadman-*.timer",
)

_ID: Final[str] = "Id"
LOAD_STATE: Final[str] = "LoadState"
UNIT_FILE_STATE: Final[str] = "UnitFileState"

LOADED: Final[str] = "loaded"
ACTIVE: Final[str] = "active"

# Where a process reads its own cgroup, relative to `/proc`. Relative so
# the read is drivable against a RECORDED tree through the host's own
# `proc_root`, exactly as the boot-id read is.
SELF_CGROUP_RELATIVE_PATH: Final[Path] = Path("self/cgroup")

# The hierarchy id the unified (cgroup v2) line carries. gmktec runs
# cgroup v2 with the systemd cgroup driver, so this is the line that
# names the unit; a file without one names no unit at all rather than
# having one guessed from a legacy controller's path.
_UNIFIED_HIERARCHY: Final[str] = "0"


def _states_by_unit(*, text: str, name: str) -> dict[str, str]:
    """One `systemctl show` answer over several units, keyed by unit.

    The records come back separated by a blank line and each opens with
    the `Id=` the read asks for FIRST, because `systemctl show` emits
    properties in the order they were requested. That ordering is what
    lets a single pass key each state by the unit above it; a read that
    did not ask for `Id` could not tell whose state it was holding, and
    a unit the manager does not know is simply ABSENT from the output
    rather than reported as stopped.
    """
    states: dict[str, str] = {}
    unit = ""
    for line in text.splitlines():
        key, _, value = line.partition("=")
        if key == _ID:
            unit = value
        elif key == name:
            states[unit] = value
    return states


def guard_unit_states(*, runner: GuardCommandRunner) -> Mapping[str, str]:
    """Every guard unit the service manager has loaded, mapped to its `ActiveState`.

    `failed` comes back as itself rather than folded into `inactive`:
    the two mean opposite things to admission, because a failed
    dead-man service is a rollback that was attempted and did not
    finish, and that is precisely the host a new reservation must not
    be admitted onto.
    """
    answer = runner(
        argv=(
            SYSTEMCTL,
            "show",
            "--property",
            _ID,
            "--property",
            ACTIVE_STATE,
            *GUARD_UNIT_PATTERNS,
        ),
        timeout_seconds=UNIT_READ_TIMEOUT_SECONDS,
    )
    return _states_by_unit(text=answer.stdout, name=ACTIVE_STATE)


def guarded_unit_active_states(*, runner: GuardCommandRunner) -> Mapping[str, str]:
    """Each GUARDED unit's `ActiveState`, read one unit at a time.

    NOT `guard_unit_states` above, and the two being different reads is
    the whole reason this one exists. That read enumerates the GUARD's
    own transient units by glob; the three units the guard CONDITIONS
    match none of those globs, so a post-commit validation that reached
    for it read an EMPTY map and reported all three guarded units
    adrift on every real committed run. H-01 measured exactly that on
    2026-10-17: `confirm` refused a committed host whose service
    manager reported all three `enabled` and `active`.

    Per unit, like `unit_enabled_states` below, and over the same fixed
    set: the validation needs both halves of "enabled AND running" for
    the same three units, and reading them the same way is what keeps a
    unit the manager does not know ABSENT from both answers rather than
    reported as something it is not.
    """
    return unit_active_states(runner=runner, units=GUARDED_UNITS)


def unit_enabled_states(*, runner: GuardCommandRunner) -> Mapping[str, str]:
    """Each guarded unit's `UnitFileState`, read one unit at a time.

    Per unit for the reason `unit_active_states` is: a single
    `systemctl show` over several units interleaves their properties
    and omits one it does not know, so a mis-parse would report an
    unenabled unit as enabled. The set is FIXED here, unlike the
    admission read above, because enablement is a question about the
    three units the guard conditions and about nothing else — the
    guard's own units are transient and were never enabled at all.
    """
    return {
        unit: unit_property(runner=runner, unit=unit, name=UNIT_FILE_STATE)
        for unit in GUARDED_UNITS
    }


def invoking_unit(*, proc_root: Path = PROC_ROOT) -> str:
    """The unit this invocation is running inside, or no unit at all.

    Read from the cgroup rather than from an environment variable: the
    guard is started by `systemd-run`, and the cgroup is the one record
    of the resulting unit that survives into a child the guard spawns.
    An empty answer is deliberate and safe — every caller uses this to
    EXCLUDE a unit from an admission check, so naming nothing excludes
    nothing and the check stays the stricter of the two.
    """
    for line in (proc_root / SELF_CGROUP_RELATIVE_PATH).read_text(encoding="utf-8").splitlines():
        hierarchy, _, rest = line.partition(":")
        if hierarchy == _UNIFIED_HIERARCHY:
            return rest.partition(":")[2].rsplit("/", maxsplit=1)[-1]
    return ""


def deadman_timer_exists(*, runner: GuardCommandRunner, run: str) -> bool:
    """Whether this run's dead-man timer is LOADED, so a retried `arm` creates no second one."""
    loaded = unit_property(runner=runner, unit=deadman_timer_unit(run=run), name=LOAD_STATE)
    return loaded == LOADED


def deadman_timer_active(*, runner: GuardCommandRunner, run: str) -> bool:
    """Whether this run's dead-man timer is active, which `start` refuses without."""
    state = unit_property(runner=runner, unit=deadman_timer_unit(run=run), name=ACTIVE_STATE)
    return state == ACTIVE
