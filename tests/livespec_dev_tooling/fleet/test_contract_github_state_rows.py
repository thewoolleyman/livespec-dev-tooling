"""Tests for `livespec_dev_tooling/fleet/_contract_github_state_rows.py`.

The github-state slice was extracted from `_contract_rows.py` so the
central table could accept new rows again (livespec-dev-tooling-oitd).
An extraction like that has exactly one failure mode worth pinning: the
slice and the table drifting apart afterwards — a row added directly to
`_contract_rows.py`, or the splice moving and silently reordering the
table two engines walk. Both are asserted here against `OBLIGATION_ROWS`
itself rather than against a restatement of it.
"""

from __future__ import annotations

from livespec_dev_tooling.fleet._contract_github_state_rows import GITHUB_STATE_ROWS
from livespec_dev_tooling.fleet._contract_model import (
    ADMIN_VANTAGE,
    CENTRAL_APP_VANTAGE,
    CENTRAL_VANTAGE,
)
from livespec_dev_tooling.fleet._contract_rows import OBLIGATION_ROWS, REPO_CLASSES

__all__: list[str] = []


def test_slice_holds_every_github_state_row_and_nothing_else() -> None:
    # The extraction is only honest while the partition holds: a
    # `github-state` row registered directly in `_contract_rows.py` would
    # leave this module a partial slice whose name overclaims, and the
    # next reader looking for "the GitHub rows" would find some of them.
    in_table = tuple(row for row in OBLIGATION_ROWS if row.obligation_type == "github-state")
    assert in_table == GITHUB_STATE_ROWS


def test_slice_is_spliced_contiguously_and_in_order() -> None:
    # `OBLIGATION_ROWS` content AND ordering had to survive the move
    # unchanged — `wire_fleet_member` reconciles in table order, so a
    # reordering is a behavior change wearing a refactor's clothes.
    row_ids = [row.row_id for row in OBLIGATION_ROWS]
    slice_ids = [row.row_id for row in GITHUB_STATE_ROWS]
    start = row_ids.index(slice_ids[0])
    assert row_ids[start : start + len(slice_ids)] == slice_ids


def test_every_slice_row_is_universal_and_reconcilable_or_hinted() -> None:
    # Repo state on GitHub applies to every class by construction (no
    # `applies_to` argument is even offered), and the two engines require
    # each row to be either machine-fixable or to name its manual fix.
    for row in GITHUB_STATE_ROWS:
        assert row.applies_to == frozenset(REPO_CLASSES), row.row_id
        assert row.reconcile is not None or row.manual_hint, row.row_id


def test_declared_vantages_survived_the_move() -> None:
    # The three vantages are the part of a row a verbatim move is most
    # likely to lose, because they are defaulted: dropping one silently
    # re-homes an admin-token read into the plain central lane, which
    # reports blind instead of out-of-vantage.
    vantages = {row.row_id: row.vantage for row in GITHUB_STATE_ROWS}
    assert vantages["secret-names"] == ADMIN_VANTAGE
    assert vantages["branch-protection"] == ADMIN_VANTAGE
    assert vantages["app-installation"] == CENTRAL_APP_VANTAGE
    assert vantages["merge-settings"] == CENTRAL_VANTAGE
    assert vantages["delete-branch-on-merge"] == CENTRAL_VANTAGE
    assert vantages["topic-livespec-sibling"] == CENTRAL_VANTAGE
