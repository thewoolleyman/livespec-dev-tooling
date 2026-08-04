"""Tests for `livespec_dev_tooling/fleet/_rows_files.py`.

Each committed-file row is exercised across its full outcome lattice —
pass, definitive-absence finding, can't-read skip, truncated-tree skip
— through a canned-response `FleetContext` (no network, no real `gh`).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import test_ensure_plugins as red_plugin_tests
from _gh_railway import lift_gh

from livespec_dev_tooling.fleet import ensure_plugins
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

if TYPE_CHECKING:
    import pytest

__all__: list[str] = []


_MEMBER = FleetMember(repo="widget", repo_class="impl-plugin")
_TREE_ARGS: tuple[str, ...] = ("api", "repos/acme/widget/git/trees/master?recursive=1")
_PYPROJECT_ARGS: tuple[str, ...] = (
    "api",
    "repos/acme/widget/contents/pyproject.toml?ref=master",
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
    return FleetContext(owner="acme", run_gh=lift_gh(runner))


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


def test_ensure_plugins_planner_ignores_malformed_optional_shapes() -> None:
    settings = json.dumps(
        {
            "extraKnownMarketplaces": {
                "scalar": "junk",
                "no-source": {},
                "bad-ref": {"source": {"repo": "owner/repo", "ref": 7}},
            },
            "enabledPlugins": {"plugin@ok": "yes"},
        }
    )
    assert ensure_plugins.planned_commands(settings_text="[]") == ()
    assert ensure_plugins.planned_commands(settings_text=settings) == ()
    assert ensure_plugins.planned_commands(settings_text=json.dumps({})) == ()


def test_ensure_plugins_planner_accepts_list_plugins_and_rejects_bad_list_item() -> None:
    settings = json.dumps({"enabledPlugins": ["one@plugin", "two@plugin"]})
    assert ensure_plugins.planned_commands(settings_text=settings) == (
        ("claude", "plugin", "install", "one@plugin", "-s", "project"),
        ("claude", "plugin", "update", "one@plugin", "-s", "project"),
        ("claude", "plugin", "install", "two@plugin", "-s", "project"),
        ("claude", "plugin", "update", "two@plugin", "-s", "project"),
    )
    assert ensure_plugins.planned_commands(settings_text=json.dumps({"enabledPlugins": [7]})) == ()
    assert (
        ensure_plugins.planned_commands(settings_text=json.dumps({"enabledPlugins": "bad"})) == ()
    )


def test_ensure_plugins_main_noops_without_declared_plugins(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings_dir = tmp_path / ".claude"
    settings_dir.mkdir()
    _ = (settings_dir / "settings.json").write_text("{}", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert ensure_plugins.main() == 0


def test_red_plugin_currency_table_helper_can_omit_justfile() -> None:
    helper = vars(red_plugin_tests)["_plugin_currency_table"]
    table = helper(justfile=None)
    assert all("justfile" not in part for key in table for part in key)


def test_ensure_plugins_subprocess_runner_reports_command_status() -> None:
    assert (
        ensure_plugins.subprocess_runner(
            args=(sys.executable, "-c", "raise SystemExit(3)")
        ).returncode
        == 3
    )


def test_ensure_plugins_subprocess_runner_reports_missing_binary() -> None:
    result = ensure_plugins.subprocess_runner(args=("definitely-missing-livespec-claude-binary",))
    assert result.returncode != 0


# --- uv.lock <-> pin lockstep leg (livespec-glv6) -------------------------

_UVLOCK_ARGS: tuple[str, ...] = (
    "api",
    "repos/acme/widget/contents/uv.lock?ref=master",
    "-H",
    "Accept: application/vnd.github.raw",
)


def _dt_lock(*, tag: str) -> str:
    """A minimal uv.lock locking livespec-dev-tooling at `tag` via a git source."""
    return (
        "[[package]]\n"
        'name = "livespec-dev-tooling"\n'
        'version = "1.2.0"\n'
        f'source = {{ git = "https://github.com/acme/livespec-dev-tooling.git?tag={tag}#abc" }}\n'
    )


def _pin_lock_table(
    *, pyproject: str, latest_tag: str, uv_lock: str | None
) -> dict[tuple[str, ...], GhResult]:
    """A `_pin_table` that always lists `uv.lock` in the tree (content optional).

    `uv_lock=None` lists the file but serves no content, so `file_text`
    returns None — the lock-present-but-unreadable case.
    """
    table = tree_table(paths=["pyproject.toml", "uv.lock"])
    table[_PYPROJECT_ARGS] = GhResult(returncode=0, stdout=pyproject, stderr="")
    if uv_lock is not None:
        table[_UVLOCK_ARGS] = GhResult(returncode=0, stdout=uv_lock, stderr="")
    table[_LATEST_ARGS] = GhResult(
        returncode=0, stdout=json.dumps({"tag_name": latest_tag}), stderr=""
    )
    return table


def test_pin_row_lock_mismatch_is_error_finding() -> None:
    # pyproject pins v1.2.0 (== latest, so the freshness leg alone would
    # PASS), but the committed uv.lock still locks v1.1.0 — the lockstep
    # leg must red the fleet at error severity (livespec-glv6).
    ctx = make_context(
        table=_pin_lock_table(
            pyproject=_PINNED_PYPROJECT, latest_tag="v1.2.0", uv_lock=_dt_lock(tag="v1.1.0")
        )
    )
    outcome = assert_dev_tooling_pin(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowFinding)
    assert outcome.severity == "error"
    assert "v1.1.0" in outcome.message
    assert "v1.2.0" in outcome.message
    assert "uv lock --refresh-package" in outcome.message


def test_pin_row_lock_match_passes() -> None:
    ctx = make_context(
        table=_pin_lock_table(
            pyproject=_PINNED_PYPROJECT, latest_tag="v1.2.0", uv_lock=_dt_lock(tag="v1.2.0")
        )
    )
    assert assert_dev_tooling_pin(ctx=ctx, member=_MEMBER) == RowPass()


def test_pin_row_lock_present_but_unreadable_defers_to_freshness() -> None:
    # uv.lock is listed in the tree but its content can't be fetched →
    # defer to freshness rather than false-red. With a stale pin, the
    # freshness leg then warns (proving control reached it).
    ctx = make_context(
        table=_pin_lock_table(pyproject=_PINNED_PYPROJECT, latest_tag="v1.3.0", uv_lock=None)
    )
    outcome = assert_dev_tooling_pin(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowFinding)
    assert outcome.severity == "warning"


def test_pin_row_lock_shapes_without_a_dt_tag_defer() -> None:
    # Every uv.lock shape from which no dev-tooling git tag is extractable
    # defers to the freshness leg (never a false red). latest == pin, so
    # each defer yields a clean pass.
    defer_locks = [
        "[[[",  # unparseable TOML
        'package = "x"\n',  # `package` is not an array
        'package = ["x"]\n',  # array element is not a table
        '[[package]]\nname = "other"\n',  # no dev-tooling entry
        '[[package]]\nname = "livespec-dev-tooling"\nsource = "x"\n',  # source not a table
        '[[package]]\nname = "livespec-dev-tooling"\nsource = { rev = "x" }\n',  # no git key
        # git source carrying no ?tag= query:
        '[[package]]\nname = "livespec-dev-tooling"\n'
        'source = { git = "https://github.com/acme/livespec-dev-tooling.git#abc" }\n',
    ]
    for lock in defer_locks:
        ctx = make_context(
            table=_pin_lock_table(pyproject=_PINNED_PYPROJECT, latest_tag="v1.2.0", uv_lock=lock)
        )
        assert assert_dev_tooling_pin(ctx=ctx, member=_MEMBER) == RowPass(), lock
