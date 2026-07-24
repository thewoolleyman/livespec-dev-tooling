"""Tests for the persisting-gap ERROR promotion in pin-currency rows.

livespec core work-item `livespec-dh9r` Slice 3 (maintainer-approved
cut): a pin that is stale AND already has an open bump PR for the
latest release is a PERSISTING gap — the self-heal mechanism fired and
could not land — and escalates to an error finding. Plain staleness
(the normal minutes-long window between a release and its bump PR
merging) stays a warning, and an unreadable PR list never escalates
(a can't-read is not a violation — the livespec-dev-tooling-6ge
principle).
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Protocol, cast

from livespec_dev_tooling.fleet._context import (
    FleetContext,
    FleetMember,
    GhResult,
    GhRunner,
    RowFinding,
)

__all__: list[str] = []


_MEMBER = FleetMember(repo="widget", repo_class="impl-plugin")
_TREE_ARGS: tuple[str, ...] = ("api", "repos/acme/widget/git/trees/master?recursive=1")
_LATEST_LIVESPEC_ARGS: tuple[str, ...] = ("api", "repos/acme/livespec/releases/latest")
_OPEN_PRS_ARGS: tuple[str, ...] = ("api", "repos/acme/widget/pulls?state=open&per_page=100")


class PinCurrencyRow(Protocol):
    """One pin-currency row assertion."""

    def __call__(self, *, ctx: FleetContext, member: FleetMember) -> object: ...


def _module() -> object:
    module_path = (
        Path(__file__).resolve().parents[3]
        / "livespec_dev_tooling"
        / "fleet"
        / "_rows_pin_currency.py"
    )
    assert module_path.is_file()
    return importlib.import_module("livespec_dev_tooling.fleet._rows_pin_currency")


def _raw_args(*, path: str) -> tuple[str, ...]:
    return (
        "api",
        f"repos/acme/widget/contents/{path}?ref=master",
        "-H",
        "Accept: application/vnd.github.raw",
    )


def _bump_pr(*, number: int, source: str, tag: str) -> dict[str, object]:
    return {
        "number": number,
        "title": f"chore(deps): bump {source} pin to {tag}",
        "head": {"ref": f"bump-{source}-{tag}"},
    }


def _context(
    *,
    files: dict[str, str],
    latest: dict[tuple[str, ...], str],
    open_prs: list[dict[str, object]] | None,
) -> FleetContext:
    tree_payload = {
        "tree": [{"path": path, "mode": "100644"} for path in files],
        "truncated": False,
    }
    table = {
        _TREE_ARGS: GhResult(returncode=0, stdout=json.dumps(tree_payload), stderr=""),
    }
    for path, text in files.items():
        table[_raw_args(path=path)] = GhResult(returncode=0, stdout=text, stderr="")
    for args, tag in latest.items():
        table[args] = GhResult(returncode=0, stdout=json.dumps({"tag_name": tag}), stderr="")
    if open_prs is not None:
        table[_OPEN_PRS_ARGS] = GhResult(returncode=0, stdout=json.dumps(open_prs), stderr="")

    def run(*, args: list[str], stdin: str | None = None) -> GhResult:
        del stdin
        return table.get(tuple(args), GhResult(returncode=1, stdout="", stderr="no canned"))

    runner: GhRunner = run
    # The filter-consuming preflight context, deliberately. The persisting-gap
    # escalation is context-scoped, so in per-PR CI context EVERY outcome here
    # would be a warning and the four "stays warning" assertions below would
    # pass vacuously — proving nothing about the conjunction's guard
    # conditions (no open PR, an older tag, another source, an unreadable PR
    # list). Exercising the escalating context is what keeps them falsifiable;
    # the per-PR context is covered by test_rows_pin_currency_context_scope.py.
    return FleetContext(owner="acme", run_gh=runner, filter_consuming_preflight=True)


def _stale_compat_files() -> dict[str, str]:
    return {
        ".livespec.jsonc": json.dumps(
            {"impl-plugin": {"compat": {"pinned": "v1.0.0", "livespec": "v1"}}}
        )
    }


def _row(*, module: object) -> PinCurrencyRow:
    return cast("PinCurrencyRow", module.assert_livespec_compat_pin_currency)


def test_stale_with_open_bump_pr_for_latest_is_an_error() -> None:
    module = _module()
    ctx = _context(
        files=_stale_compat_files(),
        latest={_LATEST_LIVESPEC_ARGS: "v1.1.0"},
        open_prs=[_bump_pr(number=7, source="livespec", tag="v1.1.0")],
    )

    outcome = _row(module=module)(ctx=ctx, member=_MEMBER)

    assert isinstance(outcome, RowFinding)
    assert outcome.severity == "error"
    assert "widget" in outcome.message
    assert "livespec_jsonc_compat_pinned" in outcome.message
    assert "persisting" in outcome.message
    assert "#7" in outcome.message


def test_stale_without_open_bump_pr_stays_warning() -> None:
    module = _module()
    ctx = _context(
        files=_stale_compat_files(),
        latest={_LATEST_LIVESPEC_ARGS: "v1.1.0"},
        open_prs=[],
    )

    outcome = _row(module=module)(ctx=ctx, member=_MEMBER)

    assert isinstance(outcome, RowFinding)
    assert outcome.severity == "warning"


def test_stale_with_open_bump_pr_for_an_older_tag_stays_warning() -> None:
    module = _module()
    ctx = _context(
        files=_stale_compat_files(),
        latest={_LATEST_LIVESPEC_ARGS: "v1.1.0"},
        open_prs=[_bump_pr(number=3, source="livespec", tag="v1.0.5")],
    )

    outcome = _row(module=module)(ctx=ctx, member=_MEMBER)

    assert isinstance(outcome, RowFinding)
    assert outcome.severity == "warning"


def test_stale_with_open_bump_pr_for_another_source_stays_warning() -> None:
    module = _module()
    ctx = _context(
        files=_stale_compat_files(),
        latest={_LATEST_LIVESPEC_ARGS: "v1.1.0"},
        open_prs=[_bump_pr(number=9, source="livespec-dev-tooling", tag="v1.1.0")],
    )

    outcome = _row(module=module)(ctx=ctx, member=_MEMBER)

    assert isinstance(outcome, RowFinding)
    assert outcome.severity == "warning"


def test_unreadable_pr_list_never_escalates() -> None:
    module = _module()
    ctx = _context(
        files=_stale_compat_files(),
        latest={_LATEST_LIVESPEC_ARGS: "v1.1.0"},
        open_prs=None,
    )

    outcome = _row(module=module)(ctx=ctx, member=_MEMBER)

    assert isinstance(outcome, RowFinding)
    assert outcome.severity == "warning"
