"""`read_latest_release` answers on a railway, and three unreads stop being one.

`SPECIFICATION/contracts.md` section "Pin-currency severity policy" says "a
can't-READ never escalates" (livespec-dev-tooling-6ge), and this conversion
leaves that untouched: both pin sites still fold an unread release onto the
same non-escalating `RowPass`. What changes is REPRESENTATION. The `None`
this replaces covered THREE conditions — the read never answered, the payload
was not a release object, the release carried no `tag_name` — and the note
both sites rendered named only the first of them, so a release GitHub
answered with in full was reported to the operator as an unreadable payload.

⛔ WHY EVERY ASSERTION NAMES THE DETAIL RATHER THAN STOPPING AT `IOFailure`.
Three tests that each assert only "this left the success track" are
ASSERTION-IDENTICAL over fixtures that differ in exactly the thing the
conversion exists for; they would all pass against one collapsed failure
value, which is the sentinel wearing a railway. The detail is the only
observable that tells the three conditions apart.
"""

from __future__ import annotations

import json

from _gh_railway import lift_gh
from returns.io import IOFailure, IOSuccess
from returns.unsafe import unsafe_perform_io

from livespec_dev_tooling.fleet._context import (
    FleetContext,
    FleetMember,
    GhResult,
    GhRunner,
    RowPass,
)
from livespec_dev_tooling.fleet._rows_files import assert_dev_tooling_pin
from livespec_dev_tooling.fleet._rows_pin_currency import assert_livespec_compat_pin_currency
from livespec_dev_tooling.fleet._settle_window import LatestRelease, read_latest_release

__all__: list[str] = []


_MEMBER = FleetMember(repo="widget", repo_class="impl-plugin")
_TREE_ARGS: tuple[str, ...] = ("api", "repos/acme/widget/git/trees/master?recursive=1")
_LATEST_LIVESPEC_ARGS: tuple[str, ...] = ("api", "repos/acme/livespec/releases/latest")

_PINNED_COMPAT = json.dumps({"impl-plugin": {"compat": {"pinned": "v1.0.0", "livespec": "v1"}}})
_PINNED_PYPROJECT = '[tool.uv.sources]\nlivespec-dev-tooling = { git = "x", tag = "v1.2.0" }\n'

# The invariant half of the clause both pin sites render, and the detail the
# unanswered read contributes to it. Spelled as literals rather than built
# from the renderer under test, so a renderer that stopped distinguishing
# anything could not make its own assertion pass.
_CLAUSE_HEAD = "freshness unverified (latest release unread for "
_UNANSWERED_DETAIL = "the latest-release read did not answer; see this run's read failures"


def _context(*, files: dict[str, str], table: dict[tuple[str, ...], GhResult]) -> FleetContext:
    tree_payload = {
        "tree": [{"path": path, "mode": "100644"} for path in files],
        "truncated": False,
    }
    canned = {_TREE_ARGS: GhResult(returncode=0, stdout=json.dumps(tree_payload), stderr="")}
    for path, text in files.items():
        canned[
            (
                "api",
                f"repos/acme/widget/contents/{path}?ref=master",
                "-H",
                "Accept: application/vnd.github.raw",
            )
        ] = GhResult(returncode=0, stdout=text, stderr="")
    canned.update(table)

    def run(*, args: list[str], stdin: str | None = None) -> GhResult:
        del stdin
        return canned.get(tuple(args), GhResult(returncode=1, stdout="", stderr="no canned"))

    runner: GhRunner = run
    return FleetContext(owner="acme", run_gh=lift_gh(runner))


def _release_context(*, stdout: str | None) -> FleetContext:
    table: dict[tuple[str, ...], GhResult] = {}
    if stdout is not None:
        table[_LATEST_LIVESPEC_ARGS] = GhResult(returncode=0, stdout=stdout, stderr="")
    return _context(files={}, table=table)


def _detail_for(*, stdout: str | None) -> str:
    read = read_latest_release(ctx=_release_context(stdout=stdout), repo="livespec")

    assert isinstance(read, IOFailure)
    failure = unsafe_perform_io(read.failure())
    assert failure.repo == "livespec"
    return failure.detail


def test_a_readable_release_rides_the_success_track_with_both_fields() -> None:
    """`published_at` rides along, because the settle window is computed from it."""
    payload = json.dumps({"tag_name": "v1.1.0", "published_at": "2026-09-09T12:00:00Z"})

    read = read_latest_release(ctx=_release_context(stdout=payload), repo="livespec")

    assert isinstance(read, IOSuccess)
    assert unsafe_perform_io(read.unwrap()) == LatestRelease(
        tag="v1.1.0", published_at="2026-09-09T12:00:00Z"
    )


def test_a_read_that_never_answered_says_so_and_names_the_repo() -> None:
    """`gh` never ran or exited non-zero: the cause is on this run's read failures."""
    assert _detail_for(stdout=None) == _UNANSWERED_DETAIL


def test_a_payload_that_is_not_a_release_object_is_not_an_unread_payload() -> None:
    """The endpoint ANSWERED — with something that is not a release.

    This is the quieter of the two non-answers: `gh` exited 0 and the JSON
    parsed, so nothing upstream recorded a read failure at all.
    """
    detail = _detail_for(stdout=json.dumps([{"tag_name": "v1.1.0"}]))

    assert "not a release object" in detail
    assert detail != _UNANSWERED_DETAIL


def test_a_release_without_a_tag_name_says_which_field_is_missing() -> None:
    """A tagless release is a readable payload the freshness comparison cannot use."""
    detail = _detail_for(stdout=json.dumps({"id": 1, "published_at": "2026-09-09T12:00:00Z"}))

    assert "tag_name" in detail
    assert detail != _UNANSWERED_DETAIL


def test_both_pin_sites_render_the_same_unread_clause_and_still_pass() -> None:
    """Drift between the two persisting-gap sites is what this asserts against.

    `_rows_files`'s own comment says "both persisting-gap sites must move
    together or the promotion is half-armed", and a per-site test cannot see
    them drift. Severity is asserted too: a can't-read still never escalates.
    """
    compat = assert_livespec_compat_pin_currency(
        ctx=_context(files={".livespec.jsonc": _PINNED_COMPAT}, table={}), member=_MEMBER
    )
    dev_tooling = assert_dev_tooling_pin(
        ctx=_context(files={"pyproject.toml": _PINNED_PYPROJECT}, table={}), member=_MEMBER
    )

    assert isinstance(compat, RowPass)
    assert isinstance(dev_tooling, RowPass)
    assert compat.note == f"pin records present; {_CLAUSE_HEAD}livespec: {_UNANSWERED_DETAIL})"
    assert dev_tooling.note == (
        f"pin present; {_CLAUSE_HEAD}livespec-dev-tooling: {_UNANSWERED_DETAIL})"
    )
