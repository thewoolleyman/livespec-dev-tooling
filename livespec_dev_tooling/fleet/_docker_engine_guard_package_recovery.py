"""Finishing the interrupted install a guard run left on a host.

Governing specification: `SPECIFICATION/non-functional-requirements.md`
section "Docker engine install guard", "Package fence", as amended in
revise v076. Governing design: `docs/docker-engine-guard-design.md`,
Mechanism 5 as amended by F6 (the recovery branch) and G7 (the install
completes the trigger handlers its own packages activate).

This module is design F6's recovery BRANCH, and it is separate from the
step (`_docker_engine_guard_packages.py`) because it is a different job:
the step issues ONE audited transaction, while this finishes transactions
somebody else's process already started and was killed inside. Which
dpkg verb a leftover gets is decided here, by the STATE dpkg holds it in,
and the re-unpack half of it — matching a `half-installed` leftover to
its own audited archive — is `_docker_engine_guard_package_reunpack.py`
beside this.

Whether a flagged package is the guard's own leftover AT ALL is decided
before this runs, by `_docker_engine_guard_package_leftovers.py`; every
name reaching here has already been accounted for against the recorded
intended sets.

Expected refusals are RETURNED as the reason an operator reads, never
raised: the modules are copied onto the guarded host and run against its
bare interpreter, where the `returns` railway is not importable.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Final

from livespec_dev_tooling.fleet._docker_engine_guard_package_audit import (
    UNHELD,
    InstalledPackage,
    read_installed,
)
from livespec_dev_tooling.fleet._docker_engine_guard_package_reunpack import (
    reunpack_half_installed,
)
from livespec_dev_tooling.fleet._docker_engine_guard_package_runner import (
    FENCED_ENV,
    INSTALL_TIMEOUT_SECONDS,
    TimedCommand,
    TimedRunner,
)

__all__: list[str] = [
    "recover_interrupted",
]

# The two states a package can be in that `dpkg --configure` completes,
# and the only ones design F6 allows it to be aimed at. Narrow on
# purpose: `--configure -a` would adopt whatever else the host has left
# pending, which is the one thing the recovery branch must not do.
#
# `half-installed` is deliberately NOT here, and its absence is the fix
# FAULTS B-06 and M-04 paid for: dpkg cannot configure that state at all
# — it answers `cannot configure (current status 'half-installed')` and
# exits 1 — so a package in it is re-unpacked from its own audited
# archive first and reaches this set, as `unpacked`, only afterwards.
_RECOVERABLE_STATES: Final[frozenset[str]] = frozenset(
    {
        "half-configured",
        "unpacked",
    }
)

# The two states a helper killed during trigger processing leaves behind.
# Neither is broken enough for `--configure` nor finished enough to be
# installed over, so design G7 completes them with `--triggers-only`.
_TRIGGER_STATES: Final[frozenset[str]] = frozenset(
    {
        "triggers-awaited",
        "triggers-pending",
    }
)


def _in_states(
    *,
    flagged: tuple[str, ...],
    installed: Mapping[str, InstalledPackage],
    states: frozenset[str],
) -> tuple[str, ...]:
    """The flagged packages dpkg holds in one of `states`, sorted."""
    return tuple(sorted(name for name in flagged if installed.get(name, UNHELD).status in states))


def recover_interrupted(
    *,
    runner: TimedRunner,
    flagged: tuple[str, ...],
    installed: Mapping[str, InstalledPackage],
    debs: tuple[Path, ...],
) -> str | None:
    """Finish what an interrupted install left, and only for those packages.

    Design F6's recovery branch. It runs BEFORE this run's own
    transaction because dpkg refuses to unpack over a database that
    still holds an unfinished one, and it is aimed at named packages
    rather than issued as `--configure -a`, which would adopt whatever
    else the host has left pending.

    Every name here has already been accounted for against the recorded
    intended sets, so the narrowness that remains is by STATE: a package
    an interrupted UNPACK left `half-installed` is re-unpacked from its
    own audited archive, because that is the one state
    `dpkg --configure` can do nothing with; the states an interrupted
    CONFIGURE leaves go to `--configure`; and the two a helper killed
    during trigger processing leaves go to `--triggers-only`. A package
    is in exactly one of those positions, and completing an unpacked
    package's triggers would skip the configuration it is actually
    waiting for.

    Those last two sets are read from the states AFTER the re-unpack,
    which is why the table is re-read when one happened: the package the
    unpack moved out of `half-installed` is exactly the one
    `dpkg --configure` now has to name, and the snapshot the step took
    before the recovery still reports it in the state dpkg refuses. The
    re-read is skipped when nothing was unpacked, because then that
    snapshot still describes the host and a second query would only cost
    a command.

    The one refusal this branch can answer with is the re-unpack's: a
    `half-installed` leftover that no audited `.deb` of this run carries
    at that exact identity is work neither the recovery nor the install
    can do anything with, so it stops the step here rather than being
    handed to a `dpkg --configure` that cannot complete it.
    """
    reunpack = reunpack_half_installed(
        runner=runner, flagged=flagged, installed=installed, debs=debs
    )
    if reunpack.refusal is not None:
        return reunpack.refusal
    current = read_installed(runner=runner) if reunpack.unpacked else installed
    recoverable = _in_states(flagged=flagged, installed=current, states=_RECOVERABLE_STATES)
    if recoverable:
        _ = runner(
            command=TimedCommand(
                argv=("dpkg", "--configure", *recoverable),
                timeout_seconds=INSTALL_TIMEOUT_SECONDS,
                env=FENCED_ENV,
            )
        )
    awaiting = _in_states(flagged=flagged, installed=current, states=_TRIGGER_STATES)
    if awaiting:
        _ = runner(
            command=TimedCommand(
                argv=("dpkg", "--triggers-only", *awaiting),
                timeout_seconds=INSTALL_TIMEOUT_SECONDS,
                env=FENCED_ENV,
            )
        )
    return None
