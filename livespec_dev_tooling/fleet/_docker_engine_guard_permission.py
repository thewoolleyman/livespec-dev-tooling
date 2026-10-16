"""The start permission, and the runtime directory it lives in.

Governing specification: `SPECIFICATION/non-functional-requirements.md`
section "Docker engine install guard", "Start condition". Governing
design: `docs/docker-engine-guard-design.md` Mechanism 1, F3, H2 and I4.

THE PERMISSION IS THE WHOLE FAIL-CLOSED DESIGN IN ONE FILE. Each of the
three guarded units carries two OR'd `ConditionPathExists`, and until
this path exists — or the commit marker does — not one of them can
start, however often the postinst, a socket activation or a reboot
tries. Creating it is therefore the most consequential thing this host
does, and removing it is the first act of every rollback (H2).

The directory belongs with it rather than with the durable records. It
is on tmpfs, so a reboot takes BOTH away and the first helper to run
recreates them (I4) — which is exactly why a reboot before the commit
point leaves a host no guarded unit can start on. For the same reason
nothing here is written durably: an fsync on tmpfs buys nothing, and a
permission that survived a reboot would be the one failure the start
condition exists to prevent.

The mode of the directory is set in-process by its caller and the
OWNERSHIP is set here, through the guard's one bounded runner — so this
action is bounded like every other and is drivable from recorded output,
which is how an action that grants a Docker daemon permission to run is
asserted on at all.

Stdlib only, Python 3.10 syntax.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from pathlib import Path

    from livespec_dev_tooling.fleet._docker_engine_guard_model import GuardPaths
    from livespec_dev_tooling.fleet._docker_engine_guard_runner import GuardCommandRunner

__all__: list[str] = [
    "OWNERSHIP_TIMEOUT_SECONDS",
    "PERMISSION_MODE",
    "ROOT_OWNER",
    "grant_start_permission",
    "revoke_start_permission",
    "set_owner_root",
]

_CHOWN: Final[str] = "chown"

ROOT_OWNER: Final[str] = "root:root"

# Setting ownership of one path touches no daemon and waits on nothing,
# so it gets the same short bound the unit reads do.
OWNERSHIP_TIMEOUT_SECONDS: Final[int] = 15

# Root-only, like the directory holding it. Nothing reads the permission
# but the service manager, which reads it as root; a mode anything else
# could create would make the start condition satisfiable by a party the
# guard never admitted.
PERMISSION_MODE: Final[int] = 0o600


def set_owner_root(*, runner: GuardCommandRunner, path: Path) -> None:
    """Make `path` root-owned, through the one bounded runner."""
    _ = runner(argv=(_CHOWN, ROOT_OWNER, str(path)), timeout_seconds=OWNERSHIP_TIMEOUT_SECONDS)


def grant_start_permission(*, paths: GuardPaths) -> None:
    """Create the start permission the guarded units' condition reads.

    Idempotent, because `start` is: a retried invocation that found the
    permission already there must reach its unit starts rather than
    fail on the file it was about to create.

    The directory is ensured first for the reboot case — /run is tmpfs,
    so a helper reaching this point after a reboot may be the first one
    to run — and nothing is fsynced, because a start permission that
    outlived its boot is precisely what the start condition exists to
    prevent.
    """
    paths.permission.parent.mkdir(parents=True, exist_ok=True)
    paths.permission.touch(mode=PERMISSION_MODE, exist_ok=True)


def revoke_start_permission(*, paths: GuardPaths) -> None:
    """Remove the start permission, and succeed when it is already gone.

    The first act of every rollback, and a rollback is re-run by its
    dead-man every sixty seconds until an outcome is recorded — so an
    absent permission is the NORMAL case here, not an error. Raising on
    it would stop the second firing before the steps that still have
    work to do.
    """
    paths.permission.unlink(missing_ok=True)
