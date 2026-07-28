"""Tests for `livespec_dev_tooling/fleet/_rows_role_key_spellings.py`."""

from __future__ import annotations

import json

from livespec_dev_tooling.config import BLESSED_ROLE_SPELLINGS, UNION_ROLE_KEYS
from livespec_dev_tooling.fleet._context import (
    FleetContext,
    FleetMember,
    GhResult,
    GhRunner,
    RowFinding,
    RowPass,
    RowSkip,
)
from livespec_dev_tooling.fleet._rows_role_key_spellings import (
    assert_role_key_spellings_conformant,
)

__all__: list[str] = []


_MEMBER = FleetMember(repo="widget", repo_class="impl-plugin")
_TREE_ARGS: tuple[str, ...] = ("api", "repos/acme/widget/git/trees/master?recursive=1")
_PYPROJECT_ARGS: tuple[str, ...] = (
    "api",
    "repos/acme/widget/contents/pyproject.toml?ref=master",
    "-H",
    "Accept: application/vnd.github.raw",
)
# The five keys whose value IS a check's scan universe carry a scalar `""`
# spelling rather than a list `[]` spelling for these two.
_SCALAR_UNION_KEYS = frozenset({"dataclasses_tree", "neutral_hook_body_path"})


def make_context(*, table: dict[tuple[str, ...], GhResult]) -> FleetContext:
    """A `FleetContext` for owner `acme` over a canned-response runner."""

    def run(*, args: list[str], stdin: str | None = None) -> GhResult:
        del stdin
        return table.get(tuple(args), GhResult(returncode=1, stdout="", stderr="no canned"))

    runner: GhRunner = run
    return FleetContext(owner="acme", run_gh=runner)


def tree_table(*, paths: list[str], truncated: bool = False) -> dict[tuple[str, ...], GhResult]:
    """A canned table whose tree call yields `paths`."""
    entries = [{"path": path, "mode": "100644"} for path in paths]
    payload = {"tree": entries, "truncated": truncated}
    return {_TREE_ARGS: GhResult(returncode=0, stdout=json.dumps(payload), stderr="")}


def spelling_table(*, pyproject: str) -> dict[tuple[str, ...], GhResult]:
    """A canned table exposing `pyproject.toml` with the given text."""
    table = tree_table(paths=["pyproject.toml"])
    table[_PYPROJECT_ARGS] = GhResult(returncode=0, stdout=pyproject, stderr="")
    return table


def _legacy_block() -> str:
    """Every union key declared with the retired ambiguous empty spelling."""
    lines = ["[tool.livespec_dev_tooling]"]
    for key in sorted(UNION_ROLE_KEYS):
        lines.append(f'{key} = ""' if key in _SCALAR_UNION_KEYS else f"{key} = []")
    return "\n".join(lines) + "\n"


def _migrated_block() -> str:
    """Every union key declared with a blessed declared-absent spelling."""
    lines = ["[tool.livespec_dev_tooling]"]
    for key in sorted(UNION_ROLE_KEYS):
        lines.append(f'{key} = {{ not_applicable = "no such tree here" }}')
    return "\n".join(lines) + "\n"


def test_row_passes_when_every_union_key_uses_a_blessed_spelling() -> None:
    ctx = make_context(table=spelling_table(pyproject=_migrated_block()))

    assert assert_role_key_spellings_conformant(ctx=ctx, member=_MEMBER) == RowPass()


def test_row_passes_when_union_keys_carry_real_values() -> None:
    populated = (
        "[tool.livespec_dev_tooling]\n"
        'pure_trees = ["src/pure"]\n'
        'target_dirs = ["src"]\n'
        'source_tree_prefixes = ["src/"]\n'
        'dataclasses_tree = "src/schemas"\n'
        'neutral_hook_body_path = "hooks/body.py"\n'
    )
    ctx = make_context(table=spelling_table(pyproject=populated))

    assert assert_role_key_spellings_conformant(ctx=ctx, member=_MEMBER) == RowPass()


def test_row_flags_every_legacy_ambiguous_empty_key_by_name() -> None:
    ctx = make_context(table=spelling_table(pyproject=_legacy_block()))

    outcome = assert_role_key_spellings_conformant(ctx=ctx, member=_MEMBER)

    assert isinstance(outcome, RowFinding)
    assert "widget" in outcome.message
    for key in UNION_ROLE_KEYS:
        assert key in outcome.message


def test_row_flags_only_the_unmigrated_keys() -> None:
    mixed = (
        "[tool.livespec_dev_tooling]\n"
        "pure_trees = []\n"
        'target_dirs = { superseded_by = "git-derived universe" }\n'
    )
    ctx = make_context(table=spelling_table(pyproject=mixed))

    outcome = assert_role_key_spellings_conformant(ctx=ctx, member=_MEMBER)

    assert isinstance(outcome, RowFinding)
    assert "pure_trees" in outcome.message
    assert "target_dirs" not in outcome.message


def test_row_flags_a_blessed_name_carrying_an_empty_payload() -> None:
    """An empty payload is a NEW unreadable emptiness wearing a blessed name."""
    ctx = make_context(
        table=spelling_table(
            pyproject='[tool.livespec_dev_tooling]\npure_trees = { not_applicable = "  " }\n'
        )
    )

    outcome = assert_role_key_spellings_conformant(ctx=ctx, member=_MEMBER)

    assert isinstance(outcome, RowFinding)
    assert "pure_trees" in outcome.message


def test_row_flags_an_unrecognized_inline_table_spelling() -> None:
    ctx = make_context(
        table=spelling_table(
            pyproject='[tool.livespec_dev_tooling]\npure_trees = { retired_reason = "x" }\n'
        )
    )

    outcome = assert_role_key_spellings_conformant(ctx=ctx, member=_MEMBER)

    assert isinstance(outcome, RowFinding)
    assert "pure_trees" in outcome.message


def test_row_message_names_every_blessed_spelling_as_remediation() -> None:
    ctx = make_context(table=spelling_table(pyproject=_legacy_block()))

    outcome = assert_role_key_spellings_conformant(ctx=ctx, member=_MEMBER)

    assert isinstance(outcome, RowFinding)
    for spelling in BLESSED_ROLE_SPELLINGS:
        assert spelling in outcome.message


def test_row_ignores_clean_keys_declared_empty() -> None:
    """`[]` on a CLEAN key is legitimate — it makes its check stricter, not blinder."""
    clean_empty = (
        "[tool.livespec_dev_tooling]\n"
        "source_trees = []\n"
        "io_trees = []\n"
        "commands_trees = []\n"
        "supervisor_entry_files = []\n"
        "covered_trees = []\n"
    )
    ctx = make_context(table=spelling_table(pyproject=clean_empty))

    assert assert_role_key_spellings_conformant(ctx=ctx, member=_MEMBER) == RowPass()


def test_row_excludes_a_member_with_no_tool_table() -> None:
    ctx = make_context(table=spelling_table(pyproject="[tool.other]\nname = 'x'\n"))

    outcome = assert_role_key_spellings_conformant(ctx=ctx, member=_MEMBER)

    assert isinstance(outcome, RowPass)
    assert "excluded-with-reason" in outcome.note


def test_row_excludes_a_member_with_no_pyproject() -> None:
    outcome = assert_role_key_spellings_conformant(
        ctx=make_context(table=tree_table(paths=[])), member=_MEMBER
    )

    assert isinstance(outcome, RowPass)
    assert "excluded-with-reason" in outcome.note


def test_row_skips_unreadable_tree() -> None:
    outcome = assert_role_key_spellings_conformant(ctx=make_context(table={}), member=_MEMBER)

    assert isinstance(outcome, RowSkip)
    assert "tree unreadable" in outcome.reason


def test_row_skips_truncated_tree_missing_pyproject() -> None:
    ctx = make_context(table=tree_table(paths=[], truncated=True))

    outcome = assert_role_key_spellings_conformant(ctx=ctx, member=_MEMBER)

    assert isinstance(outcome, RowSkip)
    assert "pyproject.toml absence" in outcome.reason


def test_row_skips_unreadable_pyproject() -> None:
    outcome = assert_role_key_spellings_conformant(
        ctx=make_context(table=tree_table(paths=["pyproject.toml"])), member=_MEMBER
    )

    assert isinstance(outcome, RowSkip)
    assert "pyproject.toml unreadable" in outcome.reason


def test_row_flags_malformed_pyproject() -> None:
    ctx = make_context(table=spelling_table(pyproject="not [toml"))

    outcome = assert_role_key_spellings_conformant(ctx=ctx, member=_MEMBER)

    assert isinstance(outcome, RowFinding)
    assert "malformed pyproject" in outcome.message


def test_row_excludes_a_member_whose_pyproject_has_no_tool_section() -> None:
    ctx = make_context(table=spelling_table(pyproject='[project]\nname = "widget"\n'))

    outcome = assert_role_key_spellings_conformant(ctx=ctx, member=_MEMBER)

    assert isinstance(outcome, RowPass)
    assert "excluded-with-reason" in outcome.note


def test_row_flags_a_union_key_declared_with_an_unsupported_type() -> None:
    """A non-list, non-string, non-table value is not a spelling this schema recognizes."""
    ctx = make_context(
        table=spelling_table(pyproject="[tool.livespec_dev_tooling]\npure_trees = 5\n")
    )

    outcome = assert_role_key_spellings_conformant(ctx=ctx, member=_MEMBER)

    assert isinstance(outcome, RowFinding)
    assert "pure_trees" in outcome.message
