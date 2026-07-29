"""A pin-currency row SKIPS when the walk cannot read the member's pin file.

`SPECIFICATION/contracts.md` §"Pin-currency severity policy": "A can't-read
never escalates. An unreadable PR list, release list, or tree keeps the row at
its lower severity or skips it (a can't-read is not a violation)."

Before livespec-dev-tooling-9sl0 converted `pin_autodiscovery.discover` to
`IOResult`, this input reached no decision at all: the read raised out of the
walk and killed the whole nine-member sweep partway through one member. A skip
is not a free pass either — a row that skips for EVERY applicable member is
BLIND, which this repo already treats as error severity.

The walk is substituted at the seam rather than provoked through a real
unreadable file, because the row materializes member bytes into a temp tree
itself: everything it writes is readable by construction, so the only honest
way to ask "what does the row do when the WALK reports unreadable" is to have
the walk report it.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from returns.io import IOFailure

from livespec_dev_tooling.cross_repo.pin_autodiscovery import PinFileUnreadable
from livespec_dev_tooling.fleet import _rows_pin_currency
from livespec_dev_tooling.fleet._context import (
    FleetContext,
    FleetMember,
    GhResult,
    GhRunner,
    RowSkip,
)

if TYPE_CHECKING:
    import pytest

__all__: list[str] = []


_MEMBER = FleetMember(repo="widget", repo_class="impl-plugin")
_TREE_ARGS: tuple[str, ...] = ("api", "repos/acme/widget/git/trees/master?recursive=1")
_UNREADABLE = PinFileUnreadable(
    pin_walk="walk_livespec_jsonc",
    file_path="/tmp/materialized/.livespec.jsonc",
    detail="[Errno 13] Permission denied",
)


def _context() -> FleetContext:
    tree = {"tree": [{"path": ".livespec.jsonc", "mode": "100644"}], "truncated": False}
    table = {_TREE_ARGS: GhResult(returncode=0, stdout=json.dumps(tree), stderr="")}

    def run(*, args: list[str], stdin: str | None = None) -> GhResult:
        del stdin
        return table.get(tuple(args), GhResult(returncode=1, stdout="", stderr="no canned"))

    runner: GhRunner = run
    return FleetContext(owner="acme", run_gh=runner)


def test_an_unreadable_pin_file_skips_the_row_and_names_the_file(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The skip carries the file AND the cause, not just "unreadable".

    Both are asserted because the operator reading this is looking at a
    central sweep over nine repos: a skip naming neither the member's file
    nor why it could not be read is a row they cannot act on, and it would
    still satisfy an `isinstance(outcome, RowSkip)` assertion by itself.
    """
    monkeypatch.setattr(_rows_pin_currency, "discover", lambda **_kwargs: IOFailure(_UNREADABLE))

    outcome = _rows_pin_currency.assert_livespec_compat_pin_currency(ctx=_context(), member=_MEMBER)

    assert (
        isinstance(outcome, RowSkip)
        and _UNREADABLE.file_path in outcome.reason
        and _UNREADABLE.detail in outcome.reason
    )
