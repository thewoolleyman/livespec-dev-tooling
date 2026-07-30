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


@dataclass(frozen=True, kw_only=True)
class TreeState:
    """A member's recursive master tree: paths, gitlink entries, read status."""

    readable: bool
    truncated: bool = False
    paths: frozenset[str] = frozenset()
    gitlink_paths: tuple[str, ...] = ()


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
    for entry in cast("list[object]", entries):
        if not isinstance(entry, dict):
            continue
        record = cast("dict[str, object]", entry)
        path = record.get("path")
        if not isinstance(path, str):
            continue
        paths.add(path)
        if record.get("mode") == _GITLINK_MODE:
            gitlinks.append(path)
    return TreeState(
        readable=True,
        truncated=bool(mapping.get("truncated")),
        paths=frozenset(paths),
        gitlink_paths=tuple(sorted(gitlinks)),
    )
