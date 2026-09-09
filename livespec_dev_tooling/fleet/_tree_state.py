"""A member's recursive tree listing, and the payload parser that builds it.

Split out of `_context.py` when that module reached its 250-LLOC hard ceiling
for the second time — the first split produced `_read_failure.py`. The
contents are the same kind of cohesive half that one was: what a tree read
WAS and how its payload is parsed, with no knowledge of `FleetContext`
itself, so the module is imported BY the context and imports nothing from it.

The split is not cosmetic. `livespec-dev-tooling-oitd` records what a full
module costs here: `_contract_rows.py` sat at 246 of 250 and had SILENTLY
closed the fleet's one obligation table to new rows. A context module with
no headroom closes the fleet's one GitHub seam to new reads the same way.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

__all__: list[str] = [
    "TreeState",
    "parse_tree_payload",
]


_GITLINK_MODE = "160000"
# The blob mode git gives a symlink. It is captured because the tree is the
# ONLY GitHub surface that distinguishes a symlink from a real file at the
# same path: the contents API RESOLVES an in-repo symlink to its target's
# bytes, so a `.claude/CLAUDE.md` symlinked to `../AGENTS.md` and a divergent
# real file there read identically through it. What the tree does NOT carry is
# the link TEXT — that lives in the blob — so a consumer reading these paths
# learns that an entry is a symlink, never where it points.
_SYMLINK_MODE = "120000"


@dataclass(frozen=True, kw_only=True)
class TreeState:
    """A member's recursive master tree: paths, gitlink/symlink entries, read status."""

    readable: bool
    truncated: bool = False
    paths: frozenset[str] = frozenset()
    gitlink_paths: tuple[str, ...] = ()
    symlink_paths: tuple[str, ...] = ()


def parse_tree_payload(*, payload: object) -> TreeState:
    """Map a `git/trees` JSON payload onto a `TreeState` value."""
    if not isinstance(payload, dict):
        return TreeState(readable=False)
    mapping = cast("dict[str, object]", payload)
    entries = mapping.get("tree")
    if not isinstance(entries, list):
        return TreeState(readable=False)
    paths: set[str] = set()
    gitlinks: list[str] = []
    symlinks: list[str] = []
    for entry in cast("list[object]", entries):
        if not isinstance(entry, dict):
            continue
        record = cast("dict[str, object]", entry)
        path = record.get("path")
        if not isinstance(path, str):
            continue
        paths.add(path)
        mode = record.get("mode")
        if mode == _GITLINK_MODE:
            gitlinks.append(path)
        elif mode == _SYMLINK_MODE:
            symlinks.append(path)
    return TreeState(
        readable=True,
        truncated=bool(mapping.get("truncated")),
        paths=frozenset(paths),
        gitlink_paths=tuple(sorted(gitlinks)),
        symlink_paths=tuple(sorted(symlinks)),
    )
