"""One ownership check for every expedited-incident path that trusts a file or directory."""

from __future__ import annotations

import os
import stat
from pathlib import Path

__all__: list[str] = ["protected_path"]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-xhb7pj


def protected_path(*, path: Path) -> bool:
    """Validate ownership of lexical links, resolved targets and every ancestor.

    The path must be absolute and exist. The path, every ancestor directory, the
    resolved target and every ancestor of the target must each be owned by root or
    this account (as a link and as its target) and not writable by group or other.
    The one exception is a root-owned sticky directory. Any filesystem error or
    symlink cycle refuses the path rather than raising.
    """
    try:
        if not path.is_absolute() or not path.exists():
            return False
        resolved = path.resolve(strict=True)
        for entry in (path, *path.parents, resolved, *resolved.parents):
            link, info = entry.lstat(), entry.stat()
            sticky = entry.is_dir() and info.st_uid == 0 and bool(info.st_mode & stat.S_ISVTX)
            if (
                link.st_uid not in {0, os.geteuid()}
                or info.st_uid not in {0, os.geteuid()}
                or (info.st_mode & 0o022 and not sticky)
            ):
                return False
    except (OSError, RuntimeError):
        return False
    else:
        return True
