"""Read the tracked tree of the checkout currently under conformance review."""

from __future__ import annotations

import subprocess
from pathlib import Path

from livespec_dev_tooling.fleet._tree_state import TreeState

__all__: list[str] = ["checked_out_tree"]


def checked_out_tree(*, root: Path) -> TreeState:
    """Return the tree at ``HEAD`` in ``root``, or an unreadable state on failure.

    ``git ls-tree`` deliberately reads the checked-out commit rather than
    walking the filesystem: a CI checkout can contain untracked build output,
    but conformance rows grade only the member's committed files. Its mode
    column is also the local equivalent of the GitHub recursive-tree API's
    mode, preserving the gitlink and symlink distinctions rows rely on.
    """
    try:
        completed = subprocess.run(
            ["git", "ls-tree", "-r", "-z", "HEAD"],
            cwd=root,
            capture_output=True,
            check=False,
        )
    except OSError:
        return TreeState(readable=False)
    if completed.returncode != 0:
        return TreeState(readable=False)
    paths: set[str] = set()
    gitlinks: list[str] = []
    symlinks: list[str] = []
    try:
        for entry in completed.stdout.split(b"\0"):
            if entry == b"":
                continue
            metadata, raw_path = entry.split(b"\t", maxsplit=1)
            mode = metadata.split(b" ", maxsplit=1)[0].decode("ascii")
            path = raw_path.decode("utf-8")
            paths.add(path)
            if mode == "160000":
                gitlinks.append(path)
            elif mode == "120000":
                symlinks.append(path)
    except (UnicodeDecodeError, ValueError):
        return TreeState(readable=False)
    return TreeState(
        readable=True,
        paths=frozenset(paths),
        gitlink_paths=tuple(sorted(gitlinks)),
        symlink_paths=tuple(sorted(symlinks)),
    )
