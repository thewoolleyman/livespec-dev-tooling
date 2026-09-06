"""The decision-authority row's header must agree with the obligation table.

`_rows_decision_authority.py` was authored DISARMED in `1c2aa2dd` and armed
fifty minutes later in `5cfd7595` — a commit that touched `_contract_rows.py`
and two test files, which is the correct minimal change for arming and is
precisely why the row module was not among them. So for three weeks master
carried a header opening "AUTHORED, SHIPPED DISARMED" and asserting, in
capitals, "THIS ROW IS DELIBERATELY NOT REGISTERED IN `OBLIGATION_ROWS`" while
the check ran armed in the gating aggregate. Nobody was careless: the statement
was true when written and went false without anything editing it.

`bb29e7f8` corrected the prose BY HAND and left nothing behind to keep it
correct. These pins are that missing something. They do not judge the header's
wording in the abstract — they COUPLE it to `OBLIGATION_ROWS`, comparing the
claim the module makes about itself against what the table actually holds. The
pair therefore fails in BOTH directions: a future arming that forgets the
header fails here, and so does a future DISarming that leaves the armed claim
standing.

Deliberately NOT pinned out: the header's historical narration of the
disarmed-then-armed sequence ("the row shipped DISARMED in `1c2aa2dd`"). That
ordering is the discipline the module exists to record —
`plan/rop-railway-enforcement/` carries the standing "do not arm the check
anywhere" constraint because `46c5dab` armed one early and reddened five repos
— so the detector matches only PRESENT-TENSE claims of not being registered.
"""

from __future__ import annotations

from pathlib import Path

from livespec_dev_tooling.fleet import _contract_rows, _rows_decision_authority
from livespec_dev_tooling.fleet._contract_model import RowFn
from livespec_dev_tooling.fleet._rows_decision_authority import (
    assert_decision_authority_section,
)

__all__: list[str] = []

# Widened to the table's own `RowFn` protocol so the identity comparison below
# is between two values of the SAME declared type. Compared as its concrete
# function type instead, pyright strict rules the `is` unsatisfiable
# (`reportUnnecessaryComparison`) even though it is exactly the question being
# asked — whether the table holds THIS callable.
_ROW_ASSERT: RowFn = assert_decision_authority_section

# The header's affirmative claim, normalized. Naming `OBLIGATION_ROWS` is the
# load-bearing half: "armed" alone would not tell a reader WHERE to look.
_ARMED_CLAIM = "this row is registered in `obligation_rows`"

# Present-tense assertions that the row is NOT live. Three spellings rather
# than one so a future disarming worded differently still trips the coupling
# instead of sliding past a single literal.
_DISARMED_CLAIMS: tuple[str, ...] = (
    "authored, shipped disarmed",
    "this row is deliberately not registered",
    "this row is not registered",
)

# The header exactly as `1c2aa2dd` shipped it — the first line plus the
# disarmed paragraph, verbatim. This is the text that sat on master while the
# row was armed, kept here as the control that the coupling below is not
# vacuous: a pin that cannot recognize the defect it was written for is
# decoration.
_STALE_DISARMED_HEADER = (
    "Decision-authority AGENTS.md obligation row — AUTHORED, SHIPPED DISARMED.\n"
    "\n"
    "THIS ROW IS DELIBERATELY NOT REGISTERED IN `OBLIGATION_ROWS`. Registering it\n"
    "is what ARMS it, and arming is a separate work-item that lands only after\n"
    "every governed member has adopted the section.\n"
)


def _normalized(*, text: str) -> str:
    """`text` with whitespace runs collapsed to one space, then case-folded.

    The same normalization the row's own marker test applies, and for the same
    reason: an 80-column header hard-wraps its sentences, so a claim is plainly
    present to a reader and absent to a literal substring test.
    """
    return " ".join(text.split()).casefold()


def _row_module_header() -> str:
    """The row module's docstring, normalized for substring comparison."""
    doc = _rows_decision_authority.__doc__
    assert doc is not None, "_rows_decision_authority must carry a module docstring"
    return _normalized(text=doc)


def _registered_row_ids() -> tuple[str, ...]:
    """The `OBLIGATION_ROWS` ids wired to this row's assert callable.

    Identity on the callable rather than a hardcoded row id: the question is
    whether the TABLE reaches this module's logic, so resolving it by name
    would assume the very wiring under test.
    """
    return tuple(
        row.row_id for row in _contract_rows.OBLIGATION_ROWS if row.assert_member is _ROW_ASSERT
    )


def _registration_site_filename() -> str:
    """The file name of the module that holds `OBLIGATION_ROWS`.

    Derived rather than hardcoded so the pin keeps naming the REAL site if the
    table ever moves modules.
    """
    module_file = _contract_rows.__file__
    assert module_file is not None, "_contract_rows must resolve to a file on disk"
    return Path(module_file).name


def test_the_header_arming_claim_matches_what_the_obligation_table_holds() -> None:
    header = _row_module_header()
    claims_armed = _ARMED_CLAIM in header
    claims_disarmed = tuple(claim for claim in _DISARMED_CLAIMS if claim in header) != ()
    registered_ids = _registered_row_ids()
    armed = registered_ids != ()
    assert (claims_armed, claims_disarmed) == (armed, not armed), (
        "the row module's header and the obligation table disagree about whether the "
        f"decision-authority row is live: {_registration_site_filename()} registers "
        f"{registered_ids!r}, while the header claims armed={claims_armed} and "
        f"disarmed={claims_disarmed}. Arming or disarming a row is not finished until "
        "its own module header says so — the header is the artifact a maintainer opens "
        "to ask whether a check is live, and it answered that question wrongly for "
        "three weeks (fixed by hand in bb29e7f8, which is why this pin exists)."
    )


def test_the_stale_disarmed_header_is_recognized_as_claiming_unregistered() -> None:
    # NON-VACUITY, against the real defect rather than a synthesized one: feed
    # the pin above the exact header master carried while the row was armed and
    # confirm it scores it as a disarmed claim and not an armed one. Without
    # this control, deleting `_DISARMED_CLAIMS` would leave the coupling green.
    stale = _normalized(text=_STALE_DISARMED_HEADER)
    assert _ARMED_CLAIM not in stale
    assert tuple(claim for claim in _DISARMED_CLAIMS if claim in stale) == (
        "authored, shipped disarmed",
        "this row is deliberately not registered",
    )


def test_the_header_names_the_registration_site_and_every_id_it_is_wired_to() -> None:
    header = _row_module_header()
    site = _registration_site_filename()
    assert _normalized(text=site) in header, (
        f"the header must name {site}, the module whose OBLIGATION_ROWS registers this "
        "row: a reader who learns the row is armed still has nowhere to go to verify it"
    )
    for row_id in _registered_row_ids():
        assert row_id in header, (
            f"the header must name the row id {row_id!r} the table registers this "
            "module's assert under"
        )
