"""The host-wide orchestrator adoption lock.

A tag adopt, a full-commit adopt step run on its own and `just
ensure-plugins-fleet` each write the host's `installed_plugins.json`, so each
holds one exclusive lock for its whole run and two of them never write at once.
The lock lives at one fixed host path, the same for every checkout and every
release of this library, with `~` resolved from the invoking user's home before
any `HOME` override; it does not follow `XDG_STATE_HOME`. The adopt step that
`just ensure-plugins-fleet` runs for a member runs under the fleet recipe's own
hold, so only each entrypoint takes it. The kernel releases an `flock` when the
holding process ends, however it ends.
"""

from __future__ import annotations

import fcntl
from collections.abc import Callable
from pathlib import Path

__all__: list[str] = ["ADOPTION_LOCK_RELATIVE", "adoption_lock_path", "holding_adoption_lock"]

ADOPTION_LOCK_RELATIVE = Path(".local/state/livespec-dev-tooling/orchestrator-adoption.lock")


def adoption_lock_path(*, home: Path) -> Path:
    """The fixed adoption lock path below the invoking user's home."""
    return home / ADOPTION_LOCK_RELATIVE


def holding_adoption_lock(
    *, path: Path, body: Callable[[], int], on_wait: Callable[[], None]
) -> int:
    """Run `body` holding the exclusive adoption lock, waiting for any other holder first."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            on_wait()
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        return body()
