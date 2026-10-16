"""The Docker daemon's configuration file, and the restart it is owed.

Governing specification: `SPECIFICATION/non-functional-requirements.md`
section "Sandbox resource envelope" — a role that edits
`/etc/docker/daemon.json` MUST preserve every key it does not own, and a
converge MUST NOT restart `dockerd`: a setting that takes effect only on
a restart is RECORDED as pending and applied by an operator inside a
drained window. Governing design: `docs/docker-engine-guard-design.md`
F4, whose post-commit reconfiguration is exactly those two steps.

THE WRITE AND THE MARKER ARE ONE CONCERN because a write without the
marker is the failure the rule exists to prevent. `cgroup-parent` and
its neighbours are not reloadable, so the file this module writes
describes a daemon that is NOT running yet — and the only record that
says so is the marker beside it. Writing one without the other leaves a
host whose configuration says one thing and whose daemon does another,
with nothing anywhere to say which.

THE MARKER PATH IS THE `docker_sandbox_slice` ROLE'S, deliberately
shared rather than invented here (`ansible/roles/docker_sandbox_slice/
defaults/main.yml`). One host has one deferred-restart record and one
drained-restart procedure that clears it; a second file beside it would
be a second thing an operator has to know to look for, and the one they
did not look at is the one that was owed.

Stdlib only, Python 3.10 syntax.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Final

from livespec_dev_tooling.fleet._docker_engine_guard_state import write_durable

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__: list[str] = [
    "DAEMON_CONFIG",
    "PENDING_RESTART_MARKER",
    "pending_restart_text",
    "record_pending_drained_restart",
    "write_daemon_keys",
]

# The daemon configuration this host reads at every daemon start, and the
# only file this module writes keys into.
DAEMON_CONFIG: Final[Path] = Path("/etc/docker/daemon.json")

# The `docker_sandbox_slice` role's own pending-restart marker, shared
# rather than duplicated: one host, one record of what a restart owes.
PENDING_RESTART_MARKER: Final[Path] = Path("/var/lib/docker-sandbox-slice/restart-pending")

# Two spaces of indent and sorted keys, so the file an operator opens
# after a reconfiguration reads like the file they wrote.
_INDENT: Final[int] = 2


def _held_keys(*, config: Path) -> dict[str, object]:
    """Every key the configuration already holds, or none at all.

    An ABSENT file is no keys, which is the ordinary case on a host
    whose engine has only just been installed. A file holding something
    that is not a JSON OBJECT is also no keys: no daemon ever loaded it,
    because `dockerd` refuses to start on one, so there is nothing in it
    to preserve.
    """
    if not config.is_file():
        return {}
    payload = json.loads(config.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {}
    held: dict[str, object] = payload
    return held


def write_daemon_keys(*, keys: Mapping[str, object], config: Path = DAEMON_CONFIG) -> None:
    """Write `keys` into the daemon configuration, leaving every other key alone.

    The file is read, MERGED and written back rather than rendered from
    the keys given: a key this role does not own belongs to whoever
    wrote it, and dropping it would both break that owner's setting and
    make the next converge read a change nobody made.

    Written durably, unlike the start permission: this one is on /var
    and has to survive the reboot a daemon restart may come with, and a
    configuration half-written by a crash is a daemon that will not
    start at all.
    """
    write_durable(
        path=config,
        data=json.dumps({**_held_keys(config=config), **keys}, indent=_INDENT, sort_keys=True)
        + "\n",
    )


def pending_restart_text(*, unit: str) -> str:
    """What an operator finds in the marker, naming the unit that owes the restart.

    CONSTANT but for the unit name — no timestamp — exactly as the
    role's own marker is, so a second reconfiguration before the window
    opens rewrites identical bytes and changes nothing.
    """
    return (
        f"{unit} is running WITHOUT the configuration the Docker engine guard has just\n"
        "written. The keys it wrote are not reloadable, so they take effect only when\n"
        f"{unit} next starts.\n"
        "\n"
        "Restarting it KILLS every running sandbox container. Drain this host's Fabro\n"
        "servers first, then apply the restart with the docker_sandbox_slice role's\n"
        "drained-restart tag; see that role's HOST_VARS.md. Nothing but that restart\n"
        "clears this file.\n"
    )


def record_pending_drained_restart(*, unit: str, marker: Path = PENDING_RESTART_MARKER) -> None:
    """Record that `unit` is owed a drained restart, and restart NOTHING.

    After the commit point this host is running sandbox containers under
    the very daemon the new keys describe, so restarting it here would
    kill the work the host exists to do — at a moment nobody chose, from
    a converge nobody is watching. The restart is an operator's, inside
    a window in which the Fabro servers carry no active runs; this
    record is how they learn one is owed.
    """
    write_durable(path=marker, data=pending_restart_text(unit=unit))
