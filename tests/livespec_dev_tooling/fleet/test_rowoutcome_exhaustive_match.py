"""Pins the two things the `isinstance` → `match` conversion could silently break.

The conversion discharging v181 condition 2 is behavior-preserving, so the
existing suite already covers what each arm DOES. What it did not cover is the
two places where a `match` is not merely a restatement of the chain it replaced:

1. **A bare name in a pattern is a CAPTURE, not a value comparison.** Writing
   `case RowSkip(reason=_WRAPPER_VERIFICATION_REQUIRED)` binds the constant's
   NAME to the reason and matches EVERY skip — routing an unreadable settings
   read into the justfile fallback, which manufactures a definitive verdict
   from a read that never happened. It reads exactly like the value test it is
   not, which is why it needs a test rather than care.

2. **`_fold_member_outcome` folds three variants into three different
   tallies.** It is new surface, extracted when the exhaustive match pushed
   `run_member_rows` past PLR0915's statement cap. An arm crediting the wrong
   counter would leave the sweep's arithmetic wrong while every row function
   stayed correct — and the blind-row error is computed from exactly those
   counters.

⛔ The capture-pattern test discriminates by OUTCOME, and the fixture is built
so the two paths cannot agree: the justfile IS the standard wrapper, so a
fall-through would return `RowPass` while the correct guard returns `RowSkip`.
Asserting merely "some skip came back" would pass under the bug, since both
paths can produce a skip — the sibling-assertion trap this thread has paid for
twice.
"""

from __future__ import annotations

import json

from test_rows_claude_plugin import _PLUGIN_JUSTFILE_ARGS, _PLUGIN_SETTINGS_ARGS, _STANDARD_JUSTFILE
from test_rows_files import _MEMBER, make_context, tree_table

from livespec_dev_tooling.fleet._context import GhResult, RowFinding, RowPass, RowSkip
from livespec_dev_tooling.fleet._contract_model import ObligationRow
from livespec_dev_tooling.fleet._lanes import _fold_member_outcome, _LaneTallies
from livespec_dev_tooling.fleet._rows_claude_plugin import (
    CLAUDE_SETTINGS,
    assert_claude_plugin_currency,
)

__all__: list[str] = []


def _row() -> ObligationRow:
    """A minimal obligation row; the fold reads `row_id` and `manual_hint` only.

    `assert_member` is a REAL row function rather than a stub. The fold takes
    an already-computed outcome and never calls it, so a hand-written stand-in
    would be dead lines in this file — and `check-per-file-coverage` counts
    TEST files at the same 100% bar, which is how a deliberately-never-called
    helper has already cost this repo a rebuilt commit pair.
    """
    return ObligationRow(
        row_id="demo-row",
        obligation_type="committed-file",
        applies_to=frozenset({"impl-plugin"}),
        assert_member=assert_claude_plugin_currency,
        manual_hint="demo hint",
    )


def _tallies() -> _LaneTallies:
    return _LaneTallies(evaluated={}, skips={}, failing_rows=[])


class _CapturingLog:
    """Records the structlog calls the fold makes, so arms stay distinguishable."""

    def __init__(self) -> None:
        self.events: list[tuple[str, str]] = []

    def info(self, event: str, **_kwargs: object) -> None:
        self.events.append(("info", event))

    def warning(self, event: str, **_kwargs: object) -> None:
        self.events.append(("warning", event))

    def error(self, event: str, **_kwargs: object) -> None:
        self.events.append(("error", event))


def test_fold_counts_a_skip_as_blind_evidence_and_never_as_evaluated() -> None:
    tallies = _tallies()
    log = _CapturingLog()

    delta = _fold_member_outcome(
        outcome=RowSkip(reason="widget: tree unreadable"),
        row=_row(),
        member_repo="widget",
        tallies=tallies,
        log=log,  # pyright: ignore[reportArgumentType]
    )

    assert delta == 0
    assert tallies.evaluated == {}, "a can't-read must never count as evaluated"
    assert tallies.skips == {"demo-row": ["tree unreadable"]}
    assert tallies.failing_rows == []


def test_fold_counts_a_pass_as_evaluated_with_no_error() -> None:
    tallies = _tallies()
    log = _CapturingLog()

    delta = _fold_member_outcome(
        outcome=RowPass(),
        row=_row(),
        member_repo="widget",
        tallies=tallies,
        log=log,  # pyright: ignore[reportArgumentType]
    )

    assert delta == 0
    assert tallies.evaluated == {"demo-row": 1}
    assert tallies.skips == {}
    assert tallies.failing_rows == []


def test_fold_counts_an_error_finding_as_evaluated_and_failing() -> None:
    tallies = _tallies()
    log = _CapturingLog()

    delta = _fold_member_outcome(
        outcome=RowFinding(message="widget: broken"),
        row=_row(),
        member_repo="widget",
        tallies=tallies,
        log=log,  # pyright: ignore[reportArgumentType]
    )

    assert delta == 1
    assert tallies.evaluated == {"demo-row": 1}
    assert tallies.failing_rows == ["demo-row"]
    assert ("error", "fleet obligation violated") in log.events


def test_fold_counts_a_warning_finding_as_evaluated_but_not_failing() -> None:
    tallies = _tallies()
    log = _CapturingLog()

    delta = _fold_member_outcome(
        outcome=RowFinding(message="widget: soft", severity="warning"),
        row=_row(),
        member_repo="widget",
        tallies=tallies,
        log=log,  # pyright: ignore[reportArgumentType]
    )

    assert delta == 0, "a warning finding must not move the error count"
    assert tallies.evaluated == {"demo-row": 1}
    assert tallies.failing_rows == []
    assert ("warning", "fleet obligation warning") in log.events


def test_unreadable_settings_skip_does_not_fall_through_to_the_justfile() -> None:
    """THE CAPTURE-PATTERN GUARD.

    `.claude/settings.json` is in the tree but its contents read FAILS, so the
    settings leg yields a skip whose reason is NOT the wrapper-verification
    sentinel. The justfile IS canned as the standard wrapper, so a capture
    pattern — which matches every skip — would reach it and return `RowPass`.
    The correct guard never consults it and the skip survives.
    """
    table = tree_table(paths=[CLAUDE_SETTINGS, "justfile"])
    # present in the tree, unreadable in contents: the can't-read skip
    table[_PLUGIN_SETTINGS_ARGS] = GhResult(returncode=1, stdout="", stderr="unreadable")
    # a justfile that WOULD pass, so a fall-through is visible as RowPass
    table[_PLUGIN_JUSTFILE_ARGS] = GhResult(returncode=0, stdout=_STANDARD_JUSTFILE, stderr="")
    ctx = make_context(table=table)

    outcome = assert_claude_plugin_currency(ctx=ctx, member=_MEMBER)

    assert isinstance(outcome, RowSkip), (
        "an unreadable settings read must NOT fall through to the justfile probe; "
        "a bare name in a match pattern captures instead of comparing, which "
        "would route every skip there and pass on a read that never happened"
    )
    assert "unreadable" in outcome.reason


def test_wrapper_verification_sentinel_still_reaches_the_justfile() -> None:
    """The POSITIVE CONTROL for the guard: the sentinel skip must still route.

    Without this, a guard that never matches — the opposite mistake — would
    satisfy the test above while breaking the fallback entirely.
    """
    settings = json.dumps(
        {
            "hooks": {
                "SessionStart": [
                    {
                        "matcher": "",
                        "hooks": [
                            {"type": "command", "command": "mise exec -- just ensure-plugins"}
                        ],
                    }
                ]
            }
        }
    )
    table = tree_table(paths=[CLAUDE_SETTINGS, "justfile"])
    table[_PLUGIN_SETTINGS_ARGS] = GhResult(returncode=0, stdout=settings, stderr="")
    table[_PLUGIN_JUSTFILE_ARGS] = GhResult(returncode=0, stdout=_STANDARD_JUSTFILE, stderr="")
    ctx = make_context(table=table)

    assert assert_claude_plugin_currency(ctx=ctx, member=_MEMBER) == RowPass()
