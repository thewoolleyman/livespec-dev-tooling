"""_ci_workflow_source — obtain a member's ci.yml, separating ABSENT from UNREAD.

Split out of `_rows_github` to keep both that module and `_reconcile` under
the 250-LLOC hard ceiling, and because the absent-vs-unread separation is
one rule two rows must not spell differently.

⛔ WHY THIS CANNOT BE `ctx.file_text(...) is None`. That seam returns None
for a file that is ABSENT and for a file this run failed to READ alike — a
404 and a transport failure are the same `None`. Absence is DEFINITIVE (the
member genuinely ships no CI workflow) and unreadability is a NON-ANSWER,
so folding both onto a failure track would sweep a real, reportable state
into "I could not tell" — the mistake `livespec-dev-tooling-8o8e` records
as spelling a split "catch OSError" and swallowing `FileNotFoundError` with
its siblings. The member's OWN TREE is what separates them: a path that is
absent from a readable, untruncated tree is definitively absent, which is
exactly how `_rows_files._tree_path_outcome` already decides the same
question for every other committed-file row.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.io import IOFailure, IOResult, IOSuccess  # noqa: E402  — vendor-path-aware import.

from livespec_dev_tooling.fleet._context import FleetContext, FleetMember  # noqa: E402
from livespec_dev_tooling.fleet._rows_files import CI_WORKFLOW  # noqa: E402

__all__: list[str] = ["CiWorkflowUnread", "ci_workflow_text"]


@dataclass(frozen=True, kw_only=True)
class CiWorkflowUnread:
    """This run did not obtain `repo`'s ci.yml, so its job names are UNKNOWN.

    Unknown, not empty. Every consumer of a ci.yml name set compares it
    against something the member is required to match, and an empty set
    compares as "nothing matches" — which reads as a definitive verdict
    about the member rather than as the absence of a measurement.
    """

    repo: str
    detail: str


def ci_workflow_text(
    *, ctx: FleetContext, member: FleetMember
) -> IOResult[str | None, CiWorkflowUnread]:
    """The member's ci.yml source; `None` on DEFINITIVE absence.

    `None` on the SUCCESS track carries exactly one meaning — the member's
    readable, untruncated tree does not contain the file — and is an
    ANSWER: a repo with no CI workflow declares no check names, and the
    `ci-workflow` obligation row reports the absence itself. Only a state
    this run could not establish leaves the success track.
    """
    tree = ctx.tree(repo=member.repo)
    if not tree.readable:
        return IOFailure(CiWorkflowUnread(repo=member.repo, detail="master tree unreadable"))
    if CI_WORKFLOW not in tree.paths:
        if tree.truncated:
            # A truncated tree cannot prove absence; saying "absent" here
            # would manufacture the definitive answer this module exists
            # to stop manufacturing.
            return IOFailure(
                CiWorkflowUnread(
                    repo=member.repo,
                    detail=f"master tree truncated; absence of {CI_WORKFLOW} not definitive",
                )
            )
        return IOSuccess(None)
    text = ctx.file_text(repo=member.repo, path=CI_WORKFLOW)
    if text is None:
        return IOFailure(
            CiWorkflowUnread(
                repo=member.repo,
                detail=f"{CI_WORKFLOW} is in the tree but its contents did not read",
            )
        )
    return IOSuccess(text)
