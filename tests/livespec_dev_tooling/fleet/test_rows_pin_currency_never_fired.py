"""Tests for the NEVER-FIRED staleness class and its ratified settle window.

`SPECIFICATION/contracts.md` section "Pin-currency severity policy" (v039)
partitions a STALE pin into exactly two classes and calls the partition
EXHAUSTIVE. The sibling suites cover the FIRED-AND-COULD-NOT-LAND half
(`test_rows_pin_currency_persisting.py`) and the run that established
neither class (`test_bump_pr_list_undecidable.py`). This one covers the
half that had no code at all until now: stale with NO bump PR open, which
escalates once the latest release has aged past a TWO-HOUR settle window
read from `published_at` on the `releases/latest` payload both readers
already fetch for `tag_name`.

BOTH persisting-gap sites are exercised INDEPENDENTLY here — the three
pin-format rows in `_rows_pin_currency` and the `dev-tooling-pin` row's
staleness leg in `_rows_files` — because a half-armed promotion is the
hazard `_rows_files`'s own "both persisting-gap sites must move together"
comment warns about, and a suite that drives only one site cannot see it.
"""

from __future__ import annotations

import importlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Protocol, cast

from _gh_railway import lift_gh

from livespec_dev_tooling.fleet._context import (
    FleetContext,
    FleetMember,
    GhResult,
    GhRunner,
    RowFinding,
)
from livespec_dev_tooling.fleet._settle_window import never_fired_class

__all__: list[str] = []


_MEMBER = FleetMember(repo="widget", repo_class="impl-plugin")
_TREE_ARGS: tuple[str, ...] = ("api", "repos/acme/widget/git/trees/master?recursive=1")
_LATEST_LIVESPEC_ARGS: tuple[str, ...] = ("api", "repos/acme/livespec/releases/latest")
_LATEST_DEV_TOOLING_ARGS: tuple[str, ...] = (
    "api",
    "repos/acme/livespec-dev-tooling/releases/latest",
)
_OPEN_PRS_ARGS: tuple[str, ...] = ("api", "repos/acme/widget/pulls?state=open&per_page=100")

# Comfortably outside and comfortably inside the ratified two-hour window,
# so neither case rests on a boundary a leap second could cross.
_PAST_THE_WINDOW = timedelta(hours=3, minutes=14)
_INSIDE_THE_WINDOW = timedelta(minutes=30)


class PinRow(Protocol):
    """One obligation row assertion."""

    def __call__(self, *, ctx: FleetContext, member: FleetMember) -> object: ...


def _module(*, name: str) -> object:
    module_path = (
        Path(__file__).resolve().parents[3] / "livespec_dev_tooling" / "fleet" / f"{name}.py"
    )
    assert module_path.is_file()
    return importlib.import_module(f"livespec_dev_tooling.fleet.{name}")


def _stamp(*, age: timedelta) -> str:
    """A `published_at` exactly `age` old, in GitHub's `Z`-suffixed spelling."""
    return (datetime.now(tz=timezone.utc) - age).strftime("%Y-%m-%dT%H:%M:%SZ")


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
    preflight: bool = True,
    calls: list[tuple[str, ...]] | None = None,
) -> FleetContext:
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
        if calls is not None:
            calls.append(tuple(args))
        return table.get(tuple(args), GhResult(returncode=1, stdout="", stderr="no canned"))

    runner: GhRunner = run
    return FleetContext(owner="acme", run_gh=lift_gh(runner), filter_consuming_preflight=preflight)


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


def _compat_row() -> PinRow:
    return cast("PinRow", _module(name="_rows_pin_currency").assert_livespec_compat_pin_currency)


def _dev_tooling_row() -> PinRow:
    return cast("PinRow", _module(name="_rows_files").assert_dev_tooling_pin)


def _compat_outcome(
    *,
    published_at: dict[str, object],
    preflight: bool = True,
    open_prs: list[dict[str, object]] | None = None,
) -> RowFinding:
    ctx = _context(
        files=_stale_compat_files(),
        latest={_LATEST_LIVESPEC_ARGS: {"tag_name": "v1.1.0", **published_at}},
        open_prs=[] if open_prs is None else open_prs,
        preflight=preflight,
    )
    outcome = _compat_row()(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowFinding)
    return outcome


def _dev_tooling_outcome(*, published_at: dict[str, object], preflight: bool = True) -> RowFinding:
    ctx = _context(
        files=_stale_pyproject_files(),
        latest={_LATEST_DEV_TOOLING_ARGS: {"tag_name": "v1.3.0", **published_at}},
        open_prs=[],
        preflight=preflight,
    )
    outcome = _dev_tooling_row()(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowFinding)
    return outcome


def test_never_fired_past_the_settle_window_escalates_in_the_fanout_preflight() -> None:
    """The state both fan-out outages ran in, which no severity could reach before."""
    outcome = _compat_outcome(published_at={"published_at": _stamp(age=_PAST_THE_WINDOW)})

    assert outcome.severity == "error"
    assert "NEVER FIRED" in outcome.message
    assert "no bump PR for the latest release is open" in outcome.message
    assert "3h14m ago" in outcome.message
    assert "2h settle window" in outcome.message


def test_never_fired_past_the_settle_window_keeps_its_diagnostic_in_per_pr_ci() -> None:
    """Scoping lowers the SEVERITY; the contract forbids it changing the message."""
    stamp = _stamp(age=_PAST_THE_WINDOW)

    preflight = _compat_outcome(published_at={"published_at": stamp}, preflight=True)
    per_pr_ci = _compat_outcome(published_at={"published_at": stamp}, preflight=False)

    assert preflight.severity == "error"
    assert per_pr_ci.severity == "warning"
    assert per_pr_ci.message == preflight.message


def test_never_fired_inside_the_settle_window_stays_a_warning() -> None:
    """The interval between a release publishing and its bump PR opening is normal."""
    outcome = _compat_outcome(published_at={"published_at": _stamp(age=_INSIDE_THE_WINDOW)})

    assert outcome.severity == "warning"
    assert "NEVER FIRED" in outcome.message
    assert "0h30m ago" in outcome.message


def test_an_absent_published_at_never_escalates() -> None:
    """A can't-READ is not a violation (livespec-dev-tooling-6ge)."""
    outcome = _compat_outcome(published_at={})

    assert outcome.severity == "warning"
    assert "publish time is unreadable" in outcome.message


def test_a_malformed_published_at_never_escalates() -> None:
    outcome = _compat_outcome(published_at={"published_at": "the day before yesterday"})

    assert outcome.severity == "warning"
    assert "publish time is unreadable" in outcome.message


def test_a_timezone_less_published_at_never_escalates() -> None:
    """Assuming UTC would shift the window by the offset it guessed."""
    outcome = _compat_outcome(published_at={"published_at": "2026-07-30T10:00:00"})

    assert outcome.severity == "warning"
    assert "publish time is unreadable" in outcome.message


def test_a_non_string_published_at_never_escalates() -> None:
    outcome = _compat_outcome(published_at={"published_at": 1753876800})

    assert outcome.severity == "warning"
    assert "publish time is unreadable" in outcome.message


def test_dev_tooling_pin_never_fired_past_the_settle_window_escalates() -> None:
    """The SECOND persisting-gap site, driven independently of the first."""
    outcome = _dev_tooling_outcome(published_at={"published_at": _stamp(age=_PAST_THE_WINDOW)})

    assert outcome.severity == "error"
    assert "dev-tooling pin v1.2.0 is stale" in outcome.message
    assert "NEVER FIRED" in outcome.message
    assert "3h14m ago" in outcome.message


def test_dev_tooling_pin_never_fired_inside_the_settle_window_stays_a_warning() -> None:
    outcome = _dev_tooling_outcome(published_at={"published_at": _stamp(age=_INSIDE_THE_WINDOW)})

    assert outcome.severity == "warning"
    assert "NEVER FIRED" in outcome.message


def test_dev_tooling_pin_never_fired_past_the_window_stays_a_warning_in_per_pr_ci() -> None:
    outcome = _dev_tooling_outcome(
        published_at={"published_at": _stamp(age=_PAST_THE_WINDOW)}, preflight=False
    )

    assert outcome.severity == "warning"


def test_dev_tooling_pin_absent_published_at_never_escalates() -> None:
    outcome = _dev_tooling_outcome(published_at={})

    assert outcome.severity == "warning"
    assert "publish time is unreadable" in outcome.message


def test_both_staleness_classes_name_themselves_in_the_diagnostic() -> None:
    """Each class is told apart by the message, not only by the severity."""
    fired = _compat_outcome(
        published_at={"published_at": _stamp(age=_PAST_THE_WINDOW)},
        open_prs=[_bump_pr(number=7, source="livespec", tag="v1.1.0")],
    )
    never_fired = _compat_outcome(published_at={"published_at": _stamp(age=_PAST_THE_WINDOW)})

    assert "persisting gap" in fired.message
    assert "open bump PR #7" in fired.message
    assert "NEVER FIRED" not in fired.message
    assert "NEVER FIRED" in never_fired.message
    assert "no bump PR for the latest release is open" in never_fired.message
    assert "open bump PR #" not in never_fired.message


def test_reading_published_at_adds_no_api_call() -> None:
    """The window comes off a payload already in hand — never a second request."""
    without: list[tuple[str, ...]] = []
    with_stamp: list[tuple[str, ...]] = []

    _compat_row()(
        ctx=_context(
            files=_stale_compat_files(),
            latest={_LATEST_LIVESPEC_ARGS: {"tag_name": "v1.1.0"}},
            open_prs=[],
            calls=without,
        ),
        member=_MEMBER,
    )
    _compat_row()(
        ctx=_context(
            files=_stale_compat_files(),
            latest={
                _LATEST_LIVESPEC_ARGS: {
                    "tag_name": "v1.1.0",
                    "published_at": _stamp(age=_PAST_THE_WINDOW),
                }
            },
            open_prs=[],
            calls=with_stamp,
        ),
        member=_MEMBER,
    )

    assert with_stamp == without
    assert with_stamp.count(_LATEST_LIVESPEC_ARGS) == 1


def test_the_settle_window_predicate_is_stateless() -> None:
    """One payload, two wall-clock readings, one verdict.

    The window is measured from the RELEASE's own publish time, never from
    a local clock reading of when staleness was first observed and never
    from stored history — which is what lets per-PR CI, the scheduled
    sweep, and the fan-out preflight agree without sharing anything.
    """
    published_at = _stamp(age=timedelta(days=4))
    now = datetime.now(tz=timezone.utc)

    first = never_fired_class(published_at=published_at, now=now)
    second = never_fired_class(published_at=published_at, now=now + timedelta(minutes=37))

    assert first.escalates is True
    assert second.escalates == first.escalates
