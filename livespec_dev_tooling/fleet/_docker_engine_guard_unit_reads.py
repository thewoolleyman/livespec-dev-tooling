"""What the service manager says about the guard's units, and which one is running this.

Governing specification: `SPECIFICATION/non-functional-requirements.md`
section "Docker engine install guard", "Host actions". Governing design:
`docs/docker-engine-guard-design.md` I1 (admission), I3 (fixed unit
identities) and F4, whose post-commit validation reads enablement and
active state together.

EVERYTHING HERE IS A READ, which is why it does not live beside the
stops, the kills and the disables in `_docker_engine_guard_units.py`.
That module's single load-bearing property is that every ACTION is
intersected with a fixed set so a defect can never reach the k3s agent;
a read has nothing to narrow and would dilute the rule it sat next to.

WHY THE ACTIVE-STATE SET IS A UNION. Admission (I1) asks about the
guard's OWN units — the starter, the observer, the dead-man's timer and
service, and any other `docker-engine-guard-*` invocation — while the
post-commit validation (F4) asks about the three GUARDED units, whose
active state is the only evidence left that a committed host's engine is
actually running. One read answers both, so the set is the fixed names
plus whatever the manager currently holds under the guard's two
prefixes; a caller that cares about only one half filters it.

Stdlib only, Python 3.10 syntax.
"""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Final

from livespec_dev_tooling.fleet._docker_engine_guard_model import GUARDED_UNITS
from livespec_dev_tooling.fleet._docker_engine_guard_rollback import deadman_timer_unit
from livespec_dev_tooling.fleet._docker_engine_guard_units import (
    ACTIVE_STATE,
    GUARD_OWN_UNITS,
    SYSTEMCTL,
    UNIT_READ_TIMEOUT_SECONDS,
    unit_active_states,
    unit_property,
)
from livespec_dev_tooling.fleet._docker_engine_guard_witness import PROC_ROOT

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from livespec_dev_tooling.fleet._docker_engine_guard_runner import GuardCommandRunner

__all__: list[str] = [
    "ACTIVE",
    "CGROUP_UNIT_SUFFIXES",
    "LIST_UNITS_ARGV",
    "LOADED",
    "LOAD_STATE",
    "SELF_CGROUP_PATH",
    "UNIT_FILE_STATE",
    "UNIT_SUFFIXES",
    "deadman_timer_active",
    "deadman_timer_exists",
    "guard_unit_states",
    "invoking_unit",
    "loaded_guard_units",
    "unit_enabled_states",
]

# Every unit the guard ever runs as. Both prefixes are passed to the
# manager as patterns rather than filtered here, so a run id this process
# has never heard of is still listed: admission has to see the dead-man
# of a PREVIOUS run, which is exactly the one a new reservation must not
# step over.
LIST_UNITS_ARGV: Final[tuple[str, ...]] = (
    SYSTEMCTL,
    "list-units",
    "--all",
    "--plain",
    "--no-legend",
    "--no-pager",
    "docker-engine-guard-*",
    "docker-engine-deadman-*",
)

# What a listed unit's name ends with. The listing's footer
# (`4 loaded units listed.`) has a first column too, so requiring a unit
# suffix is what keeps a count out of the admission set.
UNIT_SUFFIXES: Final[tuple[str, ...]] = (".service", ".timer")

# This process's own control group, relative to `/proc`.
SELF_CGROUP_PATH: Final[str] = "self/cgroup"

# What a cgroup path component ends with when it names the unit a process
# belongs to. `.scope` is admitted here and not above because an operator
# invoking the guard by hand from a session lands in one, and naming that
# scope is the truthful answer: it is not a guard unit, so it excludes
# nothing from admission.
CGROUP_UNIT_SUFFIXES: Final[tuple[str, ...]] = (".service", ".scope")

UNIT_FILE_STATE: Final[str] = "UnitFileState"

# Whether the manager holds the unit at all, and the value it reports for
# one it does. A transient unit armed with `--collect` is GONE once it
# has been collected, and the manager answers `not-found` for it.
LOAD_STATE: Final[str] = "LoadState"
LOADED: Final[str] = "loaded"

ACTIVE: Final[str] = "active"


def loaded_guard_units(*, runner: GuardCommandRunner) -> tuple[str, ...]:
    """Every unit the manager currently holds under the guard's two prefixes."""
    answer = runner(argv=LIST_UNITS_ARGV, timeout_seconds=UNIT_READ_TIMEOUT_SECONDS)
    named = (line.split() for line in answer.stdout.splitlines())
    return tuple(fields[0] for fields in named if fields and fields[0].endswith(UNIT_SUFFIXES))


def guard_unit_states(*, runner: GuardCommandRunner) -> Mapping[str, str]:
    """Every guard-relevant unit mapped to its `ActiveState`.

    The FIXED names are read whether the manager listed them or not. A
    unit the manager does not know answers `inactive`, which is the
    truth about it, while leaving it out of the map would make a caller
    asking "is docker.service running" read a missing key — and the
    post-commit validation treats a missing key as drift.
    """
    units = sorted({*GUARDED_UNITS, *GUARD_OWN_UNITS, *loaded_guard_units(runner=runner)})
    return unit_active_states(runner=runner, units=units)


def unit_enabled_states(*, runner: GuardCommandRunner) -> Mapping[str, str]:
    """The three guarded units mapped to their `UnitFileState`.

    Exactly the units the guard ENABLES and DISABLES, and no others: the
    guard's own units are transient, so they have no unit file and no
    enablement to report. Read beside the active states rather than
    instead of them, because enablement carries the engine across the
    next boot while the active state says it is running now, and neither
    implies the other.
    """
    return {
        unit: unit_property(runner=runner, unit=unit, name=UNIT_FILE_STATE)
        for unit in GUARDED_UNITS
    }


def invoking_unit(*, proc_root: Path = PROC_ROOT) -> str:
    """The unit this invocation itself belongs to, read from its own cgroup.

    The kernel's answer rather than the service manager's: the process
    asking is the subject of the question, so its control group names
    the unit directly with no round trip and nothing to match it against.

    An unidentifiable placement answers the empty string, and that is
    FAIL-CLOSED on purpose. The one caller excludes this name from the
    admission set, so a wrong answer would exclude a unit that is
    genuinely busy; an empty one excludes nothing and leaves a busy unit
    reported.
    """
    placement = proc_root / SELF_CGROUP_PATH
    recorded = placement.read_text(encoding="utf-8").strip() if placement.is_file() else ""
    named = [
        part
        for part in PurePosixPath(recorded.rpartition(":")[2]).parts
        if part.endswith(CGROUP_UNIT_SUFFIXES)
    ]
    return named[-1] if named else ""


def deadman_timer_exists(*, runner: GuardCommandRunner, run: str) -> bool:
    """Whether this run's dead-man timer unit is loaded at all.

    What a retried `arm` asks, so that it re-records nothing and arms
    nothing a second time: `systemd-run --unit=` would refuse a second
    timer of the same name, and the refusal would fail an operation
    that has in fact already done its job.

    LOADED rather than active, because the two answer different
    questions. A timer that has FIRED and whose rollback is running is
    not active, and arming a second one over it would put two dead-men
    on one run.
    """
    return unit_property(runner=runner, unit=deadman_timer_unit(run=run), name=LOAD_STATE) == LOADED


def deadman_timer_active(*, runner: GuardCommandRunner, run: str) -> bool:
    """Whether this run's dead-man timer is actually in the air.

    `start` refuses without it, and that refusal is the whole reason
    this read is separate from the one above. The dead-man is the only
    thing that takes the host back if the controller dies, so granting
    the start permission beside a timer that is merely LOADED -- failed,
    collected, or stopped -- would leave a Docker daemon nothing is
    watching on a machine reachable only over Tailscale.
    """
    return (
        unit_property(runner=runner, unit=deadman_timer_unit(run=run), name=ACTIVE_STATE) == ACTIVE
    )
