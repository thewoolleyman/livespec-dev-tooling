"""Every pin-currency STALENESS finding carries the non-excluding class.

`SPECIFICATION/contracts.md` section "Pin-currency severity policy" (v093) and
`SPECIFICATION/scenarios.md` section "Scenario: a member whose only error
findings are stale pins still receives the release dispatch": a finding of
either ratified staleness class stays error-severity, is named in the run's
summary, and MUST NOT exclude its member from the `sibling-released` dispatch
matrix — the dispatch is the remedy for a stale pin, so excluding the member
removes the cure.

FOUR SITES, exercised INDEPENDENTLY, for the reason `_rows_files`'s own "both
persisting-gap sites must move together" comment records: the two staleness
classes are rendered once in `_rows_pin_currency` (the three inventory-walked
pin formats) and again in `_rows_files` (the `dev-tooling-pin` row's staleness
leg), and a half-marked promotion is invisible — the unmarked site emits an
ordinary error finding, the filter excludes its member, and that member silently
stops receiving the dispatch that would cure it.

AND A CONTROL. The same `dev-tooling-pin` row's PRESENCE leg must carry NO
class, because the exception is about staleness rather than about the row: a
member with no pin at all cannot absorb a bump, so it must still be excluded.
Without the control these tests would pass just as well against a filter keyed
on the row id, which is the implementation the clause forbids.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Protocol, cast

from _gh_railway import lift_gh

from livespec_dev_tooling.fleet._context import (
    FleetContext,
    FleetMember,
    GhResult,
    GhRunner,
    RowFinding,
)
from livespec_dev_tooling.fleet._row_finding import PIN_STALENESS_FINDING_CLASS
from livespec_dev_tooling.fleet._rows_files import assert_dev_tooling_pin
from livespec_dev_tooling.fleet._rows_pin_currency import assert_livespec_compat_pin_currency

__all__: list[str] = []


_MEMBER = FleetMember(repo="widget", repo_class="impl-plugin")
_TREE_ARGS: tuple[str, ...] = ("api", "repos/acme/widget/git/trees/master?recursive=1")
_LATEST_LIVESPEC_ARGS: tuple[str, ...] = ("api", "repos/acme/livespec/releases/latest")
_LATEST_DEV_TOOLING_ARGS: tuple[str, ...] = (
    "api",
    "repos/acme/livespec-dev-tooling/releases/latest",
)
_OPEN_PRS_ARGS: tuple[str, ...] = ("api", "repos/acme/widget/pulls?state=open&per_page=100")

# Comfortably past the ratified two-hour settle window, so the never-fired
# class escalates rather than resting on a boundary.
_PAST_THE_WINDOW = timedelta(hours=3, minutes=14)


class PinRow(Protocol):
    """One obligation row assertion."""

    def __call__(self, *, ctx: FleetContext, member: FleetMember) -> RowFinding: ...


def _published_past_the_window() -> str:
    """A `published_at` old enough for the never-fired class to escalate."""
    return (datetime.now(tz=timezone.utc) - _PAST_THE_WINDOW).strftime("%Y-%m-%dT%H:%M:%SZ")


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
    latest: dict[tuple[str, ...], dict[str, object]],
    open_prs: list[dict[str, object]],
) -> FleetContext:
    """The filter-consuming preflight context — the one lane where these escalate."""
    tree_payload = {
        "tree": [{"path": path, "mode": "100644"} for path in files],
        "truncated": False,
    }
    table = {
        _TREE_ARGS: GhResult(returncode=0, stdout=json.dumps(tree_payload), stderr=""),
        _OPEN_PRS_ARGS: GhResult(returncode=0, stdout=json.dumps(open_prs), stderr=""),
    }
    for path, text in files.items():
        table[_raw_args(path=path)] = GhResult(returncode=0, stdout=text, stderr="")
    for args, payload in latest.items():
        table[args] = GhResult(returncode=0, stdout=json.dumps(payload), stderr="")

    def run(*, args: list[str], stdin: str | None = None) -> GhResult:
        del stdin
        return table.get(tuple(args), GhResult(returncode=1, stdout="", stderr="no canned"))

    runner: GhRunner = run
    return FleetContext(owner="acme", run_gh=lift_gh(runner), filter_consuming_preflight=True)


def _stale_compat_files() -> dict[str, str]:
    return {
        ".livespec.jsonc": json.dumps(
            {"impl-plugin": {"compat": {"pinned": "v1.0.0", "livespec": "v1"}}}
        )
    }


def _stale_pyproject_files() -> dict[str, str]:
    return {
        "pyproject.toml": (
            '[tool.uv.sources]\nlivespec-dev-tooling = { git = "x", tag = "v1.2.0" }\n'
        )
    }


def _finding(*, row: PinRow, ctx: FleetContext) -> RowFinding:
    outcome = row(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowFinding), outcome
    return outcome


def _compat_row() -> PinRow:
    return cast("PinRow", assert_livespec_compat_pin_currency)


def _dev_tooling_row() -> PinRow:
    return cast("PinRow", assert_dev_tooling_pin)


def test_compat_pin_persisting_gap_is_error_and_non_excluding() -> None:
    finding = _finding(
        row=_compat_row(),
        ctx=_context(
            files=_stale_compat_files(),
            latest={_LATEST_LIVESPEC_ARGS: {"tag_name": "v1.1.0"}},
            open_prs=[_bump_pr(number=7, source="livespec", tag="v1.1.0")],
        ),
    )

    assert finding.severity == "error", "the staleness classes stay loud where they escalate"
    assert finding.finding_class == PIN_STALENESS_FINDING_CLASS
    assert "persisting" in finding.message


def test_compat_pin_never_fired_past_the_window_is_error_and_non_excluding() -> None:
    finding = _finding(
        row=_compat_row(),
        ctx=_context(
            files=_stale_compat_files(),
            latest={
                _LATEST_LIVESPEC_ARGS: {
                    "tag_name": "v1.1.0",
                    "published_at": _published_past_the_window(),
                }
            },
            open_prs=[],
        ),
    )

    assert finding.severity == "error"
    assert finding.finding_class == PIN_STALENESS_FINDING_CLASS
    assert "NEVER FIRED" in finding.message


def test_dev_tooling_pin_persisting_gap_is_error_and_non_excluding() -> None:
    finding = _finding(
        row=_dev_tooling_row(),
        ctx=_context(
            files=_stale_pyproject_files(),
            latest={_LATEST_DEV_TOOLING_ARGS: {"tag_name": "v1.3.0"}},
            open_prs=[_bump_pr(number=11, source="livespec-dev-tooling", tag="v1.3.0")],
        ),
    )

    assert finding.severity == "error"
    assert finding.finding_class == PIN_STALENESS_FINDING_CLASS
    assert "persisting gap" in finding.message


def test_dev_tooling_pin_never_fired_past_the_window_is_error_and_non_excluding() -> None:
    finding = _finding(
        row=_dev_tooling_row(),
        ctx=_context(
            files=_stale_pyproject_files(),
            latest={
                _LATEST_DEV_TOOLING_ARGS: {
                    "tag_name": "v1.3.0",
                    "published_at": _published_past_the_window(),
                }
            },
            open_prs=[],
        ),
    )

    assert finding.severity == "error"
    assert finding.finding_class == PIN_STALENESS_FINDING_CLASS
    assert "NEVER FIRED" in finding.message


def test_an_absent_dev_tooling_pin_carries_no_class_and_still_excludes() -> None:
    # The CONTROL. Same row, a different leg: the pin is missing outright, which
    # is not staleness and is not curable by a dispatch — a member with no
    # `[tool.uv.sources]` entry has nothing for the bump rewrite to rewrite.
    finding = _finding(
        row=_dev_tooling_row(),
        ctx=_context(
            files={"pyproject.toml": "[project]\nname = 'widget'\n"},
            latest={_LATEST_DEV_TOOLING_ARGS: {"tag_name": "v1.3.0"}},
            open_prs=[],
        ),
    )

    assert finding.severity == "error"
    assert finding.finding_class == "", "only STALENESS is non-excluding, never the row"
