"""The Docker daemon's configuration, and the restart this guard never performs.

Governing specification: `SPECIFICATION/non-functional-requirements.md`
section "Docker engine install guard", "Host actions" (this
repository). Governing design: `docs/docker-engine-guard-design.md` —
`reconfigure` writes the role-OWNED `daemon.json` keys and records that
a drained restart is pending.

BOTH LOCATIONS ARE SHARED WITH AN ANSIBLE ROLE, which is why they are
named here as constants rather than assembled by a caller. The
configuration is `/etc/docker/daemon.json` and the marker is
`ansible/roles/docker_sandbox_slice/defaults/main.yml`'s
`docker_sandbox_slice_pending_restart_marker`. A guard writing either
one somewhere else would leave that role's converge reading a file
nothing updates — and the failure would be SILENT, because an absent
marker reads exactly like a host with no pending restart.

The two acts here have opposite shapes and the asymmetry is the point.
The write is a MERGE, because a key this role does not own belongs to
whoever wrote it. The restart is a RECORD and not an act, because after
the commit point the host is running sandbox containers under the very
daemon a restart would stop.

Stdlib only, Python 3.10 syntax, for the reason
`_docker_engine_guard_model.py` records.
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
    "record_pending_drained_restart",
    "write_daemon_keys",
]

DAEMON_CONFIG: Final[Path] = Path("/etc/docker/daemon.json")

# The `docker_sandbox_slice` role's own default. A DURABLE file rather
# than a play-recap line, because the operator who opens the drained
# window is not necessarily the one who ran the converge, and a recap
# line is gone when the terminal scrolls. Only the drained restart
# clears it.
PENDING_RESTART_MARKER: Final[Path] = Path("/var/lib/docker-sandbox-slice/restart-pending")

# Two-space indent and sorted keys, so a daemon configuration an
# operator opens after a reconfiguration reads like one a human wrote
# and diffs stably against the last write.
_INDENT: Final[int] = 2


def _configured_keys(*, config: Path) -> dict[str, object]:
    """Whatever the daemon configuration already holds, or nothing at all.

    An absent file is an empty mapping rather than a refusal: the guard
    installs the engine on a host that may never have had a
    `daemon.json`, and "no configuration yet" is the ordinary state
    there, not a fault. A file that is present and unparseable IS a
    fault, and raises — merging into a configuration nobody can read
    would silently discard whatever it was trying to say.
    """
    if not config.is_file():
        return {}
    return dict(json.loads(config.read_text(encoding="utf-8")))


def write_daemon_keys(*, keys: Mapping[str, object], config: Path = DAEMON_CONFIG) -> None:
    """Write `keys` into the daemon configuration, leaving every other key alone.

    A MERGE, never a replacement. The digest the commit marker carries
    covers the OWNED keys alone, so a write that dropped a foreign key
    would make its disappearance read as a guarded reconfiguration on
    the next converge — and the key it dropped would belong to whoever
    wrote it, which is not this role.

    Written through the durable write for the reason every record this
    guard keeps is: the daemon reads this file at every start, and a
    half-written one is a daemon that will not start at all.
    """
    merged = {**_configured_keys(config=config), **keys}
    write_durable(path=config, data=json.dumps(merged, indent=_INDENT, sort_keys=True) + "\n")


def record_pending_drained_restart(*, unit: str, marker: Path = PENDING_RESTART_MARKER) -> None:
    """Record that `unit` needs a drained restart, and restart NOTHING.

    The restraint is the whole function. Past the commit point this
    host is running the sandbox containers it exists to run, under the
    daemon a restart would stop, so performing one here would kill the
    work rather than protect it. The fleet's deferred-restart mechanism
    takes it from here, in a window somebody drained on purpose.
    """
    write_durable(path=marker, data=f"{unit}\n")
