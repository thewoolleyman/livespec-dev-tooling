"""Every remaining "the `gh` never ran" arm of the central seam.

The sibling `test_context_invocation_railway.py` pins the seam itself and
the two READ paths that recorded a fabricated cause. This file covers the
row and reconcile arms, which no existing test can reach: every canned
`GhRunner` in this suite answers as a `gh` that RAN — that is what
`fleet/CLAUDE.md`'s hermetic-testing mandate makes them — so the failure
track is structurally invisible to the tables the rows are tested through.

⛔ EACH ASSERTION HERE IS ABOUT A DIAGNOSTIC THAT USED TO BE WRONG, not
merely about a new branch existing. The fabricated 127 did not fail
loudly; it produced confident sentences about the member, and those
sentences are what these tests pin.
"""

from __future__ import annotations

from returns.io import IOFailure

from livespec_dev_tooling.fleet._context import (
    FleetContext,
    FleetMember,
    GhOutcome,
    RowFinding,
    RowSkip,
)
from livespec_dev_tooling.fleet._invocation_failure import (
    BINARY_ABSENT,
    InvocationNotPerformed,
)
from livespec_dev_tooling.fleet._reconcile import (
    reconcile_delete_branch_on_merge,
    reconcile_merge_settings,
    reconcile_shim_workflows,
)
from livespec_dev_tooling.fleet._rows_github import assert_branch_protection
from livespec_dev_tooling.fleet._tree_state import TreeState
from livespec_dev_tooling.fleet.merged_branch_sweep import (
    SweepableBranch,
    SweepMode,
    _api_pages,
    _ApiFailure,
    _delete_sweepable,
)

__all__: list[str] = []

_MEMBER = FleetMember(repo="widget", repo_class="member")
# Readable and EMPTY, so every shim workflow counts as missing and the row
# reaches the branch probe rather than short-circuiting on an unreadable tree.
_READABLE_EMPTY_TREE = TreeState(readable=True)


def _never_ran(*, args: list[str], stdin: str | None = None) -> GhOutcome:
    """A `GhRunner` reporting every invocation as never performed."""
    del stdin
    return IOFailure(
        InvocationNotPerformed(argv=("gh", *args), kind=BINARY_ABSENT, detail="gh CLI not on PATH")
    )


def _ctx() -> FleetContext:
    return FleetContext(owner="acme", run_gh=_never_ran)


def test_merge_settings_names_the_uninvokable_gh_not_the_member() -> None:
    """`_gh_failed`'s not-performed arm.

    "setting merge settings failed" describes an operation against the
    member. Nothing was asked of the member.
    """
    outcome = reconcile_merge_settings(ctx=_ctx(), member=_MEMBER)
    assert isinstance(outcome, RowFinding)
    assert "gh" in outcome.message
    assert "setting merge settings failed" not in outcome.message


def test_delete_branch_on_merge_does_not_advise_a_token_permission_fix() -> None:
    """The remediation it normally prints is wrong advice when nothing ran.

    That finding tells the operator to re-run with a token carrying
    repository Administration permission — a diagnosis of the TOKEN, from
    a run that never presented one.
    """
    outcome = reconcile_delete_branch_on_merge(ctx=_ctx(), member=_MEMBER)
    assert isinstance(outcome, RowFinding)
    assert "Administration permission" not in outcome.message


def test_branch_protection_does_not_guess_at_an_admin_scope() -> None:
    """Same shape at the READ side: "needs admin scope" is a guess about the token."""
    outcome = assert_branch_protection(ctx=_ctx(), member=_MEMBER)
    assert isinstance(outcome, RowSkip)
    assert "needs admin scope" not in outcome.reason


def test_shim_branch_probe_that_never_ran_does_not_read_as_a_missing_branch() -> None:
    """The most dangerous of the four, because the wrong answer MUTATES.

    An unrun probe read as "no such branch" sends the run on to CREATE a
    shim branch and open a PR whose non-existence it never established.
    """
    ctx = _ctx()
    ctx.tree_cache["widget"] = _READABLE_EMPTY_TREE
    outcome = reconcile_shim_workflows(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowSkip)
    assert "gh" in outcome.reason


def test_a_branch_is_deleted_only_when_a_gh_that_ran_said_so() -> None:
    """A sweep that never touched the remote must not report deletions."""
    branches = [SweepableBranch(branch="feature/x", pr_number=1)]
    deleted = _delete_sweepable(
        ctx=_ctx(), repo="widget", branches=branches, mode=SweepMode.EXECUTE
    )
    assert deleted == []


def test_api_pages_reports_the_uninvokable_gh_as_the_failure_cause() -> None:
    """The sweep's paginated read carries a CAUSE into its operator message.

    `_stderr_text` reads that cause off a `gh` that spoke. When nothing ran
    there is no stderr to read, so the seam's own reason is carried instead
    of an empty string that would render as a blank explanation.
    """
    failure = _api_pages(ctx=_ctx(), repo="widget", path="repos/acme/widget/pulls")
    assert isinstance(failure, _ApiFailure)
    assert "gh" in failure.stderr
    assert failure.stderr.strip()
