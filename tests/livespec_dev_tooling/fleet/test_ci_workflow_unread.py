"""An unread ci.yml must not certify a member's required checks as aligned.

`assert_branch_protection`'s contract, from its own docstring: aligned means
"every required check matched by a ci.yml matrix leg OR a top-level ci.yml
job", because "a required check matching NEITHER is a phantom that can never
report and would deadlock every merge".

That comparison needs the member's ci.yml names. When the run could not
obtain them the comparison DOES NOT RUN — and the row used to return
`RowPass`. A member whose every merge would deadlock was certified aligned
because a read failed, which is the fail-open `livespec-dev-tooling-6ge`
names: a can't-read SKIPS, it does not pass.

⛔ AND THE OTHER HALF, WHICH IS NOT A CAN'T-READ AT ALL. The same `None`
was returned when ci.yml was READ and named nothing. That is the DEFINITIVE
form of the defect the row exists to catch — every required check is a
phantom — and it was the case that passed most quietly. Absence and
unreadability are separated here by the member's own TREE, exactly as
`_rows_files` already separates them for every other committed-file row.

⛔ THE POSITIVE CONTROL IS NOT OPTIONAL. If the row skipped or flagged
unconditionally, every assertion below would still pass while the row had
stopped distinguishing anything. `test_readable_ci_yml_naming_the_check_
still_passes` is the input that must produce NEITHER outcome.
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
    RowPass,
    RowSkip,
)
from livespec_dev_tooling.fleet._reconcile import reconcile_branch_protection
from livespec_dev_tooling.fleet._rows_github import assert_branch_protection

__all__: list[str] = []


_MEMBER = FleetMember(repo="widget", repo_class="impl-plugin")
_CI_WORKFLOW = ".github/workflows/ci.yml"
_TREE_ARGS: tuple[str, ...] = ("api", "repos/acme/widget/git/trees/master?recursive=1")
_PROTECTION_ARGS: tuple[str, ...] = ("api", "repos/acme/widget/branches/master/protection")
_CI_ARGS: tuple[str, ...] = (
    "api",
    f"repos/acme/widget/contents/{_CI_WORKFLOW}?ref=master",
    "-H",
    "Accept: application/vnd.github.raw",
)

_REAL_CI = "jobs:\n  ci-green:\n    name: ci-green\n"
# Otherwise-perfect protection requiring ONE check. Whether that check is a
# phantom is decided solely by the ci.yml reading, which is the variable.
_PROTECTION = {
    "enforce_admins": {"enabled": True},
    "required_status_checks": {"strict": False, "contexts": ["ci-green"]},
}


def _context(*, ci: GhResult | None, ci_in_tree: bool = True) -> FleetContext:
    tree = {
        "tree": [{"path": _CI_WORKFLOW, "mode": "100644"}] if ci_in_tree else [],
        "truncated": False,
    }
    table = {
        _TREE_ARGS: GhResult(returncode=0, stdout=json.dumps(tree), stderr=""),
        _PROTECTION_ARGS: GhResult(returncode=0, stdout=json.dumps(_PROTECTION), stderr=""),
    }
    if ci is not None:
        table[_CI_ARGS] = ci

    def run(*, args: list[str], stdin: str | None = None) -> GhResult:
        del stdin
        return table.get(tuple(args), GhResult(returncode=1, stdout="", stderr="no canned"))

    runner: GhRunner = run
    return FleetContext(owner="acme", run_gh=lift_gh(runner))


def test_readable_ci_yml_naming_the_check_still_passes() -> None:
    """POSITIVE CONTROL — the only input here that must be a plain pass."""
    ctx = _context(ci=GhResult(returncode=0, stdout=_REAL_CI, stderr=""))

    assert assert_branch_protection(ctx=ctx, member=_MEMBER) == RowPass()


def test_ci_yml_in_the_tree_but_unread_skips_rather_than_certifying_alignment() -> None:
    """The fail-open: a comparison that did not run reported as one that passed."""
    ctx = _context(ci=GhResult(returncode=1, stdout="", stderr="gh: 500"))

    outcome = assert_branch_protection(ctx=ctx, member=_MEMBER)

    assert isinstance(outcome, RowSkip)
    assert "alignment unverified" in outcome.reason
    assert _CI_WORKFLOW in outcome.reason


def test_ci_yml_definitively_absent_flags_every_required_check_as_phantom() -> None:
    """Not a can't-read. A member with no ci.yml can never report `ci-green`."""
    ctx = _context(ci=None, ci_in_tree=False)

    outcome = assert_branch_protection(ctx=ctx, member=_MEMBER)

    assert isinstance(outcome, RowFinding)
    assert "ci-green" in outcome.message
    assert "matches no ci.yml matrix leg or top-level job" in outcome.message


def test_unreadable_tree_does_not_certify_alignment_either() -> None:
    """The tree is what separates absent from unread, so its own failure counts."""

    def run(*, args: list[str], stdin: str | None = None) -> GhResult:
        del stdin
        if tuple(args) == _PROTECTION_ARGS:
            return GhResult(returncode=0, stdout=json.dumps(_PROTECTION), stderr="")
        return GhResult(returncode=1, stdout="", stderr="gh: 500")

    runner: GhRunner = run
    ctx = FleetContext(owner="acme", run_gh=lift_gh(runner))

    outcome = assert_branch_protection(ctx=ctx, member=_MEMBER)

    assert isinstance(outcome, RowSkip)
    assert "alignment unverified" in outcome.reason


def test_truncated_tree_is_not_read_as_a_definitively_absent_ci_yml() -> None:
    """A truncated tree cannot PROVE absence, so it must not manufacture one.

    This is the arm that separates the two safe answers from the unsafe
    one. `ci.yml` missing from a COMPLETE tree is definitive; missing from
    a truncated tree is unknown, and treating it as absence would flag
    every required check as a phantom on a member that may declare them
    all — a false red manufactured out of a partial read.
    """
    truncated = {"tree": [], "truncated": True}

    def run(*, args: list[str], stdin: str | None = None) -> GhResult:
        del stdin
        if tuple(args) == _PROTECTION_ARGS:
            return GhResult(returncode=0, stdout=json.dumps(_PROTECTION), stderr="")
        if tuple(args) == _TREE_ARGS:
            return GhResult(returncode=0, stdout=json.dumps(truncated), stderr="")
        return GhResult(returncode=1, stdout="", stderr="no canned")

    runner: GhRunner = run
    ctx = FleetContext(owner="acme", run_gh=lift_gh(runner))

    outcome = assert_branch_protection(ctx=ctx, member=_MEMBER)

    assert isinstance(outcome, RowSkip)
    assert "truncated" in outcome.reason


def test_reconcile_skips_rather_than_sending_the_operator_to_configure_by_hand() -> None:
    """A can't-read is not a member defect, and manual wiring is not its remedy."""
    ctx = _context(ci=GhResult(returncode=1, stdout="", stderr="gh: 500"))

    outcome = reconcile_branch_protection(ctx=ctx, member=_MEMBER)

    assert isinstance(outcome, RowSkip)
    assert "cannot derive required checks" in outcome.reason


def test_reconcile_still_reports_a_definitively_empty_matrix_as_a_finding() -> None:
    """The DEFINITIVE half stays a finding — only the fused can't-read moved."""
    ctx = _context(ci=GhResult(returncode=0, stdout=_REAL_CI, stderr=""))

    outcome = reconcile_branch_protection(ctx=ctx, member=_MEMBER)

    assert isinstance(outcome, RowFinding)
    assert "declares no matrix targets" in outcome.message
