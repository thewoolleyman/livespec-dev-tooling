"""Tests for `livespec_dev_tooling/fleet/_tree_state.py`.

`parse_tree_payload` was reachable only through `FleetContext.tree` before the
extraction, so every malformed-payload branch was exercised at one remove,
through a canned `gh` response. Pinning them directly is what the extraction
buys: the parser's contract is "a payload that is not a tree yields
`readable=False`", and that is a statement about the PARSER, not about the
seam that happens to feed it.
"""

from __future__ import annotations

import dataclasses

from livespec_dev_tooling.fleet._tree_state import TreeState, parse_tree_payload

__all__: list[str] = []


def test_a_payload_that_is_not_an_object_is_unreadable() -> None:
    assert parse_tree_payload(payload=["not", "an", "object"]) == TreeState(readable=False)


def test_a_payload_without_a_tree_list_is_unreadable() -> None:
    assert parse_tree_payload(payload={"truncated": False}) == TreeState(readable=False)
    assert parse_tree_payload(payload={"tree": "not-a-list"}) == TreeState(readable=False)


def test_entries_that_are_not_objects_with_string_paths_are_skipped() -> None:
    """A malformed ENTRY is dropped; it does not make the whole tree unreadable.

    The distinction is load-bearing for every consumer: `readable=False` means
    "this member's absence claims prove nothing", while a dropped entry leaves
    the rest of the listing usable.
    """
    state = parse_tree_payload(
        payload={
            "tree": [
                "not-an-object",
                {"mode": "100644"},
                {"path": 17},
                {"path": "justfile", "mode": "100644"},
            ]
        }
    )
    assert state.readable
    assert state.paths == frozenset({"justfile"})


def test_gitlink_entries_are_collected_sorted_and_still_counted_as_paths() -> None:
    state = parse_tree_payload(
        payload={
            "truncated": True,
            "tree": [
                {"path": "vendor/z", "mode": "160000"},
                {"path": "vendor/a", "mode": "160000"},
                {"path": "README.md", "mode": "100644"},
            ],
        }
    )
    assert state.truncated
    assert state.gitlink_paths == ("vendor/a", "vendor/z")
    assert state.paths == frozenset({"vendor/a", "vendor/z", "README.md"})


def test_symlink_entries_are_captured_apart_from_gitlinks_and_still_counted_as_paths() -> None:
    """Mode 120000 lands in `symlink_paths` — not `gitlink_paths`, and still in `paths`.

    The FIELD assertion comes first on purpose. Reading `state.symlink_paths`
    before the field exists raises `AttributeError`, which proves only that a
    name is missing; asserting the field set is a genuine assertion that fails
    at Red and states the additive contract the capture has to keep — a
    symlink is a THIRD kind of entry, distinct from a regular file and from a
    gitlink, and it is not subtracted from either of the two existing views.
    """
    fields = {f.name for f in dataclasses.fields(TreeState)}
    assert {"gitlink_paths", "symlink_paths"} <= fields
    state = parse_tree_payload(
        payload={
            "tree": [
                {"path": "CLAUDE.md", "mode": "120000"},
                {"path": ".claude/CLAUDE.md", "mode": "120000"},
                {"path": "vendor/a", "mode": "160000"},
                {"path": "README.md", "mode": "100644"},
            ]
        }
    )
    assert state.symlink_paths == (".claude/CLAUDE.md", "CLAUDE.md")
    assert state.gitlink_paths == ("vendor/a",)
    assert state.paths == frozenset({".claude/CLAUDE.md", "CLAUDE.md", "vendor/a", "README.md"})
