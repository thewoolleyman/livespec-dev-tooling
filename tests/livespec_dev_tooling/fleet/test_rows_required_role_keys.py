"""Tests for `livespec_dev_tooling/fleet/_rows_required_role_keys.py`."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from livespec_dev_tooling.config import REQUIRED_ROLE_KEYS, Config
from livespec_dev_tooling.fleet import _rows_required_role_keys as role_keys
from livespec_dev_tooling.fleet._context import (
    FleetContext,
    FleetMember,
    GhResult,
    GhRunner,
    RowFinding,
    RowPass,
    RowSkip,
    TreeState,
)
from livespec_dev_tooling.fleet._rows_required_role_keys import (
    assert_required_role_keys_declared,
)

_VENDOR_DIR = Path(role_keys.__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from _gh_railway import lift_gh  # noqa: E402  — sibling helper, after the sys.path insert.
from returns.io import IOFailure  # noqa: E402  — vendor-path-aware import after sys.path insert.

__all__: list[str] = []


_MEMBER = FleetMember(repo="widget", repo_class="impl-plugin")
_TREE_ARGS: tuple[str, ...] = ("api", "repos/acme/widget/git/trees/master?recursive=1")
_JUSTFILE_ARGS: tuple[str, ...] = (
    "api",
    "repos/acme/widget/contents/justfile?ref=master",
    "-H",
    "Accept: application/vnd.github.raw",
)
_PYPROJECT_ARGS: tuple[str, ...] = (
    "api",
    "repos/acme/widget/contents/pyproject.toml?ref=master",
    "-H",
    "Accept: application/vnd.github.raw",
)
_LAYOUT_JUSTFILE = "check:\n    targets=(\n        check-no-inheritance\n    )\n"
_BASELINE_JUSTFILE = (
    "check:\n"
    "    targets=(\n"
    "        check-plugin-resolution\n"
    "        check-primary-checkout-commit-refuse-hook-installed\n"
    "    )\n"
)


def make_context(*, table: dict[tuple[str, ...], GhResult]) -> FleetContext:
    """A `FleetContext` for owner `acme` over a canned-response runner."""

    def run(*, args: list[str], stdin: str | None = None) -> GhResult:
        del stdin
        return table.get(tuple(args), GhResult(returncode=1, stdout="", stderr="no canned"))

    runner: GhRunner = run
    return FleetContext(owner="acme", run_gh=lift_gh(runner))


def tree_table(*, paths: list[str], truncated: bool = False) -> dict[tuple[str, ...], GhResult]:
    """A canned table whose tree call yields `paths`."""
    entries = [{"path": path, "mode": "100644"} for path in paths]
    payload = {"tree": entries, "truncated": truncated}
    return {_TREE_ARGS: GhResult(returncode=0, stdout=json.dumps(payload), stderr="")}


def _all_required_empty_block() -> str:
    lines = ["[tool.livespec_dev_tooling]"]
    fields = Config.__dataclass_fields__
    for key in sorted(REQUIRED_ROLE_KEYS):
        default = fields[key].default
        value = '""' if default is None else "[]"
        lines.append(f"{key} = {value}")
    return "\n".join(lines) + "\n"


def _role_key_table(*, justfile: str, pyproject: str) -> dict[tuple[str, ...], GhResult]:
    table = tree_table(paths=["justfile", "pyproject.toml"])
    table[_JUSTFILE_ARGS] = GhResult(returncode=0, stdout=justfile, stderr="")
    table[_PYPROJECT_ARGS] = GhResult(returncode=0, stdout=pyproject, stderr="")
    return table


def test_required_role_keys_row_fails_when_layout_check_omits_key() -> None:
    missing_key = sorted(REQUIRED_ROLE_KEYS)[0]
    pyproject = _all_required_empty_block().replace(f"{missing_key} = []\n", "")
    ctx = make_context(table=_role_key_table(justfile=_LAYOUT_JUSTFILE, pyproject=pyproject))

    outcome = assert_required_role_keys_declared(ctx=ctx, member=_MEMBER)

    assert isinstance(outcome, RowFinding)
    assert missing_key in outcome.message
    assert "declare the real value" in outcome.message


def test_required_role_keys_row_skips_when_the_checks_package_is_unreadable(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unreadable checks package SKIPS the row rather than passing it.

    The walk that resolves layout-dependent slugs is railway-typed, and this is its
    fail-closed branch. It exists because the natural unwrap is silently wrong: an
    I/O error defaulted to an empty slug set reads as "no layout-dependent checks
    wired", which is an EXCLUSION, which PASSES. `RowSkip` instead records the row as
    UNEVALUATED, which the conformance engine already tracks — a row that could not
    be determined must never be indistinguishable from a row that passed.
    """
    missing_key = sorted(REQUIRED_ROLE_KEYS)[0]
    pyproject = _all_required_empty_block().replace(f"{missing_key} = []\n", "")
    ctx = make_context(table=_role_key_table(justfile=_LAYOUT_JUSTFILE, pyproject=pyproject))
    monkeypatch.setattr(
        role_keys,
        "layout_dependent_check_slugs",
        lambda: IOFailure(OSError("checks package unreadable")),
    )

    outcome = assert_required_role_keys_declared(ctx=ctx, member=_MEMBER)

    assert isinstance(
        outcome, RowSkip
    ), f"an unreadable checks package must SKIP, never pass; got {type(outcome).__name__}"
    assert "checks package unreadable" in outcome.reason


def test_required_role_keys_row_accepts_declared_empty_keys() -> None:
    ctx = make_context(
        table=_role_key_table(justfile=_LAYOUT_JUSTFILE, pyproject=_all_required_empty_block())
    )

    assert assert_required_role_keys_declared(ctx=ctx, member=_MEMBER) == RowPass()


def test_required_role_keys_row_names_layout_independent_exclusion() -> None:
    ctx = make_context(table=_role_key_table(justfile=_BASELINE_JUSTFILE, pyproject=""))

    outcome = assert_required_role_keys_declared(ctx=ctx, member=_MEMBER)

    assert isinstance(outcome, RowPass)
    assert "excluded-with-reason" in outcome.note
    assert "no layout-dependent checks wired" in outcome.note


def test_required_role_keys_row_skips_unreadable_tree() -> None:
    outcome = assert_required_role_keys_declared(ctx=make_context(table={}), member=_MEMBER)
    assert isinstance(outcome, RowSkip)
    assert "tree unreadable" in outcome.reason


def test_required_role_keys_row_skips_inconclusive_missing_files() -> None:
    ctx_justfile = make_context(table=tree_table(paths=[], truncated=True))
    justfile_outcome = assert_required_role_keys_declared(ctx=ctx_justfile, member=_MEMBER)
    assert isinstance(justfile_outcome, RowSkip)
    assert "justfile absence" in justfile_outcome.reason

    table = tree_table(paths=["justfile"], truncated=True)
    table[_JUSTFILE_ARGS] = GhResult(returncode=0, stdout=_LAYOUT_JUSTFILE, stderr="")
    pyproject_outcome = assert_required_role_keys_declared(
        ctx=make_context(table=table), member=_MEMBER
    )
    assert isinstance(pyproject_outcome, RowSkip)
    assert "pyproject.toml absence" in pyproject_outcome.reason


def test_required_role_keys_row_skips_unreadable_contents() -> None:
    justfile_outcome = assert_required_role_keys_declared(
        ctx=make_context(table=tree_table(paths=["justfile"])), member=_MEMBER
    )
    assert isinstance(justfile_outcome, RowSkip)
    assert "justfile unreadable" in justfile_outcome.reason

    table = tree_table(paths=["justfile", "pyproject.toml"])
    table[_JUSTFILE_ARGS] = GhResult(returncode=0, stdout=_LAYOUT_JUSTFILE, stderr="")
    pyproject_outcome = assert_required_role_keys_declared(
        ctx=make_context(table=table), member=_MEMBER
    )
    assert isinstance(pyproject_outcome, RowSkip)
    assert "pyproject.toml unreadable" in pyproject_outcome.reason


def test_required_role_keys_row_flags_malformed_pyproject() -> None:
    ctx = make_context(table=_role_key_table(justfile=_LAYOUT_JUSTFILE, pyproject="not [toml"))
    outcome = assert_required_role_keys_declared(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowFinding)
    assert "malformed pyproject" in outcome.message


def test_required_role_keys_row_missing_pyproject_fails_when_in_scope() -> None:
    table = tree_table(paths=["justfile"])
    table[_JUSTFILE_ARGS] = GhResult(returncode=0, stdout=_LAYOUT_JUSTFILE, stderr="")
    outcome = assert_required_role_keys_declared(ctx=make_context(table=table), member=_MEMBER)
    assert isinstance(outcome, RowFinding)
    assert sorted(REQUIRED_ROLE_KEYS)[0] in outcome.message


def test_required_role_keys_row_names_missing_justfile_exclusion() -> None:
    table = tree_table(paths=["pyproject.toml"])
    table[_PYPROJECT_ARGS] = GhResult(returncode=0, stdout="", stderr="")

    outcome = assert_required_role_keys_declared(ctx=make_context(table=table), member=_MEMBER)

    assert isinstance(outcome, RowPass)
    assert "excluded-with-reason" in outcome.note
    assert "justfile not found" in outcome.note


def test_required_role_keys_row_missing_tool_table_fails_when_in_scope() -> None:
    ctx = make_context(
        table=_role_key_table(justfile=_LAYOUT_JUSTFILE, pyproject="[tool.other]\nname = 'x'\n")
    )

    outcome = assert_required_role_keys_declared(ctx=ctx, member=_MEMBER)

    assert isinstance(outcome, RowFinding)
    assert sorted(REQUIRED_ROLE_KEYS)[0] in outcome.message


def test_required_role_keys_row_defensively_skips_impossible_empty_justfile_text(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    table = tree_table(paths=["justfile", "pyproject.toml"])
    table[_PYPROJECT_ARGS] = GhResult(returncode=0, stdout="", stderr="")

    def no_conclusive_justfile(*, ctx: FleetContext, member: FleetMember, tree: TreeState):
        del ctx, member, tree
        return None, None

    monkeypatch.setattr(role_keys, "_required_role_justfile_text", no_conclusive_justfile)

    outcome = assert_required_role_keys_declared(ctx=make_context(table=table), member=_MEMBER)

    assert isinstance(outcome, RowSkip)
    assert "justfile unreadable" in outcome.reason
