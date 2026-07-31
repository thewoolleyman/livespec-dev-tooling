"""An UNPARSEABLE pin file is a FINDING, never a passing row.

`livespec-dev-tooling-2j2l`, closed by this module's subject. Ratified as
spec v039 — `SPECIFICATION/contracts.md` §"Pin autodiscovery rules": a
known-format file the walk cannot PARSE "MUST be surfaced as a DISTINCT,
typed outcome that a consumer CANNOT silently drop" and "MUST NOT be
carried as an in-band record in the walk's normal record stream"; and
§"Pin-currency severity policy": "A can't-PARSE is NOT a can't-read, and
is NEVER a pass."

THE DEFECT THIS PINS, because it is the reason the assertions below look
redundant and are not. The walk used to emit a record with
`pin_format="unrecognized"` for a file it read and could not parse.
`fleet/_rows_pin_currency._records_for` filters the walk's records by
`pin_format` equality; `"unrecognized"` matched no spec, so the record
was SILENTLY DROPPED. Zero records then reached the staleness
comparison, and "no stale pins" rendered as `RowPass()`. A member with a
truncated `.livespec.jsonc` and a member with NO `.livespec.jsonc` at
all were indistinguishable at the row — both green.

So the two assertions are at DIFFERENT layers on purpose:

- the walk must not return the can't-parse as a SUCCESS value, because a
  success value is exactly what a record filter discards without a
  decision;
- the row must not render it as a PASS, which is the observable the
  fleet sweep actually reports.

Testing only the walk would leave the drop intact one layer up — the
"MOVING the sentinel, not removing it" shortcut this epic refuses by
name. Testing only the row would let a future walk re-introduce an
in-band sentinel that some other consumer drops again.

Neither assertion names `PinFileUnparseable`. That is deliberate: the
type is the mechanism, and pinning the OBSERVABLE (not a success / not a
pass) keeps the test honest if the failure type is ever renamed or
merged, while still failing loudly on the defect itself.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from returns.io import IOSuccess

from livespec_dev_tooling.cross_repo.pin_autodiscovery import discover
from livespec_dev_tooling.fleet import _rows_pin_currency
from livespec_dev_tooling.fleet._context import (
    FleetContext,
    FleetMember,
    GhOutcome,
    GhResult,
    GhRunner,
    RowPass,
)

if TYPE_CHECKING:
    pass

__all__: list[str] = []


_MEMBER = FleetMember(repo="widget", repo_class="impl-plugin")
# Truncated mid-object: `jsoncomment.loads` raises, which is precisely the
# input that used to become an `unrecognized` record.
_TRUNCATED = '{ "widget": { "compat": { "pinned": "v1.0.0",'


def _context() -> FleetContext:
    tree = {"tree": [{"path": ".livespec.jsonc", "mode": "100644"}], "truncated": False}
    table: dict[tuple[str, ...], GhResult] = {
        ("api", "repos/acme/widget/git/trees/master?recursive=1"): GhResult(
            returncode=0, stdout=json.dumps(tree), stderr=""
        ),
        (
            "api",
            "repos/acme/widget/contents/.livespec.jsonc?ref=master",
            "-H",
            "Accept: application/vnd.github.raw",
        ): GhResult(returncode=0, stdout=_TRUNCATED, stderr=""),
    }

    def run(*, args: list[str], stdin: str | None = None) -> GhResult:
        del stdin
        return table.get(tuple(args), GhResult(returncode=1, stdout="", stderr="no canned"))

    runner: GhRunner = run

    def lifted(*, args: list[str], stdin: str | None = None) -> GhOutcome:
        # Lifted inline: `_gh_railway` sits in the FLEET test directory,
        # which only that package's conftest puts on `sys.path`.
        return IOSuccess(runner(args=args, stdin=stdin))

    return FleetContext(owner="acme", run_gh=lifted)


def test_walk_does_not_return_unparseable_file_as_a_success(tmp_path: Path) -> None:
    """A truncated `.livespec.jsonc` must NOT come back on the success track.

    A success value is what `_records_for`'s `pin_format` filter drops
    without ever making a decision, which is how this became a passing
    row.
    """
    _ = (tmp_path / ".livespec.jsonc").write_text(_TRUNCATED, encoding="utf-8")

    walked = discover(root=tmp_path, source_repo=None)

    assert not isinstance(walked, IOSuccess), (
        "an unparseable .livespec.jsonc came back on the SUCCESS track; it is "
        "then indistinguishable from a repo carrying no pins once a consumer "
        "filters by pin_format (livespec-dev-tooling-2j2l)"
    )


def test_row_does_not_pass_on_an_unparseable_pin_file() -> None:
    """The observable the fleet sweep reports: not a PASS.

    This is the assertion that convicts the defect end-to-end — the row
    materializes the member's bytes, runs the real walk over them, and
    must not report health for a file it could not parse.
    """
    outcome = _rows_pin_currency.assert_livespec_compat_pin_currency(ctx=_context(), member=_MEMBER)

    assert not isinstance(outcome, RowPass), (
        f"pin-currency row reported {outcome!r} for a member whose "
        ".livespec.jsonc could not be parsed; an unparseable pin file must "
        'never render as a passing row (spec v039, §"Pin-currency severity '
        'policy": "A can\'t-PARSE is NOT a can\'t-read, and is NEVER a pass")'
    )
