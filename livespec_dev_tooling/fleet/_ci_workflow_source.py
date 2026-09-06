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
from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware import.

from livespec_dev_tooling.checks._ci_job_names import (  # noqa: E402
    parse_ci_matrix,
    parse_top_level_jobs,
    workflow_triggers_pull_request,
)
from livespec_dev_tooling.fleet._context import FleetContext, FleetMember  # noqa: E402
from livespec_dev_tooling.fleet._rows_files import CI_WORKFLOW  # noqa: E402

__all__: list[str] = ["CiWorkflowUnread", "ci_workflow_text", "member_required_check_names"]

_WORKFLOWS_DIR = ".github/workflows/"


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


def _extra_workflow_paths(*, tree_paths: frozenset[str]) -> set[str]:
    """Workflow files DIRECTLY under `.github/workflows/`, other than ci.yml.

    GitHub runs a workflow only when it sits at the top of
    `.github/workflows/` — a nested path is never a status-check reporter —
    and ci.yml is derived separately, so both are excluded here. Only `.yml`
    and `.yaml` entries qualify.
    """
    return {
        path
        for path in tree_paths
        if path.startswith(_WORKFLOWS_DIR)
        and path != CI_WORKFLOW
        and path.endswith((".yml", ".yaml"))
        and "/" not in path[len(_WORKFLOWS_DIR) :]
    }


def member_required_check_names(
    *, ctx: FleetContext, member: FleetMember
) -> IOResult[set[str], CiWorkflowUnread]:
    """Every status-check context a required check may LEGITIMATELY match.

    The union, across the member's canonical ref, of:

    - ci.yml's `matrix.target` legs and top-level job ids / `name:` values
      (the canonical merge gate — always a valid reporter), AND
    - the same job names from EVERY OTHER `.github/workflows/*` file whose
      `on:` includes `pull_request` or `pull_request_target`.

    The second source exists because a required status check can be reported
    by a base-branch-side gate kept deliberately OUTSIDE ci.yml — a
    `pull_request_target` workflow running the BASE branch's definition
    against an untrusted head (livespec-dev-tooling-uyhtih). A rule that knew
    only ci.yml read that check as a phantom that can never report and would
    deadlock every merge, and no ci.yml change could ever satisfy it.

    Returns UNKNOWN (an `IOFailure`) when the member's ci.yml — the CANONICAL
    reporter — could not be obtained, exactly as `ci_workflow_text` decides on
    its own: a can't-read of the primary source leaves the whole comparison
    UNVERIFIED rather than risking a false red against it. A SUPPLEMENTARY
    workflow that fails to read is handled more leniently (see the loop): its
    names go uncounted, degrading to the pre-uyhtih behaviour for that one
    file, never to a false pass.
    """
    ci = ci_workflow_text(ctx=ctx, member=member)
    if isinstance(ci, IOFailure):
        return ci
    names: set[str] = set()
    ci_text = unsafe_perform_io(ci.unwrap())
    if ci_text is not None:
        names |= parse_ci_matrix(source=ci_text) | parse_top_level_jobs(source=ci_text)
    tree = ctx.tree(repo=member.repo)
    for path in sorted(_extra_workflow_paths(tree_paths=tree.paths)):
        text = ctx.file_text(repo=member.repo, path=path)
        if text is None:
            # A supplementary reporter that did not read degrades to the
            # pre-uyhtih behaviour for THIS file — its names go uncounted —
            # never to a false pass: a check that no READABLE workflow names
            # is still flagged, exactly as before this second source existed.
            # Only ci.yml, the canonical reporter, escalates a can't-read to a
            # whole-comparison SKIP (via `ci_workflow_text`), because missing
            # it means the primary source itself is unverifiable.
            continue
        if workflow_triggers_pull_request(source=text):
            names |= parse_ci_matrix(source=text) | parse_top_level_jobs(source=text)
    return IOSuccess(names)
