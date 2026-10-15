"""Build the revert COMMIT the master-health reconciler's revert step requests.

Per `SPECIFICATION/contracts.md` section "Cross-repo coordination automation
surface", the design in this repository's
`plan/red-master-self-healing/research/001-charter-red-master-self-healing.md`
(epic `livespec-dev-tooling-zcp5vb`), and the negative verification recorded in
`docs/master-health-reconciler.md` section "The negative verification: a
web-flow revert here is UNSIGNED" (work-item `livespec-dev-tooling-7n2itg`).

THE RECONCILER DESCRIBES THE REVERT COMMIT; THE FORGE ONLY COMMITS IT. The
charter expected the revert to be a web-flow revert through the GraphQL
`revertPullRequest` mutation, "so it carries the signing the server-side-revert
exemption recognises". Measured 2026-10-14, it does not: every revert commit
GitHub minted for orchestrator PR #2918 reports `verification.verified: false`
with reason `unsigned`, as do 60 of 60 surveyed `master` commits across two
fleet repositories. The exemption in `docs/server-side-revert-exemption.md`
requires BOTH a signature verifying against the pinned web-flow trust root AND
byte-identity with the reverted commit's parent, and it FAILS CLOSED — so an
unsigned revert of a culprit that touched product impl `.py` is convicted by
`check-red-green-replay`'s commit-range gate, and revert-by-default heals
nothing for the commonest regression there is.

NEITHER HALF OF THE EXEMPTION MOVES. What moves is the only thing in that
pipeline that was ever ours: the reconciler stops asking the forge to AUTHOR
its revert and asks the forge to COMMIT a revert the reconciler itself
described, through `createCommitOnBranch` authenticated with the fleet GitHub
App installation token (`SPECIFICATION/contracts.md` section "GitHub App auth
model"). Whether the forge signs an App-authored commit is a LIVE MEASUREMENT
no sandbox can make — it needs a fleet repository and the App's private key —
and if it comes back unsigned the finding belongs on the plan epic rather than
in a weakened exemption.

THE REQUEST IS DATA, NOT A CALL. This package is network-I/O-free (see this
package's `__init__`), so the mutation is BUILT here and POSTED by the reusable
workflow, exactly as the decision table is computed here and acted on there.
That is also what keeps every claim about the revert replay-testable: the
request a given recorded forge state produces is a value a test can compare,
where a call would only be a thing that happened.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__: list[str] = [
    "FORGE_COMMIT_MUTATION",
    "REVERT_COMMIT_CREDENTIAL",
    "RevertCommitRequest",
    "revert_commit_request",
]

# The forge operation that COMMITS a tree the caller describes. It is the whole
# substitution this module exists for, so it is named once, here, and the
# sibling test asserts that no `master_health_*` module declares any other.
FORGE_COMMIT_MUTATION = "createCommitOnBranch"

# The ONE credential the revert commit may be built with, carried as DATA for
# the same reason `ReconcileStep.auto_merge_held` is: a transport reading the
# request cannot authenticate by omission. `GITHUB_TOKEN` is the omission that
# matters — a commit it authors triggers no downstream CI (GitHub's
# workflow-recursion ceiling), so the revert's own CI would never speak and the
# release step would wait forever on a verdict nothing was going to produce.
REVERT_COMMIT_CREDENTIAL = "github-app-installation-token"

# The revert branch is derived from the CULPRIT rather than from the run, so a
# duplicate reconcile run computes the same name and finds the branch already
# there. Same idempotence argument as the rest of the reconciler: the forge
# state, not a lock or a cursor, is what stops a second revert.
_REVERT_BRANCH_PREFIX = "master-health/revert-"
_SHORT_SHA_CHARS = 12


@dataclass(frozen=True, kw_only=True)
class RevertCommitRequest:
    """One `createCommitOnBranch` mutation, as the data a transport posts.

    `expected_head_oid` is the oid the mutation is told to expect at `branch`,
    which is what makes the post safe to retry: a branch that moved under the
    request fails the mutation rather than committing against a tree the
    reconciler never read.

    `headline` and `body` are separate because the mutation's `message` input
    is. The body carries the `This reverts commit <sha>.` line on its OWN line,
    which is not decoration: it is the lookup the server-side-revert exemption
    reads to decide which ancestor the restored bytes are compared against.
    """

    mutation: str
    credential: str
    branch: str
    expected_head_oid: str
    headline: str
    body: str


def revert_commit_request(
    *, culprit_sha: str, target_branch: str, expected_head_oid: str
) -> RevertCommitRequest:
    """The mutation one `STEP_OPEN_REVERT` run asks the forge for.

    The caller is the reusable workflow, which has already read the step out of
    `master_health_reconcile.reconcile_step` — so the culprit is passed in
    rather than re-derived here, and this module stays a builder with one job
    rather than a second copy of the decision table.
    """
    return RevertCommitRequest(
        mutation=FORGE_COMMIT_MUTATION,
        credential=REVERT_COMMIT_CREDENTIAL,
        branch=f"{_REVERT_BRANCH_PREFIX}{culprit_sha[:_SHORT_SHA_CHARS]}",
        expected_head_oid=expected_head_oid,
        headline=(
            f"chore(revert): undo {culprit_sha[:_SHORT_SHA_CHARS]} "
            f"to return {target_branch} to green"
        ),
        body=(
            f"This reverts commit {culprit_sha}.\n"
            "\n"
            "Built by the master-health reconciler's revert step, which "
            "describes the\nrevert commit itself rather than asking the forge "
            "to author one.\n"
        ),
    )
