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
from pathlib import Path

__all__: list[str] = [
    "LIMIT_FILE",
    "SLOT_DIR",
    "configured_limit",
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
