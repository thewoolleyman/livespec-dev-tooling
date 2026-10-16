"""Durable records, the lock, and the deadline of the Docker engine install guard.

Governing specification: `SPECIFICATION/non-functional-requirements.md`
section "Docker engine install guard" (this repository) — "One run at a
time, under one lock", "Phases" and "Deadline".

Everything here is stdlib: this module is copied onto the guarded host and
runs against its bare interpreter. Expected refusals are RETURNED (a
`None`, a `MarkerState`) and never raised, which is the Result discipline
this repository requires, carried in a shape that needs no dependency.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final

from livespec_dev_tooling.fleet._docker_engine_guard_model import PHASES, Deadline, GuardPaths

if TYPE_CHECKING:
    from livespec_dev_tooling.fleet._docker_engine_guard_hostops import HostOps
    from livespec_dev_tooling.fleet._docker_engine_guard_model import MarkerState, Phase

__all__: list[str] = [
    "GuardEnv",
    "deadline_passed",
    "read_deadline",
    "read_marker",
    "read_phase",
    "read_reservation",
    "record_phase",
    "write_deadline",
    "write_durable",
    "write_reservation",
]

_TMP_SUFFIX = ".tmp"

# Every phase name keyed by itself, so a recorded string narrows to a
# `Phase` through an ordinary lookup rather than a cast, and an
# unrecognised record answers `None` instead of pretending to be a phase.
_PHASE_BY_NAME: Final[dict[str, Phase]] = {phase: phase for phase in PHASES}


@dataclass(frozen=True, kw_only=True)
class GuardEnv:
    """Everything an operation needs that is not its own run id.

    The paths and the host are the only two things the guard touches the
    world through, and both are injected, which is what lets the whole
    lifecycle be decided in-process against `FakeHost`.
    """

    paths: GuardPaths
    host: HostOps


def write_durable(*, path: Path, data: str) -> None:
    """Write `data` to `path` so a reader sees the whole old or the whole new record.

    Write a temporary beside the target, fsync it, rename it over the
    target, then fsync the directory — the sequence the specification
    requires of every phase record. The rename is what makes the swap
    atomic; the two fsyncs are what make it survive a power loss.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + _TMP_SUFFIX)
    fd = os.open(tmp, os.O_CREAT | os.O_WRONLY | os.O_TRUNC | os.O_CLOEXEC, 0o600)
    try:
        _ = os.write(fd, data.encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)
    _ = tmp.replace(path)
    dir_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


def _read_stripped(*, path: Path) -> str | None:
    """The file's stripped text, or `None` when it is not there at all."""
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8").strip()


def record_phase(*, paths: GuardPaths, run: str, phase: Phase) -> None:
    """Move `run` to `phase`, durably. Only ever called under the lock."""
    write_durable(path=paths.phase_path(run=run), data=phase)


def read_phase(*, paths: GuardPaths, run: str) -> Phase | None:
    """The run's recorded phase, or `None` when the run has no usable record.

    A record naming something outside the phase vocabulary reads as `None`
    rather than as itself, which is fail-closed: every dispatch row lists
    the phases it is allowed from, so an unrecognised record is allowed
    from nowhere.
    """
    recorded = _read_stripped(path=paths.phase_path(run=run))
    return None if recorded is None else _PHASE_BY_NAME.get(recorded)


def write_reservation(*, paths: GuardPaths, run: str) -> None:
    """Name `run` as the host's current reservation, durably."""
    write_durable(path=paths.reservation, data=run)


def read_reservation(*, paths: GuardPaths) -> str | None:
    """The run the host currently holds a reservation for, or `None`."""
    return _read_stripped(path=paths.reservation)


def read_marker(*, paths: GuardPaths, run: str) -> MarkerState:
    """How the commit marker reads for `run`: absent, self, other or unreadable.

    Unreadable joins "other" at every call site rather than "absent",
    because a marker that cannot be parsed is not evidence that no run
    committed — and treating it as absent would roll back a committed host.
    """
    if not paths.marker.is_file():
        return "absent"
    try:
        payload = json.loads(paths.marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "unreadable"
    if not isinstance(payload, dict):
        return "unreadable"
    fields: dict[str, object] = payload
    named = fields.get("run")
    if not isinstance(named, str):
        return "unreadable"
    return "self" if named == run else "other"


def write_deadline(*, paths: GuardPaths, run: str, deadline: Deadline) -> None:
    """Record the run's deadline. `arm` writes it once and never extends it."""
    payload = {"boot_id": deadline.boot_id, "monotonic": deadline.monotonic}
    write_durable(path=paths.deadline_path(run=run), data=json.dumps(payload))


def read_deadline(*, paths: GuardPaths, run: str) -> Deadline | None:
    """The run's recorded deadline, or `None` when it was never armed."""
    recorded = _read_stripped(path=paths.deadline_path(run=run))
    if recorded is None:
        return None
    payload = json.loads(recorded)
    return Deadline(boot_id=str(payload["boot_id"]), monotonic=float(payload["monotonic"]))


def deadline_passed(*, deadline: Deadline | None, host: HostOps) -> bool:
    """True when the run is out of time, and fail-closed on both unknowns.

    An absent deadline counts as passed: an operation that checks the
    deadline is one that may only run on an armed run, so no record means
    the run is not in a state to proceed. A deadline recorded under a
    different boot id counts as passed because its monotonic instant does
    not refer to this boot's clock at all.
    """
    if deadline is None:
        return True
    if deadline.boot_id != host.boot_id():
        return True
    return host.monotonic() >= deadline.monotonic
