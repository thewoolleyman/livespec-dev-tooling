"""Edge coverage for the persisting-gap escalation seams.

Covers the dev-tooling-pin leg's persisting-gap error and the REST
payload normalizer's degenerate shapes (non-list payload, non-object
items, items without a resolvable head ref).
"""

from __future__ import annotations

import json

from _gh_railway import lift_gh

from livespec_dev_tooling.fleet._context import (
    FleetContext,
    FleetMember,
    GhResult,
    GhRunner,
    RowFinding,
)
from livespec_dev_tooling.fleet._rows_files import assert_dev_tooling_pin
from livespec_dev_tooling.fleet._rows_pin_currency import open_bump_prs_for

__all__: list[str] = []


_MEMBER = FleetMember(repo="widget", repo_class="impl-plugin")
_TREE_ARGS: tuple[str, ...] = ("api", "repos/acme/widget/git/trees/master?recursive=1")
_PYPROJECT_ARGS: tuple[str, ...] = (
    "api",
    "repos/acme/widget/contents/pyproject.toml?ref=master",
    "-H",
    "Accept: application/vnd.github.raw",
)
_LATEST_DEV_TOOLING_ARGS: tuple[str, ...] = (
    "api",
    "repos/acme/livespec-dev-tooling/releases/latest",
)
_OPEN_PRS_ARGS: tuple[str, ...] = ("api", "repos/acme/widget/pulls?state=open&per_page=100")

_PINNED_PYPROJECT = '[tool.uv.sources]\nlivespec-dev-tooling = { git = "x", tag = "v1.2.0" }\n'


def _context(*, table: dict[tuple[str, ...], GhResult]) -> FleetContext:
    def run(*, args: list[str], stdin: str | None = None) -> GhResult:
        del stdin
        return table.get(tuple(args), GhResult(returncode=1, stdout="", stderr="no canned"))

    runner: GhRunner = run
    # The filter-consuming preflight context, deliberately. The persisting-gap
    # escalation is context-scoped, so in per-PR CI context EVERY outcome here
    # would be a warning and each "stays warning" assertion below would pass
    # vacuously — proving nothing about the conjunction's guard conditions.
    # Exercising the escalating context is what keeps them falsifiable; the
    # per-PR context is covered by test_rows_pin_currency_context_scope.py.
    return FleetContext(owner="acme", run_gh=lift_gh(runner), filter_consuming_preflight=True)


def _pin_table(*, open_prs_payload: object) -> dict[tuple[str, ...], GhResult]:
    tree_payload = {
        "tree": [{"path": "pyproject.toml", "mode": "100644"}],
        "truncated": False,
    }
    return {
        _TREE_ARGS: GhResult(returncode=0, stdout=json.dumps(tree_payload), stderr=""),
        _PYPROJECT_ARGS: GhResult(returncode=0, stdout=_PINNED_PYPROJECT, stderr=""),
        _LATEST_DEV_TOOLING_ARGS: GhResult(
            returncode=0, stdout=json.dumps({"tag_name": "v1.3.0"}), stderr=""
        ),
        _OPEN_PRS_ARGS: GhResult(returncode=0, stdout=json.dumps(open_prs_payload), stderr=""),
    }


def test_dev_tooling_pin_persisting_gap_is_error() -> None:
    ctx = _context(
        table=_pin_table(
            open_prs_payload=[
                {
                    "number": 11,
                    "title": "chore(deps): bump livespec-dev-tooling pin to v1.3.0",
                    "head": {"ref": "bump-livespec-dev-tooling-v1.3.0"},
                }
            ]
        )
    )

    outcome = assert_dev_tooling_pin(ctx=ctx, member=_MEMBER)

    assert isinstance(outcome, RowFinding)
    assert outcome.severity == "error"
    assert "widget" in outcome.message
    assert "persisting" in outcome.message
    assert "#11" in outcome.message


def test_dev_tooling_pin_stale_without_matching_pr_stays_warning() -> None:
    ctx = _context(table=_pin_table(open_prs_payload=[]))

    outcome = assert_dev_tooling_pin(ctx=ctx, member=_MEMBER)

    assert isinstance(outcome, RowFinding)
    assert outcome.severity == "warning"


def test_open_bump_prs_for_non_list_payload_yields_no_records() -> None:
    ctx = _context(
        table={
            _OPEN_PRS_ARGS: GhResult(
                returncode=0, stdout=json.dumps({"message": "unexpected"}), stderr=""
            )
        }
    )

    assert open_bump_prs_for(ctx=ctx, member=_MEMBER) == []


def test_open_bump_prs_for_skips_unusable_items_and_keeps_valid_rest_items() -> None:
    payload = [
        "junk",
        {"number": 5, "title": "chore(deps): bump livespec pin to v9.9.9"},
        {
            "number": 6,
            "title": "chore(deps): bump livespec pin to v9.9.9",
            "head": {"ref": 42},
        },
        {
            "number": 7,
            "title": "chore(deps): bump livespec pin to v9.9.9",
            "head": {"ref": "bump-livespec-v9.9.9"},
        },
    ]
    ctx = _context(
        table={_OPEN_PRS_ARGS: GhResult(returncode=0, stdout=json.dumps(payload), stderr="")}
    )

    prs = open_bump_prs_for(ctx=ctx, member=_MEMBER)

    assert prs is not None
    assert [pr.number for pr in prs] == [7]
