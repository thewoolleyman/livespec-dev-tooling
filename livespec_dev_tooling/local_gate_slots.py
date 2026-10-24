"""The host-wide local-gate slot limit — N test runs at once, the rest queue.

Governed by `livespec-dev-tooling`'s own
`SPECIFICATION/non-functional-requirements.md` section "Local gate concurrency
limit" (v091) and the four scenarios beneath it in `SPECIFICATION/scenarios.md`.

WHAT THIS BOUNDS AND WHY IT IS BOUNDED AT ALL. Nothing limited how many full
local gates ran at once on one host. Measured on the dev VPS (vmi3006760, 18
cores) 2026-10-24 01:34Z: 95.8% busy by `mpstat`, PSI cpu some avg60 69%, load
78, with four to five concurrent `pytest -n 4 --cov` aggregates each using about
four cores — pre-push gates, commit-msg replay runs and pre-commit aggregates
across fleet worktrees, all contending for the same machine. Every gate slowed,
and gates were pushed toward the harness's tool-call ceiling, which converts a
would-be verdict into a kill that carries none.

IT IS A STOPGAP AND SAYS SO. Plan `delegated-gate-fleet-rollout` (epic
livespec-dev-tooling-mvalxq) moves the heavy gates onto the cluster; once
livespec, livespec-overseer and livespec-console-beads-fabro delegate theirs,
the ratified clause says the limit SHOULD be removed. Removing it is removing
one committed setting — see the `local_gate_slots` ansible role.

WHY THE LIMIT IS READ FROM A HOST FILE RATHER THAN FROM A REPOSITORY. A
repository's configuration travels with the CODE and says nothing about the
machine, so a repository that opted in would throttle in every clone of itself —
a factory sandbox and a delegated gate pod included, where there is nothing to
contend for and a queue is pure loss. Concurrency is a property of the HOST, so
it is read from the host.

EVERY UNREADABLE STATE FAILS OPEN. An absent limit file, a value that will not
parse, and an explicit zero all mean "no limit", and a host with no limit starts
pytest sessions exactly as it would without this module. That is the ratified
behavior for the fleet's sandboxes and gate pods, and it is also the only safe
posture for a throttle: a gate is the thing that says whether a tree is sound,
and a concurrency stopgap that cannot read its own setting must never be able to
refuse one.
"""

from __future__ import annotations

import fcntl
import os
import sys
import time
from collections.abc import Callable
from pathlib import Path

# `structlog` is VENDORED, not installed; a bare import here would resolve only
# when some earlier import in the process happened to run first.
_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import.

__all__: list[str] = [
    "HEARTBEAT_SECONDS",
    "LIMIT_FILE",
    "POLL_SECONDS",
    "SLOT_DIR",
    "await_slot",
    "configured_limit",
    "take_session_slot",
    "take_slot",
]

# THE ONE HOST FILE, and the only thing an operator sets. It carries the limit N
# as a decimal integer and nothing else; the `local_gate_slots` ansible role
# writes it, and removing that one committed setting removes this file and
# returns the host to no limit.
LIMIT_FILE = Path("/etc/livespec/local-gate-slots")

# Where the slots themselves live. Under `/run` rather than `/tmp` for two
# reasons that point the same way: `/run` is a tmpfs cleared at boot, which is
# exactly the lifetime a lock file wants (no lock survives a reboot, so a file
# that did would only ever be stale), and the same converge that writes the
# limit provisions this directory through `systemd-tmpfiles`, so the store and
# the setting that needs it arrive together.
SLOT_DIR = Path("/run/livespec/local-gate-slots")

# Slot files are opened O_RDONLY, which is NOT an oversight: `flock` may be
# taken on a descriptor opened in any mode, so a read-only open makes a slot
# usable by every login on the host whatever umask created the file. An O_RDWR
# open would refuse a 0644 file another user created first, and a session that
# reads "cannot open" as "taken" would queue behind a slot nobody holds.
_SLOT_OPEN_FLAGS = os.O_CREAT | os.O_RDONLY
_SLOT_CREATE_MODE = 0o666

# How often a queued session looks again for a free slot.
#
# WHY A POLL RATHER THAN A BLOCKING `flock`. A blocking lock waits on ONE named
# file, and this host has N of them: a session blocking on slot 1 would sleep
# through slot 2 falling free, so the queue would hand slots out in the order
# holders happened to finish rather than to whoever was waiting. Polling every
# slot each round costs N `flock` attempts a second — syscalls, measured in
# microseconds — which is why the poll interval can be short enough that a
# freed slot is picked up promptly without the wait costing anything.
POLL_SECONDS = 1.0

# How often a queued session says so. The ratified clause asks for at least
# once a minute; half a minute is chosen so a line is still owed well before
# that bound even if a round is scheduled late on a loaded host.
HEARTBEAT_SECONDS = 30.0

# The heartbeat expressed in poll rounds, which is what the wait counts. Rounds
# rather than a clock reading because the two intervals are then impossible to
# drift apart: a session announces on the round it is due, and every round is
# one `POLL_SECONDS` sleep by construction.
_HEARTBEAT_ROUNDS = max(1, round(HEARTBEAT_SECONDS / POLL_SECONDS))


def configured_limit(*, limit_file: Path) -> int | None:
    """This host's local-gate slot limit, or `None` when it sets none.

    `None` is the UNLIMITED answer and every absence collapses into it, for the
    fail-open reason the module docstring gives. A zero is read as no limit
    rather than as a host that admits no test run at all: the latter would be a
    setting whose only effect is to wedge every gate on the machine, and the
    role spells "no limit" as zero so that removing the committed value returns
    the host to no limit through the role's own default.
    """
    if not limit_file.is_file():
        return None
    try:
        text = limit_file.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not text.isdigit():
        return None
    limit = int(text)
    return limit if limit > 0 else None


def take_slot(*, slot_dir: Path, limit: int) -> int | None:
    """Take one of this host's `limit` slots, or `None` when every one is held.

    The return is a RAW FILE DESCRIPTOR, and the caller must hold it for the
    session's whole life without closing it. That is the mechanism rather than
    an implementation detail: the kernel releases a `flock` when the last
    descriptor of its open file description closes, so holding the descriptor IS
    holding the slot, and process death — by any cause, SIGKILL included — frees
    it with no cleanup step, no stale-lock sweep and nothing to reap. An `int`
    has no finalizer, so nothing can close it behind the session's back, which a
    file OBJECT could not promise: the garbage collector would close one the
    moment the caller stopped referring to it, silently freeing a slot the
    session still believed it held.
    """
    for path in _slot_paths(slot_dir=slot_dir, limit=limit):
        fd = _locked_fd(path=path)
        if fd is not None:
            return fd
    return None


def await_slot(
    *,
    slot_dir: Path,
    limit: int,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    """Queue until one of this host's `limit` slots is free, then hold it.

    Returns the held descriptor, under the no-closing contract `take_slot`
    records. The wait produces NO VERDICT of its own and cannot: it either
    returns a slot or keeps waiting, so a session that queued runs its own tests
    and reports their own result. That is why the queue is here rather than in
    the gate aggregate — a throttle that could fail a gate would turn a busy
    host into a red tree.

    A session killed while queued holds nothing, because it has taken nothing:
    the only state a waiting session has is its own place in no queue at all.
    There is no ticket to reclaim and no registry to prune, which is what makes
    being killed here free of consequence.
    """
    rounds = 0
    while True:
        fd = take_slot(slot_dir=slot_dir, limit=limit)
        if fd is not None:
            return fd
        if rounds % _HEARTBEAT_ROUNDS == 0:
            _announce_wait(limit=limit, slot_dir=slot_dir)
        rounds += 1
        sleep(POLL_SECONDS)


def take_session_slot(
    *,
    limit_file: Path,
    slot_dir: Path,
    sleep: Callable[[float], None] = time.sleep,
) -> int | None:
    """The slot this pytest session holds, or `None` when it needs none.

    THE WHOLE SESSION-LEVEL DECISION, in one place, so that every surface that
    runs pytest under a fleet gate is governed identically: the pre-commit
    aggregate, the commit-msg replay gate, a local pre-push `just check` and a
    hand-run `just check` all reach this through the same plugin hook.

    `None` means "run now, holding nothing", and it is returned for every reason
    a session should not be throttled: the host sets no limit, or its slot store
    cannot be reached. Neither is an error and neither is reported as one — see
    the module docstring on why a throttle must fail open.

    The return is the held descriptor under `take_slot`'s no-closing contract.
    The caller discards it ON PURPOSE: a session holds its slot for exactly as
    long as it exists, and the kernel is what hands it back.
    """
    limit = configured_limit(limit_file=limit_file)
    if limit is None:
        return None
    store = _usable_slot_dir(slot_dir=slot_dir)
    if store is None:
        return None
    return await_slot(slot_dir=store, limit=limit, sleep=sleep)


def _usable_slot_dir(*, slot_dir: Path) -> Path | None:
    """The slot store, created if it is absent, or `None` when there can be none.

    Created here as well as by the host's converge, so that a host carrying a
    limit still queues correctly before its first `systemd-tmpfiles` run. A
    store that cannot be created is ANNOUNCED rather than swallowed: the session
    then runs unthrottled, and an operator reading a host that is contending
    again needs to be able to tell that from a host nobody provisioned.
    """
    try:
        slot_dir.mkdir(parents=True, exist_ok=True)
    except OSError as unusable:
        _logger().warning(
            "local gate slot store unusable; running this session unthrottled",
            slots=str(slot_dir),
            detail=str(unusable),
        )
        return None
    return slot_dir


def _logger() -> structlog.stdlib.BoundLogger:
    """A logger writing JSON to the stream `sys.stderr` names RIGHT NOW.

    Configured per call rather than once at import, and that is deliberate.
    `structlog`'s print factory snapshots the stream at configure time, and a
    pytest session replaces `sys.stderr` as it starts and again around every
    test — so a configuration taken at import would write to a stream that had
    since been replaced, i.e. to nowhere an operator is looking.
    """
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    return structlog.get_logger("local_gate_slots")


def _announce_wait(*, limit: int, slot_dir: Path) -> None:
    """Say that this session is queued, and name the limit it is queued behind.

    The limit is carried as a FIELD rather than only in the message, because a
    reader's first question on seeing the line is how many slots the host has:
    a bare "waiting" line is indistinguishable from a wedged gate, which is the
    state this announcement exists to rule out.
    """
    _logger().info(
        "waiting for one of this host's local gate slots",
        limit=limit,
        slots=str(slot_dir),
        poll_seconds=POLL_SECONDS,
    )


def _slot_paths(*, slot_dir: Path, limit: int) -> list[Path]:
    """The `limit` slot files, in the order every session tries them.

    ONE FILE PER SLOT rather than `limit` byte ranges of a single file, because
    a POSIX record lock (`fcntl.lockf`) is owned by the PROCESS and is dropped
    when ANY descriptor to that file is closed anywhere in it. A nested session
    that opened the shared file would then release its own parent's hold — and
    `flock`, owned by the open file description, is what makes both the nesting
    case and the two-sessions-one-process case behave as the host does.

    A limit lowered from a previous converge leaves the higher-numbered files
    behind, and that is harmless: a slot exists because a session locked its
    file, so a file no reader enumerates holds nothing.
    """
    return [slot_dir / f"slot-{index}" for index in range(1, limit + 1)]


def _locked_fd(*, path: Path) -> int | None:
    """One slot file's descriptor with its lock held, or `None` when it is not free.

    A file that cannot be opened at all reports the same `None` as one already
    locked. The alternative — handing back a descriptor no lock was taken on —
    would let two sessions each believe they held that slot, which is the one
    failure this module exists to prevent, so an unopenable slot is treated as
    unavailable rather than as free.
    """
    try:
        fd = os.open(path, _SLOT_OPEN_FLAGS, _SLOT_CREATE_MODE)
    except OSError:
        return None
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        return None
    return fd
