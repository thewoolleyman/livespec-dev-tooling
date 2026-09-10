"""Consumer fixture trees for the `SPECIFICATION/scenarios.md` role-key scenarios.

Shared by `test_role_key_declared_absence.py` and
`test_unarmed_until_closed_work_item.py`, which assert different scenarios over
the SAME thing a consumer writes: a complete `[tool.livespec_dev_tooling]`
block with exactly one role key under test. Two copies of the block would drift,
and a drifted copy is silent — a fixture missing a required key makes every
role-gated check hard-error on THAT key instead of exercising the declaration
the test is about.

Not a `conftest.py` on purpose: these are plain constructors, not pytest
fixtures, so a reader of either test can see what the tree contains without
resolving fixture injection.
"""

from __future__ import annotations

import json
from pathlib import Path

__all__: list[str] = [
    "LEGACY_EMPTY_SPELLINGS",
    "ROLE_KEY_SPELLING_FIELD",
    "records_from",
    "union_key_block",
    "write_consumer",
]

# The structured field every declared-absent announcement carries, naming the
# variant the consumer declared. Its PRESENCE is what distinguishes an
# announced sanctioned opt-out from a rejection.
ROLE_KEY_SPELLING_FIELD = "role_key_spelling"

# The retired ambiguous spelling for each union role key, one per key SHAPE:
# `[]` for the collection-valued keys, `""` for the scalar-valued ones. A key
# declared with the other shape's empty is a TYPE error rather than the legacy
# emptiness, and would be rejected with a different diagnostic.
LEGACY_EMPTY_SPELLINGS: dict[str, str] = {
    "dataclasses_tree": '""',
    "neutral_hook_body_path": '""',
    "pure_trees": "[]",
    "source_tree_prefixes": "[]",
    "target_dirs": "[]",
}

# Every required role key, declared legally. The key under test is REPLACED
# rather than appended, so no fixture ever declares one key twice.
_BASE_DECLARATIONS: dict[str, str] = {
    "source_trees": '["src"]',
    "io_trees": "[]",
    "commands_trees": "[]",
    "covered_trees": "[]",
    "supervisor_entry_files": "[]",
    "pure_trees": '{ not_applicable = "fixture" }',
    "target_dirs": '{ not_applicable = "fixture" }',
    "source_tree_prefixes": '{ not_applicable = "fixture" }',
    "dataclasses_tree": '{ not_applicable = "fixture" }',
    "neutral_hook_body_path": '{ not_applicable = "fixture" }',
}


def union_key_block(*, key: str, value: str, comment: str) -> str:
    """The complete block with `key` declared as `value`, under a decoy `comment`.

    The comment is written where a consumer would really put a reason — on the
    line above the key — and every caller supplies one that CONTRADICTS the
    payload, so a reader falling back to it produces a wrong answer rather than
    a coincidentally right one.
    """
    declarations = dict(_BASE_DECLARATIONS)
    declarations[key] = value
    lines = [
        f"{comment}\n{name} = {declared}" if name == key else f"{name} = {declared}"
        for name, declared in declarations.items()
    ]
    body = "\n".join(lines)
    return f"[tool.livespec_dev_tooling]\n{body}\n"


def write_consumer(*, root: Path, block: str) -> Path:
    """A consumer tree at `root` carrying `block` in its `pyproject.toml`."""
    root.mkdir(parents=True, exist_ok=True)
    _ = root.joinpath("pyproject.toml").write_text(
        f'[project]\nname = "consumer"\nversion = "0.0.0"\n\n{block}', encoding="utf-8"
    )
    return root


def records_from(*, captured: str) -> list[dict[str, object]]:
    """Every structlog JSON record in `captured`, in emission order.

    Deliberately unguarded, matching the unit-tier sibling: these checks emit
    ONE JSON object per line and nothing else, so a non-JSON line is a real
    regression in output discipline (`check-no-write-direct` bans stray writes)
    and should fail the test loudly rather than be skipped.
    """
    return [json.loads(line) for line in captured.splitlines()]
