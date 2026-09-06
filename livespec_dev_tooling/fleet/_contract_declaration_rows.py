"""The pyproject-declaration slice of the central obligation table.

Extracted VERBATIM from `_contract_rows.py`, for the same reason and by the
same mechanism as the github-state slice beside it
(`_contract_github_state_rows.py`, livespec-dev-tooling-oitd): registering the
`worktree-pack-wired` row took that module from 248 to 262 LLOC, past this
repo's 250-LLOC hard ceiling, and a table that cannot accept a row is an
obligation that cannot be enforced.

WHY THESE THREE ROWS ARE THE SLICE. They are the family the code already
named: the comments moved with them call the second "the sibling of the row
above" and the third "the third member of that family". All three assert what
a member DECLARED in its own `pyproject.toml` `[tool.livespec_dev_tooling]`
block — that the required role keys are present, that they use a blessed
spelling, and that the cross-repo public-API surface names every function a
sibling actually imports. The cut is along that seam rather than at a
convenient line number, and it takes the whole family, so "the pyproject
declaration rows" is a complete answer wherever a reader looks for it.

`_contract_rows.py` splices `DECLARATION_ROWS` into `OBLIGATION_ROWS` at the
position these rows already occupied, so the exported table's content AND
ordering are unchanged by the move — `wire_fleet_member` reconciles in table
order, so a reordering would be a behavior change wearing a refactor's
clothes.

The row FUNCTIONS these entries reference stay where they were
(`_rows_required_role_keys.py`, `_rows_role_key_spellings.py`,
`_rows_public_api_conformance.py`); this module holds only their TABLE
REGISTRATION.
"""

from __future__ import annotations

from livespec_dev_tooling.fleet._contract_classes import ALL_CLASSES
from livespec_dev_tooling.fleet._contract_model import ObligationRow, RowFn
from livespec_dev_tooling.fleet._rows_public_api_conformance import (
    assert_cross_repo_public_api_declared,
)
from livespec_dev_tooling.fleet._rows_required_role_keys import (
    assert_required_role_keys_declared,
)
from livespec_dev_tooling.fleet._rows_role_key_spellings import (
    assert_role_key_spellings_conformant,
)

__all__: list[str] = [
    "DECLARATION_ROWS",
]


def _declaration_row(*, row_id: str, assert_member: RowFn, manual_hint: str) -> ObligationRow:
    """One manual-only committed-file declaration row, universal by class.

    The slice's own constructor, mirroring `_contract_github_state_rows`'s
    `_github_state_row`: a slice module carries the shape ITS rows share
    rather than importing the parent's private helper, which no module may do.
    Every row here is manual-only by nature — a declaration states a decision
    only the member's maintainer can make, so there is nothing to reconcile
    from the central vantage and no `reconcile` argument is offered.
    """
    return ObligationRow(
        row_id=row_id,
        obligation_type="committed-file",
        applies_to=ALL_CLASSES,
        assert_member=assert_member,
        manual_hint=manual_hint,
    )


DECLARATION_ROWS: tuple[ObligationRow, ...] = (
    _declaration_row(
        row_id="required-role-keys-declared",
        assert_member=assert_required_role_keys_declared,
        manual_hint=(
            "declare every REQUIRED_ROLE_KEYS entry in [tool.livespec_dev_tooling], or "
            "declare sanctioned-empty values with comments explaining the absent role"
        ),
    ),
    # The sibling of the row above: that one asserts the required keys are
    # DECLARED, this one asserts the declaration uses a blessed SPELLING. A key
    # declared `[]` satisfies the first and is exactly the ambiguity the second
    # exists to reject (livespec-dev-tooling-8o8e.1 Phase 3).
    _declaration_row(
        row_id="role-key-spellings",
        assert_member=assert_role_key_spellings_conformant,
        manual_hint=(
            "replace the retired ambiguous empty spelling on the named union role key(s) "
            "with a populated value, or with one blessed declared-absent spelling carrying "
            "a non-empty payload"
        ),
    ),
    # The third member of that family, and the only one needing the CENTRAL
    # vantage to answer at all: the two rows above ask whether a member's own
    # declaration is PRESENT and WELL-SPELLED, this one asks whether it is
    # TRUE — measured against what the other eight members actually import. A
    # repo-local check structurally cannot see a sibling's import, which is
    # what let `parse_manifest` be converted on a repo-local reading that found
    # no importer while a sibling's hook turned that repo's master red within
    # minutes (livespec-dev-tooling-dx8l).
    _declaration_row(
        row_id="cross-repo-public-api-declared",
        assert_member=assert_cross_repo_public_api_declared,
        manual_hint=(
            "add each named function to `cross_repo_public_api` in "
            "[tool.livespec_dev_tooling], one entry per function with a written reason "
            "naming the consuming member and file; do NOT omit a genuinely consumed name "
            "to keep the count down, and do NOT bulk-fill the key without reading each "
            "consumption site's guard first"
        ),
    ),
)
