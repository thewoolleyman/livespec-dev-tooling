"""A stale pin whose open-PR list did not answer names NEITHER staleness class.

`SPECIFICATION/contracts.md` §"Pin-currency severity policy" partitions a
stale pin into FIRED-AND-COULD-NOT-LAND and NEVER-FIRED, calls the
partition exhaustive "because a bump PR for the latest release either is
open or is not", and requires the diagnostic to name "WHICH of the two
classes applies". The partition is exhaustive over the WORLD; a RUN that
could not read the PR list has established neither class, and reporting
the never-fired class from that run claims something the run did not
measure.

WHY THIS FILE DRIVES BOTH ROWS AND ASSERTS THEY AGREE. There are exactly
two persisting-gap sites — `_rows_pin_currency`'s three pin-format rows
and `_rows_files`'s dev-tooling-pin leg — and `_rows_files`'s own comment
already says "both persisting-gap sites must move together or the
promotion is half-armed". A per-site test cannot see them drift apart, so
the agreement is asserted directly rather than hoped for.

⛔ WHY THE ASSERTIONS DO NOT STOP AT `severity == "warning"`. The suite
already carried `test_unreadable_pr_list_never_escalates` beside
`test_stale_without_open_bump_pr_stays_warning`, and the two were
ASSERTION-IDENTICAL — both asserted warning severity and nothing else,
over fixtures that differ in exactly the thing the pair is named for.
Two tests whose assertions coincide prove the code treats their fixtures
the same; they cannot detect the fusion that makes it do so. Every
assertion below therefore names the distinguishing DIAGNOSTIC, which is
the only observable that differs.
"""

from __future__ import annotations

import json

from _gh_railway import lift_gh

from livespec_dev_tooling.fleet._context import (
    FleetContext,
    FleetMember,
    GhResult,
    GhRunner,
    RowFinding,
)
from livespec_dev_tooling.fleet._rows_files import assert_dev_tooling_pin
from livespec_dev_tooling.fleet._rows_pin_currency import assert_livespec_compat_pin_currency

__all__: list[str] = []


_MEMBER = FleetMember(repo="widget", repo_class="impl-plugin")
_TREE_ARGS: tuple[str, ...] = ("api", "repos/acme/widget/git/trees/master?recursive=1")
_LATEST_LIVESPEC_ARGS: tuple[str, ...] = ("api", "repos/acme/livespec/releases/latest")
_LATEST_DEV_TOOLING_ARGS: tuple[str, ...] = (
    "api",
    "repos/acme/livespec-dev-tooling/releases/latest",
)
_OPEN_PRS_ARGS: tuple[str, ...] = ("api", "repos/acme/widget/pulls?state=open&per_page=100")

_STALE_COMPAT = json.dumps({"impl-plugin": {"compat": {"pinned": "v1.0.0", "livespec": "v1"}}})
_STALE_PYPROJECT = '[tool.uv.sources]\nlivespec-dev-tooling = { git = "x", tag = "v1.2.0" }\n'

# The two ways this run can fail to obtain the list, both of which used to
# reach `parse_open_bump_prs` or its caller as an EMPTY list of bump PRs.
# The second is the quieter one: `gh` exited 0 and the payload parsed, so
# nothing upstream recorded a read failure at all — the `pulls` body simply
# was not the list of pull requests it exists to be.
_UNANSWERED = GhResult(returncode=1, stdout="", stderr="gh: could not resolve host")
_NON_LIST = GhResult(returncode=0, stdout=json.dumps({"message": "Bad credentials"}), stderr="")


def _raw_args(*, path: str) -> tuple[str, ...]:
    return (
        "api",
        f"repos/acme/widget/contents/{path}?ref=master",
        "-H",
        "Accept: application/vnd.github.raw",
    )


def _context(*, files: dict[str, str], latest: dict[tuple[str, ...], str], open_prs: GhResult):
    tree_payload = {
        "tree": [{"path": path, "mode": "100644"} for path in files],
        "truncated": False,
    }
    table = {_TREE_ARGS: GhResult(returncode=0, stdout=json.dumps(tree_payload), stderr="")}
    for path, text in files.items():
        table[_raw_args(path=path)] = GhResult(returncode=0, stdout=text, stderr="")
    for args, tag in latest.items():
        table[args] = GhResult(returncode=0, stdout=json.dumps({"tag_name": tag}), stderr="")
    table[_OPEN_PRS_ARGS] = open_prs

    def run(*, args: list[str], stdin: str | None = None) -> GhResult:
        del stdin
        return table.get(tuple(args), GhResult(returncode=1, stdout="", stderr="no canned"))

    runner: GhRunner = run
    # The FILTER-CONSUMING PREFLIGHT deliberately: it is the only context in
    # which the persisting class would escalate, so it is the only context in
    # which "stayed at warning" is a falsifiable claim rather than a tautology.
    return FleetContext(owner="acme", run_gh=lift_gh(runner), filter_consuming_preflight=True)


def _compat_outcome(*, open_prs: GhResult) -> RowFinding:
    ctx = _context(
        files={".livespec.jsonc": _STALE_COMPAT},
        latest={_LATEST_LIVESPEC_ARGS: "v1.1.0"},
        open_prs=open_prs,
    )
    outcome = assert_livespec_compat_pin_currency(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowFinding)
    return outcome


def _dev_tooling_outcome(*, open_prs: GhResult) -> RowFinding:
    ctx = _context(
        files={"pyproject.toml": _STALE_PYPROJECT},
        latest={_LATEST_DEV_TOOLING_ARGS: "v1.3.0"},
        open_prs=open_prs,
    )
    outcome = assert_dev_tooling_pin(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowFinding)
    return outcome


def test_unanswered_pr_list_reports_the_class_as_undetermined_not_never_fired() -> None:
    """The staleness itself still reports — only the CLASS is withheld."""
    outcome = _compat_outcome(open_prs=_UNANSWERED)

    assert "UNDETERMINED" in outcome.message
    # The stale facts the run DID establish survive: withholding the class
    # must not cost the operator the finding they can act on.
    assert "livespec_jsonc_compat_pinned" in outcome.message
    assert "v1.0.0" in outcome.message
    assert "v1.1.0" in outcome.message
    # A can't-read never escalates (livespec-dev-tooling-6ge), asserted in
    # the context where escalation is possible.
    assert outcome.severity == "warning"


def test_non_list_pr_payload_reports_the_class_as_undetermined() -> None:
    """A parsed payload that is not a list of PRs is a NON-ANSWER, not zero PRs."""
    outcome = _compat_outcome(open_prs=_NON_LIST)

    assert "UNDETERMINED" in outcome.message
    assert "not a list of pull requests" in outcome.message
    assert outcome.severity == "warning"


def test_dev_tooling_pin_leg_reports_the_class_as_undetermined() -> None:
    """The second persisting-gap site, which shares no code path with the first."""
    outcome = _dev_tooling_outcome(open_prs=_UNANSWERED)

    assert "UNDETERMINED" in outcome.message
    assert "dev-tooling pin v1.2.0 is stale" in outcome.message
    assert "v1.3.0" in outcome.message
    assert outcome.severity == "warning"


def test_both_persisting_gap_sites_emit_the_same_undetermined_clause() -> None:
    """Drift between the two sites is the failure this asserts against."""
    compat = _compat_outcome(open_prs=_UNANSWERED)
    dev_tooling = _dev_tooling_outcome(open_prs=_UNANSWERED)

    clause = "which staleness class applies is UNDETERMINED (open-PR list unread for widget: "
    assert clause in compat.message
    assert clause in dev_tooling.message


def test_a_readable_empty_pr_list_still_names_the_never_fired_class() -> None:
    """The POSITIVE CONTROL, without which every assertion above is worthless.

    If the undetermined clause were emitted unconditionally, all four tests
    above would pass while the code had stopped distinguishing anything at
    all — the same "instrument that cannot produce a negative" this thread
    has now found five times. A readable, EMPTY list is the input that must
    NOT produce the clause.
    """
    readable_empty = GhResult(returncode=0, stdout=json.dumps([]), stderr="")

    outcome = _compat_outcome(open_prs=readable_empty)

    assert "UNDETERMINED" not in outcome.message
    assert outcome.severity == "warning"
