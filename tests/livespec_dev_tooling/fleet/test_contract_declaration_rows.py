"""Tests for `livespec_dev_tooling/fleet/_contract_declaration_rows.py`.

The pyproject-declaration slice was extracted from `_contract_rows.py` so the
central table could accept the `worktree-pack-wired` row without crossing the
250-LLOC hard ceiling (livespec-dev-tooling-lptplj). An extraction like that
has one failure mode worth pinning, the same one its github-state sibling
pins: the slice and the table drifting apart afterwards — a declaration row
registered directly in `_contract_rows.py`, or the splice moving and silently
reordering the table two engines walk. Both are asserted against
`OBLIGATION_ROWS` itself rather than against a restatement of it.
"""

from __future__ import annotations

from livespec_dev_tooling.fleet._contract_declaration_rows import DECLARATION_ROWS
from livespec_dev_tooling.fleet._contract_model import CENTRAL_VANTAGE
from livespec_dev_tooling.fleet._contract_rows import OBLIGATION_ROWS, REPO_CLASSES

__all__: list[str] = []


def test_slice_is_spliced_contiguously_and_in_order() -> None:
    # `OBLIGATION_ROWS` content AND ordering had to survive the move
    # unchanged — `wire_fleet_member` reconciles in table order, so a
    # reordering is a behavior change wearing a refactor's clothes.
    row_ids = [row.row_id for row in OBLIGATION_ROWS]
    slice_ids = [row.row_id for row in DECLARATION_ROWS]
    start = row_ids.index(slice_ids[0])
    assert row_ids[start : start + len(slice_ids)] == slice_ids


def test_slice_holds_the_whole_declaration_family() -> None:
    # A partial slice is the drift that matters here: the module's name
    # promises "the pyproject declaration rows", and a reader looking for one
    # of them must not find it registered somewhere else instead.
    assert [row.row_id for row in DECLARATION_ROWS] == [
        "required-role-keys-declared",
        "role-key-spellings",
        "cross-repo-public-api-declared",
    ]


def test_every_slice_row_is_universal_manual_only_and_hinted() -> None:
    # What a verbatim move is most likely to lose is the defaulted fields: a
    # declaration is a decision only the member's maintainer can make, so
    # every row here stays manual-only, universal by class, and on the plain
    # central vantage — and each must name its manual fix.
    for row in DECLARATION_ROWS:
        assert row.obligation_type == "committed-file", row.row_id
        assert row.applies_to == frozenset(REPO_CLASSES), row.row_id
        assert row.reconcile is None, row.row_id
        assert row.manual_hint, row.row_id
        assert row.vantage == CENTRAL_VANTAGE, row.row_id
