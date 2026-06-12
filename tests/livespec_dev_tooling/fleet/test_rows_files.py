"""Tests for `livespec_dev_tooling/fleet/_rows_files.py`.

Each committed-file row is exercised across its full outcome lattice —
pass, definitive-absence finding, can't-read skip, truncated-tree skip
— through a canned-response `FleetContext` (no network, no real `gh`).
"""

from __future__ import annotations

import json

from livespec_dev_tooling.fleet._context import (
    FleetContext,
    FleetMember,
    GhResult,
    GhRunner,
    RowFinding,
    RowPass,
    RowSkip,
)
from livespec_dev_tooling.fleet._rows_files import (
    BUMP_PIN_WORKFLOW,
    CI_WORKFLOW,
    COPIER_ANSWERS,
    PIN_FRESHNESS_WORKFLOW,
    RELEASE_DISPATCH_WORKFLOW,
    assert_bump_pin_workflow,
    assert_ci_workflow,
    assert_copier_answers,
    assert_dev_tooling_pin,
    assert_no_tracked_gitlinks,
    assert_pin_freshness_workflow,
    assert_release_dispatch_workflow,
)

__all__: list[str] = []


_MEMBER = FleetMember(repo="widget", repo_class="impl-plugin")
_TREE_ARGS: tuple[str, ...] = ("api", "repos/acme/widget/git/trees/master?recursive=1")
_PYPROJECT_ARGS: tuple[str, ...] = (
    "api",
    "repos/acme/widget/contents/pyproject.toml",
    "-H",
    "Accept: application/vnd.github.raw",
)
_LATEST_ARGS: tuple[str, ...] = ("api", "repos/acme/livespec-dev-tooling/releases/latest")

_PINNED_PYPROJECT = '[tool.uv.sources]\nlivespec-dev-tooling = { git = "x", tag = "v1.2.0" }\n'


def make_context(*, table: dict[tuple[str, ...], GhResult]) -> FleetContext:
    """A `FleetContext` for owner `acme` over a canned-response runner."""

    def run(*, args: list[str], stdin: str | None = None) -> GhResult:
        del stdin
        return table.get(tuple(args), GhResult(returncode=1, stdout="", stderr="no canned"))

    runner: GhRunner = run
    return FleetContext(owner="acme", run_gh=runner)


def tree_table(
    *, paths: list[str], truncated: bool = False, gitlinks: list[str] | None = None
) -> dict[tuple[str, ...], GhResult]:
    """A canned table whose tree call yields `paths` (plus optional gitlinks)."""
    entries: list[dict[str, str]] = [{"path": p, "mode": "100644"} for p in paths]
    entries.extend({"path": p, "mode": "160000"} for p in (gitlinks or []))
    payload = {"tree": entries, "truncated": truncated}
    return {_TREE_ARGS: GhResult(returncode=0, stdout=json.dumps(payload), stderr="")}


def test_workflow_rows_pass_when_files_present() -> None:
    paths = [CI_WORKFLOW, BUMP_PIN_WORKFLOW, PIN_FRESHNESS_WORKFLOW, RELEASE_DISPATCH_WORKFLOW]
    ctx = make_context(table=tree_table(paths=paths))
    assert assert_ci_workflow(ctx=ctx, member=_MEMBER) == RowPass()
    assert assert_bump_pin_workflow(ctx=ctx, member=_MEMBER) == RowPass()
    assert assert_pin_freshness_workflow(ctx=ctx, member=_MEMBER) == RowPass()
    assert assert_release_dispatch_workflow(ctx=ctx, member=_MEMBER) == RowPass()


def test_workflow_row_missing_file_is_finding() -> None:
    ctx = make_context(table=tree_table(paths=[CI_WORKFLOW]))
    outcome = assert_bump_pin_workflow(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowFinding)
    assert BUMP_PIN_WORKFLOW in outcome.message
    assert outcome.severity == "error"


def test_workflow_row_unreadable_tree_skips() -> None:
    ctx = make_context(table={})
    outcome = assert_ci_workflow(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowSkip)
    assert "unreadable" in outcome.reason


def test_workflow_row_truncated_tree_skips_on_absence() -> None:
    ctx = make_context(table=tree_table(paths=["something-else"], truncated=True))
    outcome = assert_ci_workflow(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowSkip)
    assert "truncated" in outcome.reason


def test_copier_answers_row_present_and_absent() -> None:
    ctx_present = make_context(table=tree_table(paths=[COPIER_ANSWERS]))
    assert assert_copier_answers(ctx=ctx_present, member=_MEMBER) == RowPass()
    ctx_absent = make_context(table=tree_table(paths=[]))
    outcome = assert_copier_answers(ctx=ctx_absent, member=_MEMBER)
    assert isinstance(outcome, RowFinding)
    assert COPIER_ANSWERS in outcome.message


def test_gitlinks_row_clean_tree_passes() -> None:
    ctx = make_context(table=tree_table(paths=["a", "b"]))
    assert assert_no_tracked_gitlinks(ctx=ctx, member=_MEMBER) == RowPass()


def test_gitlinks_row_gitlink_is_finding() -> None:
    ctx = make_context(table=tree_table(paths=["a"], gitlinks=["vendored/dep"]))
    outcome = assert_no_tracked_gitlinks(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowFinding)
    assert "vendored/dep" in outcome.message


def test_gitlinks_row_unreadable_and_truncated_skip() -> None:
    ctx_unreadable = make_context(table={})
    assert isinstance(assert_no_tracked_gitlinks(ctx=ctx_unreadable, member=_MEMBER), RowSkip)
    ctx_truncated = make_context(table=tree_table(paths=["a"], truncated=True))
    outcome = assert_no_tracked_gitlinks(ctx=ctx_truncated, member=_MEMBER)
    assert isinstance(outcome, RowSkip)
    assert "truncated" in outcome.reason


def _pin_table(*, pyproject: str, latest_tag: str | None) -> dict[tuple[str, ...], GhResult]:
    table = tree_table(paths=["pyproject.toml"])
    table[_PYPROJECT_ARGS] = GhResult(returncode=0, stdout=pyproject, stderr="")
    if latest_tag is not None:
        table[_LATEST_ARGS] = GhResult(
            returncode=0, stdout=json.dumps({"tag_name": latest_tag}), stderr=""
        )
    return table


def test_pin_row_fresh_pin_passes() -> None:
    ctx = make_context(table=_pin_table(pyproject=_PINNED_PYPROJECT, latest_tag="v1.2.0"))
    assert assert_dev_tooling_pin(ctx=ctx, member=_MEMBER) == RowPass()


def test_pin_row_stale_pin_is_warning_finding() -> None:
    ctx = make_context(table=_pin_table(pyproject=_PINNED_PYPROJECT, latest_tag="v1.3.0"))
    outcome = assert_dev_tooling_pin(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowFinding)
    assert outcome.severity == "warning"
    assert "v1.2.0" in outcome.message
    assert "v1.3.0" in outcome.message


def test_pin_row_unreadable_latest_release_still_passes_presence() -> None:
    ctx = make_context(table=_pin_table(pyproject=_PINNED_PYPROJECT, latest_tag=None))
    outcome = assert_dev_tooling_pin(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowPass)
    assert "freshness unverified" in outcome.note


def test_pin_row_latest_release_without_tag_name_passes_presence() -> None:
    table = _pin_table(pyproject=_PINNED_PYPROJECT, latest_tag=None)
    table[_LATEST_ARGS] = GhResult(returncode=0, stdout=json.dumps({"id": 1}), stderr="")
    ctx = make_context(table=table)
    outcome = assert_dev_tooling_pin(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowPass)
    assert "freshness unverified" in outcome.note


def test_pin_row_missing_pin_entry_is_finding() -> None:
    no_pin = '[tool.uv.sources]\nother-lib = { git = "x", tag = "v9" }\n'
    ctx = make_context(table=_pin_table(pyproject=no_pin, latest_tag="v1.2.0"))
    outcome = assert_dev_tooling_pin(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowFinding)
    assert outcome.severity == "error"


def test_pin_row_pin_entry_without_tag_is_finding() -> None:
    no_tag = '[tool.uv.sources]\nlivespec-dev-tooling = { git = "x" }\n'
    ctx = make_context(table=_pin_table(pyproject=no_tag, latest_tag="v1.2.0"))
    assert isinstance(assert_dev_tooling_pin(ctx=ctx, member=_MEMBER), RowFinding)


def test_pin_row_tag_value_not_a_string_is_finding() -> None:
    bad_tag = "[tool.uv.sources]\nlivespec-dev-tooling = { tag = 7 }\n"
    ctx = make_context(table=_pin_table(pyproject=bad_tag, latest_tag="v1.2.0"))
    assert isinstance(assert_dev_tooling_pin(ctx=ctx, member=_MEMBER), RowFinding)


def test_pin_row_unparseable_or_shapeless_pyproject_is_finding() -> None:
    for text in (
        "not [ valid toml",
        'tool = "scalar"\n',
        '[tool]\nuv = "scalar"\n',
        '[tool.uv]\nsources = "scalar"\n',
    ):
        ctx = make_context(table=_pin_table(pyproject=text, latest_tag="v1.2.0"))
        outcome = assert_dev_tooling_pin(ctx=ctx, member=_MEMBER)
        assert isinstance(outcome, RowFinding), text


def test_pin_row_missing_pyproject_is_finding() -> None:
    ctx = make_context(table=tree_table(paths=["README.md"]))
    outcome = assert_dev_tooling_pin(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowFinding)
    assert "pyproject.toml" in outcome.message


def test_pin_row_unreadable_tree_and_truncated_tree_skip() -> None:
    ctx_unreadable = make_context(table={})
    assert isinstance(assert_dev_tooling_pin(ctx=ctx_unreadable, member=_MEMBER), RowSkip)
    ctx_truncated = make_context(table=tree_table(paths=["README.md"], truncated=True))
    outcome = assert_dev_tooling_pin(ctx=ctx_truncated, member=_MEMBER)
    assert isinstance(outcome, RowSkip)
    assert "truncated" in outcome.reason


def test_pin_row_unreadable_pyproject_content_skips() -> None:
    ctx = make_context(table=tree_table(paths=["pyproject.toml"]))
    outcome = assert_dev_tooling_pin(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowSkip)
    assert "unreadable" in outcome.reason
