"""The start permission, and the root-only runtime directory that holds it.

Governing specification: `SPECIFICATION/non-functional-requirements.md`
section "Docker engine install guard", "Host actions" (this repository).
Governing design: `docs/docker-engine-guard-design.md` R1 — before the
commit point `/run/docker-engine-guard/allow-start` is the ONLY thing
that lets any of the three guarded units start, because each one's
drop-in carries `ConditionPathExists=|` on it.

That makes this the narrowest, most consequential surface the guard
has: one file's presence is the difference between a host whose Docker
daemon cannot start at all and one whose daemon can. The three acts
here are correspondingly fussy about their edges — the grant is atomic,
the revoke is idempotent, and the directory is made root-owned so no
other account can create the permission the guard alone is meant to.

Stdlib only, Python 3.10 syntax, for the reason
`_docker_engine_guard_model.py` records.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from livespec_dev_tooling.fleet._docker_engine_guard_state import write_durable

if TYPE_CHECKING:
    from pathlib import Path

    from livespec_dev_tooling.fleet._docker_engine_guard_model import GuardPaths
    from livespec_dev_tooling.fleet._docker_engine_guard_runner import GuardCommandRunner

__all__: list[str] = [
    "OWNERSHIP_TIMEOUT_SECONDS",
    "PERMISSION_CONTENT",
    "ROOT_OWNER",
    "grant_start_permission",
    "revoke_start_permission",
    "set_owner_root",
]

# What the permission says to the operator who cats it. The guarded
# units test only its EXISTENCE, so the bytes are free — and a file
# whose whole meaning is "a Docker daemon may start on this host" is
# worth one sentence rather than being left empty.
PERMISSION_CONTENT: Final[str] = (
    "docker-engine-guard: the guarded units may start while this file exists\n"
)

# `chown` rather than `os.chown`: making a path root-owned is the one
# act here the guard cannot perform without leaving its own process, so
# it goes out through the SAME bounded runner every other host command
# does and is asserted on the argv it emits.
ROOT_OWNER: Final[str] = "root:root"

# A `chown` of one directory is a single inode write. The bound is short
# for the reason every bound in this guard is short: a command that
# blocks past its operation's budget takes the transient unit down with
# it and leaves no verdict at all.
OWNERSHIP_TIMEOUT_SECONDS: Final[int] = 15


def set_owner_root(*, runner: GuardCommandRunner, path: Path) -> None:
    """Make `path` root-owned, so only root can create what lives inside it."""
    _ = runner(argv=("chown", ROOT_OWNER, str(path)), timeout_seconds=OWNERSHIP_TIMEOUT_SECONDS)


def grant_start_permission(*, paths: GuardPaths) -> None:
    """Create the start permission, whole or not at all.

    Written through the durable write and so RENAMED into place, which
    is what keeps the permission atomic: a guarded unit evaluating
    `ConditionPathExists` sees either no file or the finished one, never
    a partial write under the final name. Repeating the grant is
    harmless — the rename replaces the file it already wrote — which is
    what lets a `start` that died after granting simply be run again.
    """
    write_durable(path=paths.permission, data=PERMISSION_CONTENT)


def revoke_start_permission(*, paths: GuardPaths) -> None:
    """Remove the start permission, and SUCCEED when it is already gone.

    The idempotence is required rather than convenient. This is the
    first act of every rollback, and the dead-man re-fires its rollback
    every sixty seconds until the run ends, so all but the first firing
    meets a permission that is already absent. Raising there would stop
    the teardown at step one, on every firing after the first.
    """
    paths.permission.unlink(missing_ok=True)
