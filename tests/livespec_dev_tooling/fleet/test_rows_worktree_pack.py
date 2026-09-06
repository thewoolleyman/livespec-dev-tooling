"""Tests for `livespec_dev_tooling/fleet/_rows_worktree_pack.py`.

The `worktree-pack-wired` row across its full outcome lattice — a fully wired
member passes, a deliberately UNWIRED one is red with every missing line
named, an ignore-only gap reports at warning severity, and every can't-read
shape (unreadable tree, truncated tree, unreadable file) skips — through the
canned-response `FleetContext` the sibling row tests share (no network, no
real `gh`). What the predicate decides is tested next door, against texts.
"""

from __future__ import annotations

import json

from test_rows_files import _MEMBER, make_context, tree_table
from test_worktree_pack_wiring import (
    WIRED_GITIGNORE,
    WIRED_JUSTFILE,
    WIRED_LEFTHOOK,
    WIRED_LIVESPEC_JSONC,
)

from livespec_dev_tooling.fleet._context import GhResult, RowFinding, RowPass, RowSkip
from livespec_dev_tooling.fleet._rows_worktree_pack import assert_worktree_pack_wired
from livespec_dev_tooling.fleet.worktree_pack_wiring import (
    GITIGNORE_PATH,
    JUSTFILE_PATH,
    LEFTHOOK_PATH,
    LIVESPEC_JSONC_PATH,
    WIRING_FILES,
    worktree_pack_wiring_gaps,
)

__all__: list[str] = []


def _wiring_table(
    *,
    justfile: str = WIRED_JUSTFILE,
    gitignore: str = WIRED_GITIGNORE,
    lefthook: str = WIRED_LEFTHOOK,
    livespec_jsonc: str = WIRED_LIVESPEC_JSONC,
    paths: list[str] | None = None,
    truncated: bool = False,
    unreadable: str | None = None,
) -> dict[tuple[str, ...], GhResult]:
    """A canned table serving the four wiring files from `widget`'s master."""
    table = tree_table(paths=list(WIRING_FILES) if paths is None else paths, truncated=truncated)
    texts = {
        JUSTFILE_PATH: justfile,
        GITIGNORE_PATH: gitignore,
        LEFTHOOK_PATH: lefthook,
        LIVESPEC_JSONC_PATH: livespec_jsonc,
    }
    for path, text in texts.items():
        if path == unreadable:
            continue
        args = (
            "api",
            f"repos/acme/widget/contents/{path}?ref=master",
            "-H",
            "Accept: application/vnd.github.raw",
        )
        table[args] = GhResult(returncode=0, stdout=text, stderr="")
    return table


def test_fully_wired_member_passes() -> None:
    assert (
        worktree_pack_wiring_gaps(
            justfile_text=WIRED_JUSTFILE,
            gitignore_text=WIRED_GITIGNORE,
            lefthook_text=WIRED_LEFTHOOK,
            livespec_jsonc_text=WIRED_LIVESPEC_JSONC,
        )
        == ()
    )
    ctx = make_context(table=_wiring_table())
    assert assert_worktree_pack_wired(ctx=ctx, member=_MEMBER) == RowPass()


def test_deliberately_unwired_member_is_red_with_every_missing_line() -> None:
    # The lockstep half that proves the row REFUSES: a member carrying all four
    # files, none of them wired.
    ctx = make_context(
        table=_wiring_table(
            justfile="check:\n    echo ok\n",
            gitignore="__pycache__/\n",
            lefthook="pre-commit:\n  commands:\n    01-check:\n      run: just check\n",
            livespec_jsonc='{\n  "template": "livespec"\n}\n',
        )
    )
    outcome = assert_worktree_pack_wired(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowFinding)
    assert outcome.severity == "error"
    for expected in (
        "import? 'dev-tooling/worktree.just'",
        "import? 'dev-tooling/branch-protection.just'",
        "install-worktree-pack:",
        "/dev-tooling/gate-run.sh",
        "`pre-commit` whose name-sorted FIRST command",
        "`pre-push` whose name-sorted FIRST command",
        '"worktree_discipline"',
    ):
        assert expected in outcome.message


def test_only_ignore_gaps_report_at_warning_severity() -> None:
    # A missing root ignore entry is real drift, but the pack's own generated
    # dev-tooling/.gitignore still ignores the file in place, so it must not
    # red the fleet.
    ctx = make_context(
        table=_wiring_table(gitignore=WIRED_GITIGNORE.replace("/dev-tooling/gate-run.sh\n", ""))
    )
    outcome = assert_worktree_pack_wired(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowFinding)
    assert outcome.severity == "warning"
    assert "/dev-tooling/gate-run.sh" in outcome.message


def test_unreadable_file_skips_rather_than_finding() -> None:
    ctx = make_context(table=_wiring_table(unreadable=LEFTHOOK_PATH))
    outcome = assert_worktree_pack_wired(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowSkip)
    assert "lefthook.yml unreadable" in outcome.reason


def test_unreadable_tree_skips() -> None:
    ctx = make_context(table={})
    outcome = assert_worktree_pack_wired(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowSkip)
    assert "master tree unreadable" in outcome.reason


def test_truncated_tree_skips_on_absence() -> None:
    ctx = make_context(table=_wiring_table(paths=["justfile"], truncated=True))
    outcome = assert_worktree_pack_wired(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowSkip)
    assert "truncated" in outcome.reason


def test_definitively_absent_file_is_a_finding() -> None:
    ctx = make_context(table=_wiring_table(paths=[JUSTFILE_PATH, GITIGNORE_PATH]))
    outcome = assert_worktree_pack_wired(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowFinding)
    assert "required file lefthook.yml missing from master" in outcome.message


def test_tree_payload_shape_is_the_one_the_row_reads() -> None:
    # Guards the canned fixture itself: every wiring file must be in the tree
    # the row consults, or the tests above would exercise the absence branch.
    payload = json.loads(
        _wiring_table()[("api", "repos/acme/widget/git/trees/master?recursive=1")].stdout
    )
    assert {entry["path"] for entry in payload["tree"]} == set(WIRING_FILES)
