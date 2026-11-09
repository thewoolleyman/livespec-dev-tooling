"""The one reader of `check-targets.txt` members and their annotations."""

from __future__ import annotations

from pathlib import Path

from livespec_dev_tooling.check_inventory import (
    InventoryMember,
    annotation_values,
    inventory_members,
)
from livespec_dev_tooling.checks import aggregate_completeness

__all__: list[str] = []

_ROOT = Path(__file__).resolve().parents[2]


def test_members_are_exactly_the_aggregates_members_in_order() -> None:
    # The aggregate's own Python reader of the same file; check.sh applies the
    # same strip-comment, trim, `check-` prefix rule in shell.
    aggregate = aggregate_completeness._inventory_targets(cwd=_ROOT)  # noqa: SLF001
    members = inventory_members(text=(_ROOT / "check-targets.txt").read_text())
    assert [member.name for member in members] == aggregate


def test_annotations_are_read_in_line_order_and_comments_are_not_members() -> None:
    members = inventory_members(
        text="""# canonical: comment lines are never members
  check-lint # purity: tree-pure # incident-timing: fast
check-twice # incident-timing: fast # incident-timing: slow
check-bare
check-prose # Reads this file: never an annotation
not-a-check # incident-timing: fast
"""
    )
    assert members == (
        InventoryMember(
            name="check-lint",
            annotations=(("purity", "tree-pure"), ("incident-timing", "fast")),
        ),
        InventoryMember(
            name="check-twice",
            annotations=(("incident-timing", "fast"), ("incident-timing", "slow")),
        ),
        InventoryMember(name="check-bare", annotations=()),
        InventoryMember(name="check-prose", annotations=()),
    )
    assert annotation_values(member=members[0], key="purity") == ("tree-pure",)
    assert annotation_values(member=members[1], key="incident-timing") == ("fast", "slow")
    assert annotation_values(member=members[2], key="purity") == ()
