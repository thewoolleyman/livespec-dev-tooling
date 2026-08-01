"""Green-leg edges for the local lane's excluded-pass rendering.

A separate file from `test_rowskip_two_meanings.py` because that one is
byte-identity-bound to its Red commit and cannot be amended.

WHAT IS UNREACHED WITHOUT IT. `_already_settled` gains an arm for an ASSERT
leg returning an excluded pass. No local row's `assert_local` returns one
today — only the reconcile legs do — so the arm is real code that the composed
verb cannot currently exercise. That is the recurring shape: every converted
call site adds a line no existing test reaches, and exercising it at its OWN
seam is what keeps the branch honest rather than waiting for a caller that
does not exist yet.

⛔ AND THE DISTINCTION IS THE WHOLE POINT OF THE CHANGE: an excluded pass must
narrate "row not applicable", NOT "row already satisfied". Both settle the row
and skip the reconcile, so a test asserting only the return value would pass
either way — the local lane would go on claiming it had satisfied a row that
never applied to this checkout.
"""

from __future__ import annotations

from livespec_dev_tooling.fleet._context import (
    EXCLUDED_NOTE_PREFIX,
    RowFinding,
    RowPass,
    RowSkip,
    row_excluded,
)
from livespec_dev_tooling.fleet.local_reconcile import _already_settled

__all__: list[str] = []


class _CapturingLog:
    """Records narration so "not applicable" and "already satisfied" differ.

    `info` ALONE, deliberately: `_already_settled` narrates at info severity or
    stays silent, so `warning`/`error` stubs would be dead lines here — and
    per-file coverage counts test files at the same 100% bar.
    """

    def __init__(self) -> None:
        self.events: list[tuple[str, str]] = []

    def info(self, event: str, **_kwargs: object) -> None:
        self.events.append(("info", event))


def test_assert_leg_excluded_pass_narrates_not_applicable() -> None:
    log = _CapturingLog()

    settled = _already_settled(
        outcome=row_excluded(reason="no .beads tenant directory"),
        row_id="demo-row",
        log=log,  # pyright: ignore[reportArgumentType]
    )

    assert settled is True
    assert log.events == [("info", "row not applicable")], (
        "an excluded pass must NOT narrate 'row already satisfied' — the lane "
        "would claim it satisfied a row that never applied here"
    )


def test_assert_leg_plain_pass_narrates_already_satisfied() -> None:
    """The positive control: a genuine pass must keep its own narration."""
    log = _CapturingLog()

    settled = _already_settled(
        outcome=RowPass(note="hook installed"),
        row_id="demo-row",
        log=log,  # pyright: ignore[reportArgumentType]
    )

    assert settled is True
    assert log.events == [("info", "row already satisfied")]


def test_assert_leg_finding_and_skip_do_not_settle_the_row() -> None:
    log = _CapturingLog()

    assert (
        _already_settled(
            outcome=RowFinding(message="unmet"),
            row_id="demo-row",
            log=log,  # pyright: ignore[reportArgumentType]
        )
        is False
    )
    assert (
        _already_settled(
            outcome=RowSkip(reason="could not read"),
            row_id="demo-row",
            log=log,  # pyright: ignore[reportArgumentType]
        )
        is False
    )
    assert log.events == [], "neither arm narrates; the reconcile leg speaks next"


def test_excluded_note_prefix_round_trips_through_the_constructor() -> None:
    """`row_excluded` is the ONE spelling both lanes read."""
    outcome = row_excluded(reason="not a beads-backed repo")
    assert outcome.note.startswith(EXCLUDED_NOTE_PREFIX)
    assert outcome.note.removeprefix(EXCLUDED_NOTE_PREFIX) == "not a beads-backed repo"
