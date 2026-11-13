"""Read the members of a `check-targets.txt` inventory and their annotations.

The membership rule is the aggregate's own: `scripts/just/check.sh` strips
everything from the first `#`, trims the line, and keeps what starts with
`check-`, and `checks.aggregate_completeness` applies the same rule in Python.
So a reader built on `inventory_members` sees exactly the members `just check`
runs, in the same order, duplicates included.

`inventory_lines` is the wider reading the expedited incident hook uses
(livespec-dev-tooling-dixgta): every member line, whatever its prefix, because a
consuming repository's `check:` recipe can list a member that is not a `check-`
slug, and the hook must run or defer every member rather than skip one silently.

An annotation is a `# key: value` comment on a member's line, such as
`# purity: tree-pure` or `# incident-timing: fast`. The aggregate's reader drops
every comment, so annotations never change what it runs. One line may carry
several annotations, and the same key may appear more than once; deciding what a
repeated or missing key means is the caller's business, not this reader's.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__: list[str] = [
    "InventoryMember",
    "annotation_values",
    "inventory_lines",
    "inventory_members",
]

_SLUG_PREFIX = "check-"
_ANNOTATION = re.compile(r"#\s*(?P<key>[a-z][a-z0-9-]*):\s*(?P<value>\S+)")


@dataclass(frozen=True, kw_only=True)
class InventoryMember:
    """One member line: the target the aggregate runs, and its annotations in order."""

    name: str
    annotations: tuple[tuple[str, str], ...]


def inventory_lines(*, text: str) -> tuple[InventoryMember, ...]:
    """Every non-blank, non-comment line of `text`, in order, whatever its prefix."""
    members: list[InventoryMember] = []
    for line in text.splitlines():
        name = line.split("#", 1)[0].strip()
        if not name:
            continue
        annotations = tuple(
            (found.group("key"), found.group("value")) for found in _ANNOTATION.finditer(line)
        )
        members.append(InventoryMember(name=name, annotations=annotations))
    return tuple(members)


def inventory_members(*, text: str) -> tuple[InventoryMember, ...]:
    """Every member line of `text`, in order, with its `# key: value` annotations."""
    return tuple(
        member for member in inventory_lines(text=text) if member.name.startswith(_SLUG_PREFIX)
    )


def annotation_values(*, member: InventoryMember, key: str) -> tuple[str, ...]:
    """Every value `member` declares for `key`, in line order."""
    return tuple(value for found, value in member.annotations if found == key)
